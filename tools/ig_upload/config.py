"""계정 설정 로딩.

계정 목록(이름·사용자명)은 config/ig_accounts.json 에 두고,
비밀값(액세스 토큰, IG 사용자 ID)은 환경변수로만 받는다.

환경변수 규칙 (계정 키가 aimusic_chart 이면):
    IG_AIMUSIC_CHART_ACCESS_TOKEN
    IG_AIMUSIC_CHART_USER_ID
설정 파일의 access_token_env / user_id_env 로 이름을 바꿀 수 있다.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "ig_accounts.json"
DEFAULT_GRAPH_HOST = "https://graph.facebook.com"
DEFAULT_API_VERSION = "v21.0"


class ConfigError(ValueError):
    """설정이 잘못됐거나 필요한 환경변수가 없을 때."""


@dataclass(frozen=True)
class Account:
    key: str
    username: str
    user_id: str
    access_token: str
    graph_host: str = DEFAULT_GRAPH_HOST
    api_version: str = DEFAULT_API_VERSION

    @property
    def masked_token(self) -> str:
        t = self.access_token
        return f"{t[:4]}…{t[-4:]}" if len(t) > 12 else "****"


def _env_prefix(key: str) -> str:
    return "IG_" + re.sub(r"[^A-Za-z0-9]", "_", key).upper()


def load_accounts_file(path: Path | str | None = None) -> dict:
    p = Path(path) if path else Path(os.environ.get("IG_ACCOUNTS_CONFIG", DEFAULT_CONFIG_PATH))
    if not p.exists():
        raise ConfigError(f"계정 설정 파일이 없습니다: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ConfigError(f"계정 설정 파일 JSON 오류: {p}: {e}") from e
    if not isinstance(data.get("accounts"), dict) or not data["accounts"]:
        raise ConfigError("설정 파일에 'accounts' 항목이 비어 있습니다.")
    return data


def list_account_keys(path: Path | str | None = None) -> list[str]:
    return list(load_accounts_file(path)["accounts"].keys())


def resolve_account(
    key: str,
    path: Path | str | None = None,
    env: Mapping[str, str] | None = None,
    require_secrets: bool = True,
) -> Account:
    """계정 정보를 읽는다.

    require_secrets=False 이면 토큰·사용자 ID가 없어도 자리표시자로 채운다.
    토큰이 아직 없을 때 dry-run 계획만 만들 때 쓴다(실제 업로드에는 쓰지 말 것).
    """
    env = os.environ if env is None else env
    data = load_accounts_file(path)
    accounts = data["accounts"]
    if key not in accounts:
        raise ConfigError(f"알 수 없는 계정 '{key}'. 사용 가능: {', '.join(accounts)}")
    entry = accounts[key] or {}
    prefix = _env_prefix(key)
    token_env = entry.get("access_token_env", f"{prefix}_ACCESS_TOKEN")
    uid_env = entry.get("user_id_env", f"{prefix}_USER_ID")

    missing = [n for n in (token_env, uid_env) if not env.get(n)]
    if missing and require_secrets:
        raise ConfigError(f"계정 '{key}'의 환경변수가 없습니다: {', '.join(missing)}")

    return Account(
        key=key,
        username=entry.get("username", key),
        user_id=env.get(uid_env) or f"<{uid_env}>",
        access_token=env.get(token_env) or "",
        graph_host=env.get("IG_GRAPH_HOST", data.get("graph_host", DEFAULT_GRAPH_HOST)).rstrip("/"),
        api_version=env.get("IG_API_VERSION", data.get("api_version", DEFAULT_API_VERSION)),
    )
