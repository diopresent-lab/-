"""Instagram Graph API(비즈니스/크리에이터 계정)로 릴스 업로드.

흐름:
  1) POST /{ig-user-id}/media   media_type=REELS  → 컨테이너 ID
       - 로컬 파일: upload_type=resumable 후 rupload 주소로 바이트 전송
       - 공개 URL: video_url 지정
  2) GET  /{container-id}?fields=status_code  → FINISHED 될 때까지 대기
  3) POST /{ig-user-id}/media_publish  creation_id=컨테이너 ID → 게시물 ID

dry_run=True 이면 네트워크 호출 없이 검증과 실행 계획만 돌려준다.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .config import Account

MAX_CAPTION_CHARS = 2200
MAX_HASHTAGS = 30
MAX_MENTIONS = 20
MAX_VIDEO_BYTES = 300 * 1024 * 1024
VIDEO_EXTS = {".mp4", ".mov"}


class UploadError(RuntimeError):
    """Graph API 호출 실패 또는 처리 실패."""


@dataclass
class ReelRequest:
    caption: str = ""
    video_path: Path | None = None
    video_url: str | None = None
    share_to_feed: bool = True
    cover_url: str | None = None
    thumb_offset_ms: int | None = None


@dataclass
class UploadResult:
    account: str
    dry_run: bool
    media_id: str | None = None
    container_id: str | None = None
    permalink: str | None = None
    plan: list[str] = field(default_factory=list)


def validate(req: ReelRequest) -> list[str]:
    """문제 목록을 돌려준다. 비어 있으면 통과."""
    errors: list[str] = []
    if bool(req.video_path) == bool(req.video_url):
        errors.append("video_path 와 video_url 중 정확히 하나만 지정해야 합니다.")
    if req.video_path:
        p = Path(req.video_path)
        if not p.is_file():
            errors.append(f"영상 파일이 없습니다: {p}")
        else:
            if p.suffix.lower() not in VIDEO_EXTS:
                errors.append(f"지원하지 않는 확장자입니다(mp4/mov만): {p.suffix}")
            if p.stat().st_size > MAX_VIDEO_BYTES:
                errors.append(f"영상이 300MB를 넘습니다: {p.stat().st_size} bytes")
            if p.stat().st_size == 0:
                errors.append("영상 파일이 비어 있습니다.")
    if req.video_url and not req.video_url.startswith("https://"):
        errors.append("video_url 은 https:// 공개 주소여야 합니다.")
    if len(req.caption) > MAX_CAPTION_CHARS:
        errors.append(f"캡션이 {MAX_CAPTION_CHARS}자를 넘습니다: {len(req.caption)}자")
    tags = re.findall(r"(?<!\w)#\w+", req.caption)
    if len(tags) > MAX_HASHTAGS:
        errors.append(f"해시태그가 {MAX_HASHTAGS}개를 넘습니다: {len(tags)}개")
    mentions = re.findall(r"(?<![\w.])@[\w.]+", req.caption)
    if len(mentions) > MAX_MENTIONS:
        errors.append(f"멘션이 {MAX_MENTIONS}개를 넘습니다: {len(mentions)}개")
    return errors


class ReelUploader:
    def __init__(
        self,
        account: Account,
        http: Any = None,
        sleep: Callable[[float], None] = time.sleep,
        poll_interval: float = 5.0,
        poll_timeout: float = 600.0,
        log: Callable[[str], None] = print,
    ):
        self.account = account
        self._http = http
        self.sleep = sleep
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout
        self.log = log

    @property
    def http(self):
        if self._http is None:
            import requests

            self._http = requests.Session()
        return self._http

    # ---- 내부 헬퍼 ----
    def _url(self, path: str) -> str:
        a = self.account
        return f"{a.graph_host}/{a.api_version}/{path.lstrip('/')}"

    @staticmethod
    def _json(resp) -> dict:
        try:
            body = resp.json()
        except ValueError:
            body = {}
        if resp.status_code >= 400 or (isinstance(body, dict) and "error" in body):
            err = body.get("error", {}) if isinstance(body, dict) else {}
            msg = err.get("message") or getattr(resp, "text", "") or "unknown error"
            raise UploadError(f"Graph API 오류 (HTTP {resp.status_code}): {msg}")
        return body

    def _container_params(self, req: ReelRequest) -> dict:
        params: dict[str, Any] = {
            "media_type": "REELS",
            "caption": req.caption,
            "share_to_feed": "true" if req.share_to_feed else "false",
        }
        if req.video_path:
            params["upload_type"] = "resumable"
        else:
            params["video_url"] = req.video_url
        if req.cover_url:
            params["cover_url"] = req.cover_url
        if req.thumb_offset_ms is not None:
            params["thumb_offset"] = str(req.thumb_offset_ms)
        return params

    # ---- 공개 API ----
    def plan(self, req: ReelRequest) -> list[str]:
        a = self.account
        steps = [
            f"계정: {a.key} (@{a.username}), IG user id {a.user_id}, token {a.masked_token}",
            f"POST {self._url(f'{a.user_id}/media')} {self._container_params(req)}",
        ]
        if req.video_path:
            size = Path(req.video_path).stat().st_size
            steps.append(
                f"POST https://rupload.facebook.com/ig-api-upload/{a.api_version}/<container-id> "
                f"({req.video_path}, {size} bytes)"
            )
        steps.append(f"GET  {self._url('<container-id>')}?fields=status_code  (FINISHED 까지 대기)")
        steps.append(f"POST {self._url(f'{a.user_id}/media_publish')} creation_id=<container-id>")
        return steps

    def upload(self, req: ReelRequest, dry_run: bool = False) -> UploadResult:
        errors = validate(req)
        if errors:
            raise UploadError("업로드 전 검증 실패:\n- " + "\n- ".join(errors))

        result = UploadResult(account=self.account.key, dry_run=dry_run, plan=self.plan(req))
        if dry_run:
            for line in result.plan:
                self.log(f"[dry-run] {line}")
            return result

        a = self.account
        created = self._json(
            self.http.post(
                self._url(f"{a.user_id}/media"),
                data={**self._container_params(req), "access_token": a.access_token},
            )
        )
        cid = created.get("id")
        if not cid:
            raise UploadError(f"컨테이너 ID를 받지 못했습니다: {created}")
        result.container_id = cid
        self.log(f"컨테이너 생성: {cid}")

        if req.video_path:
            self._send_bytes(cid, Path(req.video_path), created.get("uri"))

        self._wait_until_finished(cid)

        published = self._json(
            self.http.post(
                self._url(f"{a.user_id}/media_publish"),
                data={"creation_id": cid, "access_token": a.access_token},
            )
        )
        result.media_id = published.get("id")
        if not result.media_id:
            raise UploadError(f"게시 응답에 미디어 ID가 없습니다: {published}")
        self.log(f"게시 완료: {result.media_id}")

        try:
            info = self._json(
                self.http.get(
                    self._url(result.media_id),
                    params={"fields": "permalink", "access_token": a.access_token},
                )
            )
            result.permalink = info.get("permalink")
        except UploadError as e:  # 게시는 끝났으니 링크 조회 실패는 경고만
            self.log(f"permalink 조회 실패(게시는 완료됨): {e}")
        return result

    def _send_bytes(self, cid: str, path: Path, uri: str | None) -> None:
        a = self.account
        uri = uri or f"https://rupload.facebook.com/ig-api-upload/{a.api_version}/{cid}"
        data = path.read_bytes()
        self.log(f"영상 전송: {path.name} ({len(data)} bytes)")
        resp = self.http.post(
            uri,
            headers={
                "Authorization": f"OAuth {a.access_token}",
                "offset": "0",
                "file_size": str(len(data)),
            },
            data=data,
        )
        body = self._json(resp)
        if isinstance(body, dict) and body.get("success") is False:
            raise UploadError(f"영상 전송 실패: {body}")

    def _wait_until_finished(self, cid: str) -> None:
        waited = 0.0
        while True:
            body = self._json(
                self.http.get(
                    self._url(cid),
                    params={"fields": "status_code,status", "access_token": self.account.access_token},
                )
            )
            code = body.get("status_code")
            if code == "FINISHED":
                return
            if code in ("ERROR", "EXPIRED"):
                raise UploadError(f"영상 처리 실패 ({code}): {body.get('status', '')}")
            if waited >= self.poll_timeout:
                raise UploadError(f"영상 처리 대기 시간 초과 ({self.poll_timeout:.0f}s), 마지막 상태: {code}")
            self.log(f"처리 중… ({code})")
            self.sleep(self.poll_interval)
            waited += self.poll_interval
