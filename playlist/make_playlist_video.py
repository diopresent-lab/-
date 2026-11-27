#!/usr/bin/env python3
"""설정 파일(JSON)의 곡 목록으로 유튜브용 장시간 플레이리스트 영상을 만든다.

곡 길이를 ffprobe로 읽어 타임스탬프(유튜브 챕터)를 계산하고,
배경 이미지나 반복 영상 위에 곡들을 이어 붙인 1920x1080 MP4와
유튜브 제목·설명란 텍스트 파일을 함께 만든다. 의존성은 ffmpeg/ffprobe뿐이다.

    python playlist/make_playlist_video.py playlist/configs/soulful_girl_winter.json --check
    python playlist/make_playlist_video.py playlist/configs/soulful_girl_winter.json
    python playlist/make_playlist_video.py playlist/configs/soulful_girl_winter.json -o out.mp4
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
MIN_CHAPTER_SECONDS = 10  # 유튜브 챕터 최소 길이
MIN_CHAPTERS = 3  # 유튜브 챕터 최소 개수
SIZE = (1920, 1080)


class ConfigError(Exception):
    pass


def resolve_path(base_dir, path):
    """CSV에서 복사한 윈도우 경로(역슬래시)도 그대로 쓸 수 있게 정규화한다."""
    path = path.replace("\\", "/")
    if os.path.isabs(path) or (len(path) > 1 and path[1] == ":"):
        return path
    return os.path.join(base_dir.replace("\\", "/"), path) if base_dir else path


def load_config(config_path, base_dir_override=None):
    with open(config_path, encoding="utf-8") as f:
        cfg = json.load(f)
    tracks = cfg.get("tracks") or []
    if len(tracks) < MIN_CHAPTERS:
        raise ConfigError(f"곡이 최소 {MIN_CHAPTERS}개 있어야 유튜브 챕터가 생깁니다.")
    if not cfg.get("background"):
        raise ConfigError("background(배경 이미지 또는 영상 경로)가 필요합니다.")
    base_dir = base_dir_override or cfg.get("base_dir", "")
    for i, t in enumerate(tracks, 1):
        for key in ("artist", "title", "file"):
            if not t.get(key):
                raise ConfigError(f"{i}번 곡에 '{key}' 값이 없습니다.")
        t["path"] = resolve_path(base_dir, t["file"])
    cfg["background_path"] = resolve_path(base_dir, cfg["background"])
    cfg.setdefault("gap_seconds", 0)
    cfg.setdefault("fps", 24)
    cfg.setdefault("fit", "crop")
    video_filter(cfg["fit"], cfg["fps"])  # 잘못된 fit 값은 여기서 바로 걸러낸다
    return cfg


def missing_files(cfg):
    paths = [t["path"] for t in cfg["tracks"]] + [cfg["background_path"]]
    return [p for p in paths if not os.path.isfile(p)]


def probe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


def format_ts(seconds, with_hours):
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if with_hours:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m:02d}:{sec:02d}"


def build_chapters(tracks, durations, gap_seconds=0):
    """(시작 초, 라벨) 목록과 전체 길이를 돌려준다. 곡 사이 무음(gap)도 반영한다."""
    chapters, t = [], 0.0
    for i, (track, dur) in enumerate(zip(tracks, durations)):
        if dur < MIN_CHAPTER_SECONDS:
            raise ConfigError(f"'{track['title']}' 길이가 {MIN_CHAPTER_SECONDS}초보다 짧아 챕터가 깨집니다.")
        chapters.append((t, f"{track['artist']} - {track['title']}"))
        t += dur + (gap_seconds if i < len(tracks) - 1 else 0)
    return chapters, t


def chapter_lines(chapters, total):
    with_hours = total >= 3600
    return [f"{format_ts(start, with_hours)} {label}" for start, label in chapters]


def build_description(cfg, chapters, total):
    lines = ["[제목]", cfg.get("title", ""), "", "[설명란]"]
    lines += cfg.get("intro", [])
    lines += [""] + chapter_lines(chapters, total)
    if cfg.get("links"):
        lines += [""] + cfg["links"]
    if cfg.get("hashtags"):
        lines += ["", " ".join(cfg["hashtags"])]
    if cfg.get("pinned_comment"):
        lines += ["", "[고정 댓글]"] + cfg["pinned_comment"]
    return "\n".join(lines) + "\n"


def video_filter(fit, fps, label="0:v"):
    """배경을 1920x1080으로 맞춘다.

    crop: 화면을 꽉 채우고 넘치는 부분을 자른다.
    blur: 사진 전체를 가운데 두고, 남는 양옆을 같은 사진을 흐리게 깔아 채운다 (정사각형·세로 사진용).
    """
    w, h = SIZE
    tail = f"fps={fps},format=yuv420p[vout]"
    cover = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
    if fit == "crop":
        return f"[{label}]{cover},{tail}"
    if fit == "blur":
        return (
            f"[{label}]split=2[bgsrc][fgsrc];"
            f"[bgsrc]{cover},boxblur=30:3,eq=brightness=-0.12[bg];"
            f"[fgsrc]scale={w}:{h}:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,{tail}"
        )
    raise ConfigError(f"fit 값은 crop 또는 blur 여야 합니다: {fit}")


def build_ffmpeg_cmd(cfg, total, output):
    bg = cfg["background_path"]
    is_image = os.path.splitext(bg)[1].lower() in IMAGE_EXTS
    cmd = ["ffmpeg", "-y", "-hide_banner"]
    if is_image:
        cmd += ["-loop", "1", "-framerate", str(cfg["fps"]), "-i", bg]
    else:
        cmd += ["-stream_loop", "-1", "-i", bg]
    for t in cfg["tracks"]:
        cmd += ["-i", t["path"]]

    n = len(cfg["tracks"])
    gap = cfg["gap_seconds"]
    parts = []
    for i in range(n):
        chain = f"[{i + 1}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"
        if gap and i < n - 1:
            chain += f",apad=pad_dur={gap}"
        parts.append(f"{chain}[a{i}]")
    parts.append("".join(f"[a{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1[aout]")
    parts.append(video_filter(cfg.get("fit", "crop"), cfg["fps"]))
    cmd += ["-filter_complex", ";".join(parts), "-map", "[vout]", "-map", "[aout]"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"]
    if is_image:
        cmd += ["-tune", "stillimage"]
    cmd += ["-c:a", "aac", "-b:a", "320k", "-t", f"{total:.3f}", "-movflags", "+faststart", output]
    return cmd


def main(argv=None):
    ap = argparse.ArgumentParser(description="유튜브 플레이리스트 영상 만들기")
    ap.add_argument("config")
    ap.add_argument("-o", "--output", help="출력 MP4 경로 (기본: 설정의 output 또는 playlist.mp4)")
    ap.add_argument("--base-dir", help="곡 파일 기준 폴더 (설정의 base_dir 대신)")
    ap.add_argument("--check", action="store_true", help="렌더링 없이 파일·길이·타임스탬프만 확인")
    args = ap.parse_args(argv)

    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            sys.exit(f"{tool}을 찾을 수 없습니다. 윈도우: winget install Gyan.FFmpeg")
    try:
        cfg = load_config(args.config, args.base_dir)
        missing = missing_files(cfg)
        if missing:
            raise ConfigError("파일을 찾을 수 없습니다:\n  " + "\n  ".join(missing))
        durations = [probe_duration(t["path"]) for t in cfg["tracks"]]
        chapters, total = build_chapters(cfg["tracks"], durations, cfg["gap_seconds"])
    except ConfigError as e:
        sys.exit(f"설정 오류: {e}")

    output = args.output or cfg.get("output") or "playlist.mp4"
    desc_path = os.path.splitext(output)[0] + "_youtube.txt"
    description = build_description(cfg, chapters, total)
    with open(desc_path, "w", encoding="utf-8") as f:
        f.write(description)

    print(description)
    print(f"전체 길이: {format_ts(total, True)} ({len(chapters)}곡)")
    print(f"설명란 파일: {desc_path}")
    if args.check:
        return 0

    print(f"렌더링 중: {output} (1시간 영상은 PC에 따라 10~30분 걸립니다)")
    subprocess.run(build_ffmpeg_cmd(cfg, total, output), check=True)
    print(f"완료: {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
