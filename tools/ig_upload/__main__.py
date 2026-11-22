"""CLI: python -m tools.ig_upload --account aimusic_chart --video reel.mp4 --caption-file cap.txt --dry-run"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import ConfigError, list_account_keys, resolve_account
from .uploader import ReelRequest, ReelUploader, UploadError


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m tools.ig_upload", description="Instagram 릴스 업로드")
    p.add_argument("--account", action="append", help="계정 키 (여러 번 지정 가능). --all 과 함께 쓰지 않음")
    p.add_argument("--all", action="store_true", help="설정 파일의 모든 계정에 업로드")
    p.add_argument("--config", help="계정 설정 파일 경로 (기본: config/ig_accounts.json)")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--video", type=Path, help="로컬 mp4/mov 파일")
    src.add_argument("--video-url", help="공개 https 영상 주소")
    cap = p.add_mutually_exclusive_group()
    cap.add_argument("--caption", default="", help="캡션 문자열")
    cap.add_argument("--caption-file", type=Path, help="캡션 텍스트 파일 (UTF-8)")
    p.add_argument("--no-feed", action="store_true", help="피드에는 공유하지 않음 (릴스 탭만)")
    p.add_argument("--cover-url", help="커버 이미지 공개 주소")
    p.add_argument("--thumb-offset-ms", type=int, help="썸네일로 쓸 프레임 위치(ms)")
    p.add_argument("--dry-run", action="store_true", help="실제 업로드 없이 검증과 계획만 출력")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.all:
            keys = list_account_keys(args.config)
        elif args.account:
            keys = args.account
        else:
            print("--account 또는 --all 을 지정하세요.", file=sys.stderr)
            return 2
        caption = args.caption_file.read_text(encoding="utf-8").strip() if args.caption_file else args.caption
        req = ReelRequest(
            caption=caption,
            video_path=args.video,
            video_url=args.video_url,
            share_to_feed=not args.no_feed,
            cover_url=args.cover_url,
            thumb_offset_ms=args.thumb_offset_ms,
        )
        accounts = [resolve_account(k, args.config) for k in keys]
    except (ConfigError, OSError) as e:
        print(f"설정 오류: {e}", file=sys.stderr)
        return 2

    failed = 0
    for acc in accounts:
        try:
            res = ReelUploader(acc).upload(req, dry_run=args.dry_run)
            if not res.dry_run:
                print(f"[{acc.key}] 완료: media_id={res.media_id} {res.permalink or ''}")
        except UploadError as e:
            failed += 1
            print(f"[{acc.key}] 실패: {e}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
