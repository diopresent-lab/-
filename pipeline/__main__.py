"""CLI.

    python -m pipeline prepare --account tiand --out build/reel
    python -m pipeline publish --manifest build/reel/manifest.json            # 항상 dry-run
    IG_PUBLISH_APPROVED=true python -m pipeline publish --manifest ... --publish  # 실제 게시
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tools.ig_upload import ConfigError, UploadError

from .core import PipelineError, prepare, publish


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m pipeline", description="릴스 자동화 파이프라인")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare", help="브리프 선택 → 릴스 생성 → 캡션 초안 → dry-run 계획")
    p.add_argument("--account", required=True)
    p.add_argument("--out", type=Path, default=Path("build/reel"))
    p.add_argument("--brief", type=Path, help="특정 브리프 파일을 강제로 사용")
    q = sub.add_parser("publish", help="manifest 로 업로드 (승인 없으면 dry-run)")
    q.add_argument("--manifest", type=Path, required=True)
    q.add_argument("--publish", action="store_true", help="실제 게시 요청 (IG_PUBLISH_APPROVED=true 도 필요)")
    q.add_argument("--no-wait", action="store_true", help="게시 시각까지 기다리지 않음")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "prepare":
            m = prepare(args.account, args.out, brief_path=args.brief)
            print(json.dumps({k: m[k] for k in ("account", "brief_id", "slot_date", "video")}, ensure_ascii=False))
            print("\n--- 캡션 초안 ---\n" + m["caption"])
        else:
            r = publish(args.manifest, args.publish, wait=not args.no_wait)
            print(json.dumps(r, ensure_ascii=False))
        return 0
    except (PipelineError, ConfigError, UploadError, OSError) as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
