import json
from datetime import date
from pathlib import Path

from pipeline import core, media
from tests.test_pipeline import ACC, FakeUploader

TRACKS = [
    {"id": "A", "title": "Glitter", "artist": "TIAND", "album": "Midnight Illusion", "release_date": "2026-03-12", "file": "A.m4a"},
    {"id": "B", "title": "Rainy window", "artist": "TIAND", "album": "Rainy window", "release_date": "2026-04-10", "file": "B.m4a"},
    {"id": "C", "title": "미발매곡", "artist": "TIAND", "album": "x", "release_date": None, "file": "C.m4a"},
]
BGS = [{"type": "image", "file": "p1.jpg"}, {"type": "video", "file": "v1.mp4"}]


def test_unreleased_never_picked():
    for d in range(30):
        t = media.pick_track(TRACKS, {}, "tiand", date(2026, 11, 1 + d % 28))
        assert t["id"] != "C"


def test_rotates_daily_without_history():
    picks = {media.pick_track(TRACKS, {}, "tiand", date(2026, 11, d))["id"] for d in range(1, 8)}
    assert picks == {"A", "B"}


def test_least_used_first():
    state = {"posted": [{"account": "tiand", "track_id": "A"}]}
    for d in range(1, 8):
        assert media.pick_track(TRACKS, state, "tiand", date(2026, 11, d))["id"] == "B"


def test_find_track_ignores_case_and_spaces():
    assert media.find_track(TRACKS, "rainywindow")["id"] == "B"
    assert media.find_track(TRACKS, "읽씹 금지") is None


def test_auto_brief_is_valid_reel():
    b = media.auto_brief(TRACKS[0], date(2026, 11, 27))
    r = b["reel"]
    assert r["hook"]["end"] <= 3.0 and r["song"]["title"] == "Glitter"
    assert r["subtitles"][0]["start"] >= r["hook"]["end"]
    assert r["cta"]["start"] >= r["subtitles"][-1]["end"]
    assert b["id"].startswith("2026-11-27_auto_A")


def test_prepare_auto_brief_uses_music_and_background(tmp_path):
    music, bgs, briefs = tmp_path / "m", tmp_path / "b", tmp_path / "briefs"
    for d in (music, bgs, briefs):
        d.mkdir()
    (music / "catalog.json").write_text(json.dumps({"tracks": TRACKS}), encoding="utf-8")
    (bgs / "backgrounds.json").write_text(json.dumps({"items": BGS}), encoding="utf-8")
    cfg = tmp_path / "pipeline.json"
    cfg.write_text(json.dumps({"accounts": {"tiand": {
        **{k: v for k, v in ACC.items() if k != "key"}, "username": "tiand_official",
        "briefs_dir": str(briefs), "state_file": str(tmp_path / "posted.json"),
        "music_dir": str(music), "backgrounds_dir": str(bgs), "auto_brief": True}}}), encoding="utf-8")
    seen = {}

    def fake_render(reel_cfg, workdir):
        seen.update(reel_cfg)
        Path(reel_cfg["output"]).write_bytes(b"\x00")
        return Path(reel_cfg["output"])

    m = core.prepare("tiand", tmp_path / "out", today=date(2026, 11, 27), render=fake_render,
                     uploader_factory=FakeUploader, env={}, config_path=cfg)
    assert m["track_id"] in {"A", "B"} and m["background"] in {"p1.jpg", "v1.mp4"}
    assert seen["song"]["audio"].endswith(f"{m['track_id']}.m4a")
    assert ("image" in seen["background"]) or ("video" in seen["background"])
    assert "오늘의 BGM" in m["caption"]
    assert (tmp_path / "out" / "brief.json").exists()


def test_prepare_without_auto_and_no_brief_fails(tmp_path):
    import pytest
    briefs = tmp_path / "briefs"
    briefs.mkdir()
    cfg = tmp_path / "pipeline.json"
    cfg.write_text(json.dumps({"accounts": {"tiand": {
        **{k: v for k, v in ACC.items() if k != "key"}, "briefs_dir": str(briefs),
        "state_file": str(tmp_path / "posted.json")}}}), encoding="utf-8")
    with pytest.raises(core.PipelineError):
        core.prepare("tiand", tmp_path / "out", today=date(2026, 11, 27), render=lambda c, w: None,
                     uploader_factory=FakeUploader, env={}, config_path=cfg)
