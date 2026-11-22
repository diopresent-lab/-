import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from pipeline import core
from pipeline.core import (
    Brief,
    PipelineError,
    draft_caption,
    draft_hashtags,
    pick_brief,
    publish_allowed,
    wait_for_slot,
)
from tools.ig_upload import ConfigError, UploadResult, resolve_account

KST = timezone(timedelta(hours=9))
ACC = {"key": "tiand", "base_hashtags": ["띠앙드", "TIAND", "자작곡"], "max_hashtags": 15,
       "caption_footer": "🎧 프로필 링크", "reel_defaults": {"tag": "TIAND", "cta_sub": "팔로우 → @tiand_official"}}


def brief(i, d=None, **extra):
    data = {"id": i, "reel": {"hook": {"text": "[훅] 문장"}, "song": {"title": "곡", "artist": "TIAND"},
                              "subtitles": [{"text": "자막\n둘"}], "cta": {"text": "[먼저] 들어볼래요?"}}}
    if d:
        data["publish_date"] = d
    data.update(extra)
    return Brief(id=i, path=Path(f"/x/{i}.json"), data=data)


# ---- 브리프 선택 ----

def test_pick_prefers_today_then_oldest_past():
    bs = [brief("a"), brief("b", "2026-11-25"), brief("c", "2026-11-23")]
    assert pick_brief(bs, set(), date(2026, 11, 25)).id == "b"
    assert pick_brief(bs, set(), date(2026, 11, 24)).id == "a"
    assert pick_brief(bs, {"a"}, date(2026, 11, 24)).id == "c"


def test_pick_skips_future_and_posted():
    bs = [brief("a", "2026-12-01")]
    with pytest.raises(PipelineError):
        pick_brief(bs, set(), date(2026, 11, 23))
    with pytest.raises(PipelineError):
        pick_brief([brief("a")], {"a"}, date(2026, 11, 23))


# ---- 캡션·해시태그 ----

def test_hashtags_dedupe_and_limit():
    b = brief("a", hashtags=["#tiand", "읽씹 금지", "자작곡"])
    tags = draft_hashtags(b, ACC)
    assert tags == ["#tiand", "#읽씹금지", "#자작곡", "#띠앙드"]
    many = brief("m", hashtags=[f"t{i}" for i in range(40)])
    assert len(draft_hashtags(many, ACC)) == 15


def test_caption_from_reel_text_when_no_caption():
    cap = draft_caption(brief("a"), ACC)
    assert cap.startswith("훅 문장")
    assert "자막 둘" in cap and "🎵 곡 - TIAND" in cap and "먼저 들어볼래요?" in cap
    assert "[" not in cap
    assert cap.rstrip().endswith("#자작곡")


def test_caption_uses_brief_caption():
    cap = draft_caption(brief("a", caption={"hook": "H", "body": "B", "cta": ""}), ACC)
    assert cap.split("\n\n")[:2] == ["H", "B"]


def test_sample_brief_is_valid():
    from tools.ig_upload import ReelRequest, validate

    acc = core.load_pipeline_config("tiand")
    for b in core.load_briefs(core._abs(acc["briefs_dir"])):
        cap = draft_caption(b, acc)
        assert not [e for e in validate(ReelRequest(caption=cap, video_url="https://x/y.mp4"))]
        assert b.data["reel"]["hook"]["end"] <= 3.0


# ---- 승인 게이트 ----

@pytest.mark.parametrize("flag,env,ok", [
    (False, {}, False),
    (False, {"IG_PUBLISH_APPROVED": "true"}, False),
    (True, {}, False),
    (True, {"IG_PUBLISH_APPROVED": "false"}, False),
    (True, {"IG_PUBLISH_APPROVED": "1"}, False),
    (True, {"IG_PUBLISH_APPROVED": "true"}, True),
])
def test_publish_gate(flag, env, ok):
    assert publish_allowed(flag, env)[0] is ok


def test_resolve_account_without_secrets_for_dry_run():
    acct = resolve_account("tiand", env={}, require_secrets=False)
    assert acct.username == "tiand_official" and acct.access_token == ""
    with pytest.raises(ConfigError):
        resolve_account("tiand", env={})


