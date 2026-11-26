"""배경음악 자동 선곡 · 배경 사진/영상 선택 · 브리프가 없는 날의 자동 곡 소개 릴스.

음악: pipeline/music/<계정>/catalog.json (tools/extract_highlights.py 로 만든 30초 하이라이트 클립)
배경: pipeline/backgrounds/<계정>/backgrounds.json (tools/prepare_backgrounds.py 로 만든 9:16 사진·영상)

선택 규칙 (둘 다 같은 방식)
  1) 발매된 곡만 (release_date 가 오늘 이하). 미발매곡은 발매일이 채워질 때까지 쓰지 않는다.
  2) 게시 기록에서 가장 적게 쓰인 것들 중에서
  3) 날짜를 기준으로 돌아가며 고른다 → 실제 게시가 꺼져 있어도 매일 다른 곡·배경이 나온다.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import date
from pathlib import Path

# 자동 곡 소개 릴스의 훅 문구. {title} 은 곡 제목으로 바뀐다. 날짜마다 돌아가며 쓴다.
HOOKS = [
    "오늘 하루 끝에\n[이 노래] 한 곡",
    "지금 이 풍경엔\n[이 노래]가 어울려요",
    "퇴근길에 틀어두기 좋은\n[1곡] 추천",
    "잠깐 멈춰서\n[15초]만 들어볼래요?",
    "말없이 걷고 싶은 날\n[이 노래]",
    "생각이 많은 밤엔\n[이 노래]",
    "창밖 보면서\n[이 노래] 어때요?",
]
SUBS = [
    "TIAND · {title}",
    "「{album}」 수록곡",
]
CTAS = [
    "전체 곡은 [프로필 링크]에서",
    "마음에 들면 [저장]해두세요",
    "오늘의 BGM, [팔로우]하고 매일 받아보기",
]


def _load(path: Path, key: str) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get(key, [])


def load_tracks(music_dir: Path) -> list[dict]:
    return _load(music_dir / "catalog.json", "tracks")


def load_backgrounds(bg_dir: Path) -> list[dict]:
    return _load(bg_dir / "backgrounds.json", "items")


def released(tracks: list[dict], today: date) -> list[dict]:
    return [t for t in tracks if t.get("release_date") and date.fromisoformat(t["release_date"]) <= today]


def _rotate_pick(items: list[dict], key: str, used: Counter, today: date, salt: int = 0) -> dict | None:
    if not items:
        return None
    low = min(used.get(i[key], 0) for i in items)
    pool = [i for i in items if used.get(i[key], 0) == low]
    return pool[(today.toordinal() * 7 + salt) % len(pool)]


def usage(state: dict, account: str, field: str) -> Counter:
    return Counter(e.get(field) for e in state.get("posted", []) if e.get("account") == account and e.get(field))


def find_track(tracks: list[dict], title: str) -> dict | None:
    """브리프의 곡 제목과 같은 곡을 카탈로그에서 찾는다 (대소문자·공백 무시)."""
    norm = lambda s: "".join((s or "").lower().split())
    t = norm(title)
    return next((x for x in tracks if t and norm(x["title"]) == t), None)


def pick_track(tracks: list[dict], state: dict, account: str, today: date) -> dict | None:
    return _rotate_pick(released(tracks, today), "id", usage(state, account, "track_id"), today)


def pick_background(items: list[dict], state: dict, account: str, today: date) -> dict | None:
    return _rotate_pick(items, "file", usage(state, account, "background"), today, salt=3)


def auto_brief(track: dict, today: date, duration: float = 15.0) -> dict:
    """브리프가 없는 날 쓰는 곡 소개 릴스 브리프."""
    n = today.toordinal()
    title = track["title"]
    hook = HOOKS[n % len(HOOKS)].format(title=title)
    sub2 = SUBS[1].format(album=track.get("album", "")) if track.get("album") and track["album"] != title \
        else "지금 바로 들어보세요"
    cta = CTAS[n % len(CTAS)]
    return {
        "id": f"{today.isoformat()}_auto_{track['id']}",
        "publish_date": today.isoformat(),
        "auto": True,
        "reel": {
            "duration": duration,
            "visual": "none",
            "hook": {"text": hook, "end": 3.0, "size": 84},
            "song": {"title": title, "artist": track.get("artist", "")},
            "subtitles": [
                {"start": 3.0, "end": 7.0, "text": f"[{title}]", "size": 80},
                {"start": 7.0, "end": 10.5, "text": sub2, "size": 64},
            ],
            "cta": {"start": 10.5, "title": title, "text": cta},
        },
        "caption": {
            "hook": hook.replace("\n", " ").replace("[", "").replace("]", ""),
            "body": f"오늘의 BGM: 「{title}」\n풍경이랑 같이 15초만 들어보세요.",
        },
        "hashtags": ["오늘의BGM", "플레이리스트", "감성플레이리스트", "풍경"],
    }
