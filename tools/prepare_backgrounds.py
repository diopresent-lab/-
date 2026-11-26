#!/usr/bin/env python3
"""'플레이리스트배경사진' 같은 폴더의 사진·영상을 릴스 배경용(세로 9:16)으로 변환한다.

- 세로 사진: 1080x1920 으로 꽉 채워 자른다.
- 가로 사진: 흐리게 꽉 채운 배경 위에 원본을 가운데 놓는다 (풍경이 잘리지 않게).
- 영상: 720x1280, 소리 없음, 최대 15초, 용량을 줄여 저장한다 (릴스 렌더 때 1080x1920 으로 키운다).
원본 폴더는 읽기만 한다. 결과 목록은 out/backgrounds.json 에 적는다.

    python3 tools/prepare_backgrounds.py "E:/앨범/DistroKid 백업/플레이리스트배경사진" \
        --out pipeline/backgrounds/tiand --images 120

의존성: Pillow, ffmpeg.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps

W, H = 1080, 1920
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}
VID_EXT = {".mp4", ".mov", ".m4v"}


def short_id(name: str) -> str:
    return hashlib.sha1(name.encode("utf-8")).hexdigest()[:10]


def to_portrait(src: Path, out: Path) -> str:
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    if im.height >= im.width:
        ImageOps.fit(im, (W, H), Image.LANCZOS).save(out, quality=82, optimize=True, progressive=True)
        return "cover"
    bg = ImageOps.fit(im, (W // 4, H // 4), Image.LANCZOS).filter(ImageFilter.GaussianBlur(12)).resize((W, H))
    bg = Image.blend(bg, Image.new("RGB", (W, H)), 0.25)
    fg = im.resize((W, round(im.height * W / im.width)), Image.LANCZOS)
    bg.paste(fg, (0, (H - fg.height) // 2))
    bg.save(out, quality=82, optimize=True, progressive=True)
    return "blur-fill"


def to_video(src: Path, out: Path, max_sec: float = 15.0) -> None:
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(src), "-t", str(max_sec), "-an",
         "-vf", "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1,fps=30",
         "-c:v", "libx264", "-preset", "slow", "-crf", "28", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
         str(out)],
        check=True,
    )


def spread(items: list, n: int | None) -> list:
    """정렬된 목록에서 n개를 고르게 뽑는다 (같은 날 찍은 비슷한 사진이 몰리지 않게)."""
    if n is None or n >= len(items):
        return items
    step = len(items) / n
    return [items[int(i * step)] for i in range(n)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--images", type=int, default=None, help="사진은 이 개수만 고르게 뽑는다 (기본: 전부)")
    ap.add_argument("--videos", type=int, default=None, help="영상은 이 개수만 (기본: 전부)")
    args = ap.parse_args(argv)

    files = sorted(p for p in args.src.iterdir() if p.is_file())
    imgs = spread([p for p in files if p.suffix.lower() in IMG_EXT], args.images)
    vids = spread([p for p in files if p.suffix.lower() in VID_EXT], args.videos)
    args.out.mkdir(parents=True, exist_ok=True)
    man_path = args.out / "backgrounds.json"
    manifest = json.loads(man_path.read_text(encoding="utf-8")) if man_path.exists() else {"items": []}
    known = {i["source"]: i for i in manifest["items"]}

    for p in imgs + vids:
        if p.name in known and (args.out / known[p.name]["file"]).exists():
            continue
        is_vid = p.suffix.lower() in VID_EXT
        name = f"{'v' if is_vid else 'p'}_{short_id(p.name)}.{'mp4' if is_vid else 'jpg'}"
        try:
            if is_vid:
                to_video(p, args.out / name)
                item = {"type": "video", "file": name, "source": p.name}
            else:
                mode = to_portrait(p, args.out / name)
                item = {"type": "image", "file": name, "source": p.name, "fit": mode}
        except Exception as e:  # 깨진 파일은 건너뛴다
            print(f"건너뜀 {p.name}: {e}", file=sys.stderr)
            continue
        known[p.name] = item
        print(name, "<-", p.name)

    manifest["items"] = sorted(known.values(), key=lambda i: i["source"])
    man_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    n_v = sum(i["type"] == "video" for i in manifest["items"])
    print(f"배경 목록: {man_path} (사진 {len(manifest['items']) - n_v}, 영상 {n_v})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
