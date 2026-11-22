import json

import pytest

from tools.ig_upload import (
    ConfigError,
    ReelRequest,
    ReelUploader,
    UploadError,
    list_account_keys,
    resolve_account,
    validate,
)
from tools.ig_upload.__main__ import main


class FakeResp:
    def __init__(self, body, status=200):
        self._body = body
        self.status_code = status
        self.text = json.dumps(body)

    def json(self):
        return self._body


class FakeHttp:
    """요청을 기록하고 준비된 응답을 순서대로 돌려준다."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def _next(self, method, url, **kw):
        self.calls.append((method, url, kw))
        if not self.responses:
            raise AssertionError(f"예상치 못한 요청: {method} {url}")
        return self.responses.pop(0)

    def post(self, url, **kw):
        return self._next("POST", url, **kw)

    def get(self, url, **kw):
        return self._next("GET", url, **kw)


@pytest.fixture
def cfg(tmp_path):
    p = tmp_path / "accounts.json"
    p.write_text(
        json.dumps(
            {
                "accounts": {
                    "diopresent": {"username": "diopresent.official"},
                    "aimusic_chart": {"username": "aimusic_chart"},
                    "custom": {"access_token_env": "MY_TOKEN", "user_id_env": "MY_UID"},
                }
            }
        ),
        encoding="utf-8",
    )
    return p


ENV = {
    "IG_DIOPRESENT_ACCESS_TOKEN": "tok-dio-1234567890",
    "IG_DIOPRESENT_USER_ID": "1111",
    "IG_AIMUSIC_CHART_ACCESS_TOKEN": "tok-ai-1234567890",
    "IG_AIMUSIC_CHART_USER_ID": "2222",
}


@pytest.fixture
def video(tmp_path):
    v = tmp_path / "reel.mp4"
    v.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"0" * 100)
    return v


def acct(cfg, key="aimusic_chart"):
    return resolve_account(key, cfg, ENV)


# ---- 설정 ----

def test_multiple_accounts_resolve_from_env(cfg):
    a = resolve_account("aimusic_chart", cfg, ENV)
    d = resolve_account("diopresent", cfg, ENV)
    assert (a.user_id, a.username, a.access_token) == ("2222", "aimusic_chart", "tok-ai-1234567890")
    assert (d.user_id, d.username) == ("1111", "diopresent.official")
    assert list_account_keys(cfg) == ["diopresent", "aimusic_chart", "custom"]


def test_custom_env_names(cfg):
    a = resolve_account("custom", cfg, {"MY_TOKEN": "t" * 20, "MY_UID": "9"})
    assert a.user_id == "9"


def test_missing_env_is_reported(cfg):
    with pytest.raises(ConfigError, match="IG_AIMUSIC_CHART_ACCESS_TOKEN"):
        resolve_account("aimusic_chart", cfg, {"IG_AIMUSIC_CHART_USER_ID": "2"})


def test_unknown_account(cfg):
    with pytest.raises(ConfigError, match="알 수 없는 계정"):
        resolve_account("nope", cfg, ENV)


def test_token_is_masked(cfg):
    assert "1234567890" not in acct(cfg).masked_token


def test_repo_config_lists_both_accounts():
    assert {"diopresent", "aimusic_chart"} <= set(list_account_keys())


# ---- 검증 ----

def test_validate_ok(video):
    assert validate(ReelRequest(caption="안녕 #건축", video_path=video)) == []


def test_validate_errors(tmp_path):
    assert validate(ReelRequest(caption="x"))  # 영상 없음
    assert validate(ReelRequest(video_path=tmp_path / "none.mp4"))
    assert validate(ReelRequest(video_url="http://insecure/x.mp4"))
    assert validate(ReelRequest(caption="a" * 2201, video_url="https://x/v.mp4"))
    many = " ".join(f"#t{i}" for i in range(31))
    assert any("해시태그" in e for e in validate(ReelRequest(caption=many, video_url="https://x/v.mp4")))
    png = tmp_path / "a.png"
    png.write_bytes(b"1")
    assert any("확장자" in e for e in validate(ReelRequest(video_path=png)))


# ---- dry-run ----

def test_dry_run_makes_no_requests(cfg, video):
    http = FakeHttp([])
    logs = []
    res = ReelUploader(acct(cfg), http=http, log=logs.append).upload(
        ReelRequest(caption="hi", video_path=video), dry_run=True
    )
    assert http.calls == []
    assert res.dry_run and res.media_id is None
    joined = "\n".join(logs)
    assert "2222/media" in joined and "media_publish" in joined
    assert "tok-ai-1234567890" not in joined


def test_dry_run_still_validates(cfg):
    with pytest.raises(UploadError, match="검증 실패"):
        ReelUploader(acct(cfg), http=FakeHttp([]), log=lambda m: None).upload(ReelRequest(), dry_run=True)


# ---- 실제 업로드 흐름 (가짜 HTTP) ----

def test_resumable_upload_flow(cfg, video):
    http = FakeHttp(
        [
            FakeResp({"id": "C1", "uri": "https://rupload.facebook.com/ig-api-upload/v21.0/C1"}),
            FakeResp({"success": True}),
            FakeResp({"status_code": "IN_PROGRESS"}),
            FakeResp({"status_code": "FINISHED"}),
            FakeResp({"id": "M1"}),
            FakeResp({"permalink": "https://www.instagram.com/reel/abc/"}),
        ]
    )
    sleeps = []
    up = ReelUploader(acct(cfg), http=http, sleep=sleeps.append, poll_interval=2, log=lambda m: None)
    res = up.upload(ReelRequest(caption="캡션 #음악", video_path=video))

    assert (res.container_id, res.media_id) == ("C1", "M1")
    assert res.permalink.endswith("/reel/abc/")
    assert sleeps == [2]

    m, url, kw = http.calls[0]
    assert url == "https://graph.facebook.com/v21.0/2222/media"
    assert kw["data"]["media_type"] == "REELS"
    assert kw["data"]["upload_type"] == "resumable"
    assert kw["data"]["caption"] == "캡션 #음악"
    assert "video_url" not in kw["data"]

    m, url, kw = http.calls[1]
    assert url.endswith("/C1")
    assert kw["headers"]["Authorization"] == "OAuth tok-ai-1234567890"
    assert kw["headers"]["file_size"] == str(video.stat().st_size)
    assert kw["data"] == video.read_bytes()

    m, url, kw = http.calls[4]
    assert url.endswith("/2222/media_publish") and kw["data"]["creation_id"] == "C1"


def test_video_url_flow_skips_byte_upload(cfg):
    http = FakeHttp(
        [
            FakeResp({"id": "C2"}),
            FakeResp({"status_code": "FINISHED"}),
            FakeResp({"id": "M2"}),
            FakeResp({"permalink": "p"}),
        ]
    )
    res = ReelUploader(acct(cfg), http=http, log=lambda m: None).upload(
        ReelRequest(video_url="https://cdn.example.com/r.mp4", share_to_feed=False)
    )
    assert res.media_id == "M2"
    data = http.calls[0][2]["data"]
    assert data["video_url"] == "https://cdn.example.com/r.mp4"
    assert data["share_to_feed"] == "false"
    assert "upload_type" not in data


def test_processing_error_raises(cfg):
    http = FakeHttp([FakeResp({"id": "C3"}), FakeResp({"status_code": "ERROR", "status": "bad codec"})])
    with pytest.raises(UploadError, match="bad codec"):
        ReelUploader(acct(cfg), http=http, log=lambda m: None).upload(ReelRequest(video_url="https://x/v.mp4"))


def test_processing_timeout(cfg):
    http = FakeHttp([FakeResp({"id": "C4"})] + [FakeResp({"status_code": "IN_PROGRESS"})] * 10)
    up = ReelUploader(acct(cfg), http=http, sleep=lambda s: None, poll_interval=1, poll_timeout=3, log=lambda m: None)
    with pytest.raises(UploadError, match="시간 초과"):
        up.upload(ReelRequest(video_url="https://x/v.mp4"))


def test_graph_error_message_surfaces(cfg):
    http = FakeHttp([FakeResp({"error": {"message": "Invalid OAuth access token"}}, status=400)])
    with pytest.raises(UploadError, match="Invalid OAuth"):
        ReelUploader(acct(cfg), http=http, log=lambda m: None).upload(ReelRequest(video_url="https://x/v.mp4"))


# ---- CLI ----

def test_cli_dry_run_all_accounts(cfg, video, monkeypatch, capsys):
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    accounts = json.loads(cfg.read_text())
    accounts["accounts"].pop("custom")
    cfg.write_text(json.dumps(accounts))
    rc = main(["--all", "--config", str(cfg), "--video", str(video), "--caption", "hi", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "aimusic_chart" in out and "diopresent" in out


def test_cli_missing_env_exit_code(cfg, video, monkeypatch, capsys):
    for k in ENV:
        monkeypatch.delenv(k, raising=False)
    rc = main(["--account", "aimusic_chart", "--config", str(cfg), "--video", str(video), "--dry-run"])
    assert rc == 2
    assert "IG_AIMUSIC_CHART_ACCESS_TOKEN" in capsys.readouterr().err
