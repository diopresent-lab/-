"""릴스 자동화 파이프라인 핵심 로직.

prepare: 다음 브리프 선택 → 릴스 MP4 생성 → 캡션·해시태그 초안 → dry-run 업로드 계획 → manifest.json
publish: manifest 를 읽어 승인 게이트를 통과했을 때만 실제 게시 → 게시 기록(state) 갱신

실제 게시는 두 조건이 모두 참일 때만 일어난다.
  1) 명령에 --publish 를 줬다
  2) 환경변수 IG_PUBLISH_APPROVED 가 정확히 "true" 다 (사용자가 켠 승인 스위치)
둘 중 하나라도 아니면 항상 dry-run 이다.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from . import media

ROOT = Path(__file__).resolve().parents[1]
PIPELINE_CONFIG = ROOT / "config" / "pipeline.json"
MAKE_REEL = ROOT / "reel" / "make_reel.py"
APPROVAL_ENV = "IG_PUBLISH_APPROVED"


class PipelineError(RuntimeError):
    pass


# --------------------------------------------------------------------------- 설정·상태

def load_pipeline_config(account: str, path: Path | str | None = None) -> dict:
    p = Path(path) if path else PIPELINE_CONFIG
    data = json.loads(p.read_text(encoding="utf-8"))
    accounts = data.get("accounts", {})
    if account not in accounts:
        raise PipelineError(f"config/pipeline.json 에 계정 '{account}' 이 없습니다. 사용 가능: {', '.join(accounts)}")
    cfg = dict(accounts[account])
    cfg["key"] = account
    cfg["tz"] = timezone(timedelta(hours=float(data.get("timezone_offset_hours", 9))))
    return cfg


def _abs(p: str | Path) -> Path:
    p = Path(p)
    return p if p.is_absolute() else ROOT / p


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"posted": []}
    return json.loads(path.read_text(encoding="utf-8"))


def posted_ids(state: dict, account: str) -> set[str]:
    return {e["brief_id"] for e in state.get("posted", []) if e.get("account") == account}


def record_posted(path: Path, account: str, brief_id: str, media_id: str | None,
                  permalink: str | None, now: datetime, extra: dict | None = None) -> None:
    state = load_state(path)
    entry = {
        "account": account,
        "brief_id": brief_id,
        "media_id": media_id,
        "permalink": permalink,
        "posted_at": now.isoformat(timespec="seconds"),
    }
    entry.update({k: v for k, v in (extra or {}).items() if v})
    state.setdefault("posted", []).append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- 브리프 선택

@dataclass
class Brief:
    id: str
    path: Path
    data: dict

    @property
    def publish_date(self) -> date | None:
        v = self.data.get("publish_date")
        return date.fromisoformat(v) if v else None


def load_briefs(briefs_dir: Path) -> list[Brief]:
    out = []
    for p in sorted(briefs_dir.glob("*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        out.append(Brief(id=data.get("id") or p.stem, path=p, data=data))
    return out


def pick_brief(briefs: list[Brief], done: set[str], today: date) -> Brief | None:
    """오늘 날짜로 지정된 브리프 → 없으면 날짜 미지정·지난 날짜 중 가장 오래된 미게시 브리프.

    미래 날짜로 지정된 브리프는 그날이 오기 전에는 쓰지 않는다. 쓸 브리프가 없으면 None.
    """
    pending = [b for b in briefs if b.id not in done]
    for b in pending:
        if b.publish_date == today:
            return b
    usable = [b for b in pending if b.publish_date is None or b.publish_date < today]
    return usable[0] if usable else None


# --------------------------------------------------------------------------- 릴스 설정·렌더

def build_reel_config(brief: Brief, acc_cfg: dict, output: Path, track: dict | None = None,
                      background: dict | None = None) -> dict:
    reel = json.loads(json.dumps(brief.data["reel"]))  # 깊은 복사
    defaults = acc_cfg.get("reel_defaults", {})
    reel.setdefault("tag", defaults.get("tag", ""))
    cta = reel.get("cta")
    if cta is not None and "sub" not in cta and defaults.get("cta_sub"):
        cta["sub"] = defaults["cta_sub"]
    audio = (reel.get("song") or {}).get("audio")
    if audio:
        reel["song"]["audio"] = str(_abs(audio))
    elif track:
        reel["song"]["audio"] = str(_abs(acc_cfg["music_dir"]) / track["file"])
        reel["song"]["audio_start"] = 0
        reel["song"].setdefault("artist", track.get("artist", ""))
    if background and "background" not in reel:
        src = str(_abs(acc_cfg["backgrounds_dir"]) / background["file"])
        reel["background"] = {background["type"]: src, "dim": float(acc_cfg.get("background_dim", 0.5))}
        reel.setdefault("visual", "none")
    reel["output"] = str(output)
    return reel


def render_reel(reel_cfg: dict, workdir: Path, runner: Callable = subprocess.run) -> Path:
    workdir.mkdir(parents=True, exist_ok=True)
    cfg_path = workdir / "reel_config.json"
    cfg_path.write_text(json.dumps(reel_cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    out = Path(reel_cfg["output"])
    proc = runner([sys.executable, str(MAKE_REEL), str(cfg_path), "-o", str(out)])
    if getattr(proc, "returncode", 0) != 0:
        raise PipelineError("릴스 생성(reel/make_reel.py)에 실패했습니다.")
    return out


# --------------------------------------------------------------------------- 캡션·해시태그

MARK = re.compile(r"\[([^\]]+)\]")


def _plain(text: str) -> str:
    return MARK.sub(r"\1", text or "").replace("\n", " ").strip()


def _norm_tag(t: str) -> str:
    return re.sub(r"\s+", "", t.lstrip("#"))


def draft_hashtags(brief: Brief, acc_cfg: dict) -> list[str]:
    """브리프 해시태그를 앞에, 계정 기본 해시태그를 뒤에 두고 중복(대소문자 무시)을 뺀다."""
    limit = int(acc_cfg.get("max_hashtags", 15))
    seen, out = set(), []
    for t in list(brief.data.get("hashtags", [])) + list(acc_cfg.get("base_hashtags", [])):
        n = _norm_tag(t)
        if n and n.lower() not in seen:
            seen.add(n.lower())
            out.append("#" + n)
    return out[:min(limit, 30)]


def draft_caption(brief: Brief, acc_cfg: dict) -> str:
    """브리프의 caption 값을 우선 쓰고, 없으면 릴스 문구(훅·자막·CTA)로 초안을 만든다."""
    reel = brief.data.get("reel", {})
    cap = brief.data.get("caption") or {}
    if isinstance(cap, str):
        cap = {"body": cap}
    hook = cap.get("hook") or _plain((reel.get("hook") or {}).get("text", ""))
    body = cap.get("body")
    if not body:
        subs = [_plain(s.get("text", "")) for s in reel.get("subtitles", [])]
        body = "\n".join(s for s in subs if s)
    song = reel.get("song") or {}
    song_line = ""
    if song.get("title"):
        song_line = f"🎵 {song['title']}" + (f" - {song['artist']}" if song.get("artist") else "")
    cta = cap.get("cta")
    if cta is None:
        c = reel.get("cta") or {}
        cta = _plain(c.get("text", ""))
    footer = acc_cfg.get("caption_footer", "")
    parts = [p for p in (hook, body, song_line, cta, footer) if p]
    tags = " ".join(draft_hashtags(brief, acc_cfg))
    return "\n\n".join(parts + ([tags] if tags else []))


# --------------------------------------------------------------------------- 승인 게이트

def publish_allowed(publish_flag: bool, env: dict | None = None) -> tuple[bool, str]:
    env = os.environ if env is None else env
    if not publish_flag:
        return False, "--publish 를 주지 않아 dry-run 으로 실행합니다."
    if env.get(APPROVAL_ENV, "").strip().lower() != "true":
        return False, f"승인 스위치 {APPROVAL_ENV}=true 가 아니어서 dry-run 으로 실행합니다."
    return True, "승인됨: 실제 게시합니다."


def slot_datetime(day: date, slot: str, tz) -> datetime:
    hh, mm = (int(x) for x in slot.split(":"))
    return datetime(day.year, day.month, day.day, hh, mm, tzinfo=tz)


def wait_for_slot(slot_at: datetime, now_fn: Callable[[], datetime], sleep: Callable[[float], None],
                  max_wait: float = 90 * 60, log: Callable[[str], None] = print) -> None:
    """게시 시각 전이면 기다린다(최대 max_wait초). 이미 지났으면 바로 진행."""
    delta = (slot_at - now_fn()).total_seconds()
    if delta <= 0:
        return
    if delta > max_wait:
        raise PipelineError(f"게시 시각 {slot_at.isoformat()} 까지 {delta / 60:.0f}분 남아 너무 이릅니다.")
    log(f"게시 시각 {slot_at.strftime('%H:%M')} 까지 {delta / 60:.1f}분 대기합니다.")
    sleep(delta)


# --------------------------------------------------------------------------- 단계

def prepare(account: str, out_dir: Path, today: date | None = None, brief_path: Path | None = None,
            render: Callable[[dict, Path], Path] = render_reel, uploader_factory=None,
            env: dict | None = None, config_path: Path | None = None) -> dict:
    from tools.ig_upload import ReelRequest, ReelUploader, resolve_account

    acc_cfg = load_pipeline_config(account, config_path)
    today = today or datetime.now(acc_cfg["tz"]).date()
    state_file = _abs(acc_cfg["state_file"])
    state = load_state(state_file)
    tracks = media.load_tracks(_abs(acc_cfg["music_dir"])) if acc_cfg.get("music_dir") else []
    backgrounds = media.load_backgrounds(_abs(acc_cfg["backgrounds_dir"])) if acc_cfg.get("backgrounds_dir") else []

    track = None
    if brief_path:
        data = json.loads(Path(brief_path).read_text(encoding="utf-8"))
        brief = Brief(id=data.get("id") or Path(brief_path).stem, path=Path(brief_path), data=data)
    else:
        brief = pick_brief(load_briefs(_abs(acc_cfg["briefs_dir"])), posted_ids(state, account), today)
    if brief is None:
        # 브리프가 없는 날: 카탈로그에서 곡을 골라 곡 소개 릴스를 자동으로 만든다.
        track = media.pick_track(tracks, state, account, today) if acc_cfg.get("auto_brief") else None
        if track is None:
            raise PipelineError(
                "게시할 브리프가 없습니다. pipeline/briefs/<계정>/ 에 새 브리프 JSON을 추가하세요."
            )
        data = media.auto_brief(track, today, float(acc_cfg.get("auto_duration", 15)))
        brief = Brief(id=data["id"], path=_abs(acc_cfg["briefs_dir"]) / f"{data['id']}.json", data=data)
    elif not (brief.data["reel"].get("song") or {}).get("audio"):
        # 브리프 곡이 카탈로그에 있으면 그 곡의 하이라이트를 배경음악으로 쓴다.
        track = media.find_track(tracks, (brief.data["reel"].get("song") or {}).get("title", ""))
    background = media.pick_background(backgrounds, state, account, today) \
        if brief.data.get("background", True) is not False else None

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "brief.json").write_text(json.dumps(brief.data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    video = out_dir / f"{brief.id}.mp4"
    render(build_reel_config(brief, acc_cfg, video, track, background), out_dir)

    caption = draft_caption(brief, acc_cfg)
    (out_dir / "caption.txt").write_text(caption + "\n", encoding="utf-8")

    acct = resolve_account(account, env=env, require_secrets=False)
    plan_lines: list[str] = []
    factory = uploader_factory or (lambda a: ReelUploader(a, log=plan_lines.append))
    factory(acct).upload(ReelRequest(caption=caption, video_path=video), dry_run=True)

    manifest = {
        "account": account,
        "username": acc_cfg.get("username"),
        "brief_id": brief.id,
        "brief_path": (str(brief.path.relative_to(ROOT)) if brief.path.is_relative_to(ROOT) else str(brief.path))
                      if brief.path.exists() else None,
        "slot_date": max(today, brief.publish_date or today).isoformat(),
        "slot_time": acc_cfg.get("slot_time", "19:00"),
        "video": video.name,
        "caption_file": "caption.txt",
        "caption": caption,
        "track_id": track["id"] if track else None,
        "track_title": track["title"] if track else None,
        "background": background["file"] if background else None,
        "dry_run_plan": plan_lines,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                           encoding="utf-8")
    return manifest


def publish(manifest_path: Path, publish_flag: bool, env: dict | None = None,
            now_fn: Callable[[], datetime] | None = None, sleep: Callable[[float], None] = time.sleep,
            uploader_factory=None, log: Callable[[str], None] = print,
            config_path: Path | None = None, wait: bool = True) -> dict:
    from tools.ig_upload import ReelRequest, ReelUploader, resolve_account

    env = os.environ if env is None else env
    m = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    base = Path(manifest_path).parent
    account = m["account"]
    acc_cfg = load_pipeline_config(account, config_path)
    now_fn = now_fn or (lambda: datetime.now(acc_cfg["tz"]))
    state_file = _abs(acc_cfg["state_file"])

    if m["brief_id"] in posted_ids(load_state(state_file), account):
        raise PipelineError(f"브리프 '{m['brief_id']}' 은 이미 게시됐습니다. 중복 게시를 막았습니다.")

    allowed, why = publish_allowed(publish_flag, env)
    log(why)
    req = ReelRequest(caption=(base / m["caption_file"]).read_text(encoding="utf-8").strip(),
                      video_path=base / m["video"])
    acct = resolve_account(account, env=env, require_secrets=allowed)
    factory = uploader_factory or (lambda a: ReelUploader(a, log=log))

    if not allowed:
        factory(acct).upload(req, dry_run=True)
        return {"published": False, "reason": why}

    if wait:
        slot_day = date.fromisoformat(m["slot_date"])
        wait_for_slot(slot_datetime(slot_day, m["slot_time"], acc_cfg["tz"]), now_fn, sleep, log=log)
    res = factory(acct).upload(req, dry_run=False)
    record_posted(state_file, account, m["brief_id"], res.media_id, res.permalink, now_fn(),
                  {"track_id": m.get("track_id"), "background": m.get("background")})
    return {"published": True, "media_id": res.media_id, "permalink": res.permalink}
