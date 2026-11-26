#!/usr/bin/env python3
"""DistroKid 백업 폴더의 WAV 원본에서 릴스용 하이라이트 클립을 뽑아 음악 카탈로그를 만든다.

곡마다 가장 에너지가 높은(보통 후렴) 구간을 찾아 짧은 AAC(.m4a) 클립으로 자르고,
곡 정보(ISRC·앨범·발매일·클립 시작 위치)를 catalog.json 에 적는다.
원본 폴더는 읽기만 하고 절대 바꾸지 않는다. 이미 만든 클립은 건너뛴다.

    python3 tools/extract_highlights.py "E:/앨범/DistroKid 백업" --artist 띠앙드 \
        --out pipeline/music/tiand

의존성: ffmpeg 만 (파이썬 표준 라이브러리로 에너지 계산).
"""
from __future__ import annotations

import argparse
import array
import csv
import hashlib
import json
import math
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

CSV_NAME = "전체목록_ISRC_발매일.csv"
RATE = 8000  # 분석용 샘플레이트 (모노)


def find_highlight(wav: Path, clip: float, skip_ratio: float = 0.15) -> tuple[float, float]:
    """(시작초, 전체길이초). 곡 앞 skip_ratio 구간(인트로)은 건너뛰고 RMS 합이 가장 큰 clip초 창을 고른다."""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(wav), "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"],
        check=True, capture_output=True,
    ).stdout
    a = array.array("h")
    a.frombytes(raw[: len(raw) // 2 * 2])
    if sys.byteorder == "big":
        a.byteswap()
    sec = [math.sqrt(sum(x * x for x in a[i:i + RATE]) / max(1, len(a[i:i + RATE])))
           for i in range(0, len(a), RATE)]
    total = len(a) / RATE
    win = int(clip)
    if len(sec) <= win:
        return 0.0, total
    lo = min(int(len(sec) * skip_ratio), len(sec) - win)
    hi = max(lo, min(len(sec) - win, int(len(sec) * 0.92) - win))  # 끝부분 페이드아웃(아웃트로)은 피한다
    best, best_i = -1.0, lo
    cur = sum(sec[lo:lo + win])
    for i in range(lo, hi + 1):
        if i > lo:
            cur += sec[i + win - 1] - sec[i - 1]
        if cur > best:
            best, best_i = cur, i
    return float(best_i), total


def encode_clip(wav: Path, start: float, clip: float, out: Path, bitrate: str = "160k") -> None:
    fade = 0.4
    af = f"afade=t=in:d={fade},afade=t=out:st={clip - fade}:d={fade},loudnorm=I=-14:TP=-1.5:LRA=11"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.2f}", "-t", f"{clip:.2f}", "-i", str(wav),
         "-af", af, "-ac", "2", "-ar", "44100", "-c:a", "aac", "-b:a", bitrate, "-movflags", "+faststart",
         str(out)],
        check=True,
    )


def parse_date(v: str) -> str | None:
    m = re.match(r"(\d{4}-\d{2}-\d{2})$", (v or "").strip())
    if m:
        return m.group(1)
    return None  # 미발매: 예정일은 planned_date 로 따로 둔다


def planned_date(v: str) -> str | None:
    m = re.search(r"예정일\s*(\d{4}-\d{2}-\d{2})", v or "")
    return m.group(1) if m else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", type=Path, help="DistroKid 백업 폴더 (전체목록_ISRC_발매일.csv 가 있는 곳)")
    ap.add_argument("--artist", required=True, help="CSV 의 가수 값 (예: 띠앙드)")
    ap.add_argument("--display-artist", default=None, help="자막·캡션에 쓸 아티스트 표기 (기본: --artist)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--clip", type=float, default=30.0, help="클립 길이(초)")
    ap.add_argument("--only", nargs="*", default=None, help="이 ISRC 만 처리")
    args = ap.parse_args(argv)

    rows = [r for r in csv.DictReader(open(args.root / CSV_NAME, encoding="utf-8-sig")) if r["가수"] == args.artist]
    if not rows:
        print(f"CSV 에 가수 '{args.artist}' 곡이 없습니다.", file=sys.stderr)
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    cat_path = args.out / "catalog.json"
    catalog = json.loads(cat_path.read_text(encoding="utf-8")) if cat_path.exists() else {"tracks": []}
    known = {t["id"]: t for t in catalog["tracks"]}

    for r in rows:
        isrc = r["ISRC"].strip()
        if args.only and isrc not in args.only:
            continue
        # 미발매곡은 ISRC 가 아직 없어서 파일 경로로 임시 id 를 만든다.
        key = isrc or "NOISRC_" + hashlib.sha1(r["파일"].encode("utf-8")).hexdigest()[:8]
        clip_file = f"{key}.m4a"
        wav = args.root / r["파일"].replace("\\", "/")
        if key in known and (args.out / clip_file).exists():
            continue
        if not wav.exists():
            print(f"건너뜀 (파일 없음): {wav}", file=sys.stderr)
            continue
        start, total = find_highlight(wav, args.clip)
        encode_clip(wav, start, min(args.clip, total), args.out / clip_file)
        known[key] = {
            "id": key,
            "isrc": isrc or None,
            "title": r["곡명"].strip(),
            "artist": args.display_artist or args.artist,
            "album": r["앨범"].strip(),
            "track_no": int(r["트랙번호"] or 1),
            "release_date": parse_date(r["발매일"]),
            "planned_date": planned_date(r["발매일"]),
            "upc": r["UPC"].strip(),
            "file": clip_file,
            "source_start": round(start, 1),
            "source_length": round(total, 1),
            "clip_length": round(min(args.clip, total), 1),
        }
        print(f"{key}  {r['곡명']}  {start:.0f}s~ / {total:.0f}s")

    catalog["tracks"] = sorted(known.values(), key=lambda t: (t.get("release_date") or "9999", t["album"], t["track_no"]))
    catalog["generated"] = date.today().isoformat()
    cat_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"카탈로그: {cat_path} ({len(catalog['tracks'])}곡)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