def test_wait_for_slot():
    slept = []
    slot = datetime(2026, 11, 23, 19, 0, tzinfo=KST)
    wait_for_slot(slot, lambda: slot - timedelta(minutes=10), slept.append, log=lambda m: None)
    assert slept == [600]
    wait_for_slot(slot, lambda: slot + timedelta(minutes=5), slept.append, log=lambda m: None)
    assert slept == [600]
    with pytest.raises(PipelineError):
        wait_for_slot(slot, lambda: slot - timedelta(hours=3), slept.append, log=lambda m: None)


# ---- prepare → publish 흐름 ----

class FakeUploader:
    calls = []

    def __init__(self, acct):
        self.acct = acct

    def upload(self, req, dry_run=False):
        FakeUploader.calls.append((self.acct.key, dry_run, req.caption))
        return UploadResult(account=self.acct.key, dry_run=dry_run,
                            media_id=None if dry_run else "m1", permalink=None if dry_run else "https://ig/p/1")


@pytest.fixture
def setup(tmp_path, monkeypatch):
    bdir = tmp_path / "briefs"
    bdir.mkdir()
    (bdir / "a.json").write_text(json.dumps(brief("a").data, ensure_ascii=False), encoding="utf-8")
    cfg = tmp_path / "pipeline.json"
    cfg.write_text(json.dumps({"timezone_offset_hours": 9, "accounts": {"tiand": {
        **{k: v for k, v in ACC.items() if k != "key"}, "username": "tiand_official", "slot_time": "19:00",
        "briefs_dir": str(bdir), "state_file": str(tmp_path / "posted.json")}}}), encoding="utf-8")
    FakeUploader.calls = []

    def fake_render(reel_cfg, workdir):
        Path(reel_cfg["output"]).write_bytes(b"\x00" * 10)
        assert reel_cfg["cta"]["sub"] == "팔로우 → @tiand_official"
        return Path(reel_cfg["output"])

    out = tmp_path / "build"
    m = core.prepare("tiand", out, today=date(2026, 11, 23), render=fake_render,
                     uploader_factory=FakeUploader, env={}, config_path=cfg)
    return tmp_path, cfg, out, m


def test_prepare_writes_manifest_and_dry_runs(setup):
    tmp, cfg, out, m = setup
    assert m["brief_id"] == "a" and (out / "manifest.json").exists() and (out / "caption.txt").exists()
    assert FakeUploader.calls == [("tiand", True, m["caption"])]


def test_publish_without_approval_is_dry_run(setup):
    tmp, cfg, out, m = setup
    r = core.publish(out / "manifest.json", True, env={}, uploader_factory=FakeUploader,
                     config_path=cfg, log=lambda s: None, wait=False)
    assert r["published"] is False
    assert FakeUploader.calls[-1][1] is True
    assert not (tmp / "posted.json").exists()


def test_publish_with_approval_posts_once(setup):
    tmp, cfg, out, m = setup
    env = {"IG_PUBLISH_APPROVED": "true", "IG_TIAND_ACCESS_TOKEN": "tok", "IG_TIAND_USER_ID": "1"}
    r = core.publish(out / "manifest.json", True, env=env, uploader_factory=FakeUploader,
                     config_path=cfg, log=lambda s: None, wait=False)
    assert r == {"published": True, "media_id": "m1", "permalink": "https://ig/p/1"}
    assert json.loads((tmp / "posted.json").read_text())["posted"][0]["brief_id"] == "a"
    with pytest.raises(PipelineError):
        core.publish(out / "manifest.json", True, env=env, uploader_factory=FakeUploader,
                     config_path=cfg, log=lambda s: None, wait=False)


def test_publish_approved_but_missing_token_fails(setup):
    tmp, cfg, out, m = setup
    with pytest.raises(ConfigError):
        core.publish(out / "manifest.json", True, env={"IG_PUBLISH_APPROVED": "true"},
                     uploader_factory=FakeUploader, config_path=cfg, log=lambda s: None, wait=False)
