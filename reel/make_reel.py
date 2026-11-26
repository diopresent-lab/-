#!/usr/bin/env python3
"""설정 파일(JSON)로 인스타그램 릴스용 1080x1920 MP4를 만든다.

첫 3초 훅 문구, 곡 정보, 자막, 마지막 CTA를 설정 파일에 적으면
같은 디자인으로 매번 릴스를 뽑을 수 있다. 의존성은 Pillow와 ffmpeg뿐이다.

    python3 reel/make_reel.py reel/configs/example.json
    python3 reel/make_reel.py reel/configs/example.json -o out.mp4
    python3 reel/make_reel.py reel/configs/example.json --preview 0,3.5,12
    python3 reel/make_reel.py reel/configs/example.json --check
"""
import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

DEFAULTS = {
    "fps": 30,
    "duration": 15.0,
    "size": [1080, 1920],
    "theme": {
        "background": "#121212",
        "text": "#F5F5F0",
        "accent": "#C6F432",
        "muted": "#9A9A9A",
        "font_regular": None,
        "font_bold": None,
    },
    "tag": "",
    "visual": "equalizer",
}

HOOK_MAX_END = 3.0
FONT_CANDIDATES = {
    "bold": [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "C:/Windows/Fonts/malgunbd.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    ],
    "regular": [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "C:/Windows/Fonts/malgun.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    ],
}
# Noto Sans CJK .ttc 안에서 KR 글꼴의 인덱스
TTC_KR_INDEX = {"NotoSansCJK": 1}


class ConfigError(Exception):
    pass


# ---------------------------------------------------------------- 설정

def merge(base, extra):
    out = dict(base)
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path):
    with open(path, encoding="utf-8") as f:
        cfg = merge(DEFAULTS, json.load(f))
    errors, warnings = validate(cfg)
    if errors:
        raise ConfigError("\n".join("  - " + e for e in errors))
    for w in warnings:
        print("경고:", w, file=sys.stderr)
    return cfg


def validate(cfg):
    errors, warnings = [], []
    dur = float(cfg["duration"])
    if list(cfg["size"]) != [1080, 1920]:
        warnings.append(f"size가 {cfg['size']}입니다. 릴스 권장 크기는 1080x1920입니다.")

    hook = cfg.get("hook")
    if not hook or not hook.get("text"):
        errors.append("hook.text(첫 3초 훅 문구)가 필요합니다.")
    else:
        end = float(hook.get("end", HOOK_MAX_END))
        if end > HOOK_MAX_END:
            errors.append(f"hook.end={end}초. 훅은 첫 {HOOK_MAX_END:g}초 안에 끝나야 합니다.")
        if end <= 0.5:
            errors.append("hook.end가 너무 짧습니다 (0.5초 초과).")

    song = cfg.get("song") or {}
    if not song.get("title"):
        errors.append("song.title(곡 제목)이 필요합니다.")
    audio = song.get("audio")
    if audio and not os.path.isfile(audio):
        errors.append(f"song.audio 파일이 없습니다: {audio}")

    prev_end = float(hook.get("end", HOOK_MAX_END)) if hook else 0.0
    for i, s in enumerate(cfg.get("subtitles", [])):
        tag = f"subtitles[{i}]"
        if not s.get("text"):
            errors.append(f"{tag}.text가 비었습니다.")
            continue
        a, b = float(s.get("start", -1)), float(s.get("end", -1))
        if not 0 <= a < b <= dur:
            errors.append(f"{tag}: start {a} / end {b}가 0~{dur:g}초 범위를 벗어나거나 순서가 틀렸습니다.")
        if a < prev_end - 1e-6:
            errors.append(f"{tag}: start {a}초가 앞 구간(끝 {prev_end:g}초)과 겹칩니다.")
        prev_end = max(prev_end, b)
        chars = len(strip_markup(s["text"]).replace("\n", ""))
        if b > a and chars / (b - a) > 9:
            warnings.append(f"{tag}: {chars}자를 {b - a:.1f}초에 보여줍니다. 읽기엔 빠를 수 있습니다.")

    cta = cfg.get("cta")
    if cta:
        a = float(cta.get("start", dur))
        if a < prev_end - 1e-6:
            errors.append(f"cta.start {a}초가 마지막 자막(끝 {prev_end:g}초)과 겹칩니다.")
        if a >= dur:
            errors.append("cta.start가 영상 길이보다 깁니다.")
    bg = cfg.get("background")
    if bg:
        src = bg.get("image") or bg.get("video")
        if not src or (bg.get("image") and bg.get("video")):
            errors.append("background 에는 image 또는 video 중 하나만 적습니다.")
        elif not os.path.isfile(src):
            errors.append(f"background 파일이 없습니다: {src}")
        if not 0 <= float(bg.get("dim", 0.45)) < 1:
            errors.append("background.dim 은 0 이상 1 미만입니다.")
    if cfg.get("visual") not in ("equalizer", "none"):
        errors.append("visual은 'equalizer' 또는 'none'입니다.")
    return errors, warnings


# ---------------------------------------------------------------- 글꼴·텍스트

def find_font(kind, override):
    paths = [override] if override else FONT_CANDIDATES[kind]
    for p in paths:
        if p and os.path.isfile(p):
            return p
    if override:
        raise ConfigError(f"글꼴 파일이 없습니다: {override}")
    raise ConfigError("한글 글꼴을 찾지 못했습니다. theme.font_bold / theme.font_regular에 경로를 적어주세요.")


class Fonts:
    def __init__(self, theme):
        self.paths = {"bold": find_font("bold", theme.get("font_bold")),
                      "regular": find_font("regular", theme.get("font_regular"))}
        self.cache = {}

    def get(self, kind, size):
        key = (kind, size)
        if key not in self.cache:
            path = self.paths[kind]
            index = next((i for k, i in TTC_KR_INDEX.items() if k in os.path.basename(path)), 0)
            self.cache[key] = ImageFont.truetype(path, size, index=index if path.endswith(".ttc") else 0)
        return self.cache[key]


MARK = re.compile(r"\[([^\]]+)\]")


def strip_markup(text):
    return MARK.sub(r"\1", text)


def parse_runs(line):
    """'[도면]을 그리고' -> [('도면', True), ('을 그리고', False)]"""
    runs, pos = [], 0
    for m in MARK.finditer(line):
        if m.start() > pos:
            runs.append((line[pos:m.start()], False))
        runs.append((m.group(1), True))
        pos = m.end()
    if pos < len(line):
        runs.append((line[pos:], False))
    return runs


def wrap_line(line, font, max_w):
    """단어(공백) 단위로 줄바꿈한다. 한국어 어절이 쪼개지지 않게 한다."""
    words = line.split(" ")
    lines, cur = [], ""
    for w in words:
        cand = (cur + " " + w).strip()
        if cur and font.getlength(strip_markup(cand)) > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = cand
    if cur:
        lines.append(cur)
    return fix_open_brackets(lines)


def fix_open_brackets(lines):
    """강조 [ ]가 줄바꿈으로 갈라지면 각 줄에서 다시 닫고 연다."""
    out, carry = [], False
    for ln in lines:
        if carry:
            ln = "[" + ln
        carry = ln.count("[") > ln.count("]")
        out.append(ln + "]" if carry else ln)
    return out


def text_block(draw, fonts, text, size, kind, y_center, colors, W, alpha, dy=0,
               line_gap=1.25, max_w=920):
    font = fonts.get(kind, size)
    lines = []
    for raw in text.split("\n"):
        lines += wrap_line(raw, font, max_w) if raw else [""]
    lh = int(size * line_gap)
    top = y_center - lh * len(lines) / 2 + dy
    for i, ln in enumerate(lines):
        runs = parse_runs(ln)
        width = sum(font.getlength(t) for t, _ in runs)
        x = (W - width) / 2
        y = top + i * lh
        for t, acc in runs:
            draw.text((x, y), t, font=font, fill=rgba(colors["accent" if acc else "text"], alpha))
            x += font.getlength(t)
    return top + lh * len(lines)


# ---------------------------------------------------------------- 그리기

def rgba(hex_color, alpha=1.0):
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return (r, g, b, int(255 * max(0.0, min(1.0, alpha))))


def ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def envelope(t, a, b, fade_in=0.35, fade_out=0.3, hold_end=False, instant=False):
    """구간 [a, b) 안에서 투명도와 위로 떠오르는 오프셋을 돌려준다."""
    if t < a or (t >= b and not hold_end):
        return 0.0, 0.0
    k_in = 1.0 if instant else ease((t - a) / fade_in)
    k_out = 1.0 if hold_end else ease((b - t) / fade_out)
    return min(k_in, k_out), (1 - k_in) * 40


def draw_equalizer(draw, t, theme, W, base_y=1560):
    """건축 도면 그리드가 이퀄라이저 막대로 바뀌는 배경."""
    acc = rgba(theme["accent"])
    x0, x1, y0 = 140, 940, base_y - 480
    if t < 5.2:
        k = 1.0 if t < 4 else max(0.0, 1 - (t - 4) / 1.2)
        p = min(1.0, t / 1.6)
        col = rgba("#6E6E6E", k)
        for i in range(9):
            x = x0 + (x1 - x0) * i / 8
            draw.line([(x, base_y), (x, base_y - (base_y - y0) * p)], fill=col, width=3)
        for j in range(5):
            y = base_y - (base_y - y0) * j / 4
            w = (x1 - x0) * ease(p * 5 - j)
            if w > 0:
                draw.line([(x0, y), (x0 + w, y)], fill=col, width=3)
    if t >= 3.5:
        m = ease((t - 3.5) / 1.2)
        for i in range(16):
            x = x0 + i * 50 + 10
            h = (60 + 220 * abs(math.sin(t * 3.1 + i * 0.9)) * abs(math.sin(i * 1.7 + 1))) * m
            fill = rgba(theme["accent"]) if i % 4 == 1 else rgba("#5A5A5A")
            draw.rectangle([x, base_y - h, x + 30, base_y], fill=fill)
    draw.line([(80, base_y), (W - 80, base_y)], fill=acc, width=5)


def draw_note(draw, x, y, color, s=1.0):
    """♪ 모양을 직접 그린다 (글꼴에 기호가 없어도 깨지지 않게)."""
    r = 11 * s
    draw.ellipse([x, y + 30 * s, x + 2 * r + 4, y + 30 * s + 2 * r], fill=color)
    sx = x + 2 * r + 1
    draw.rectangle([sx, y, sx + 5 * s, y + 30 * s + r], fill=color)
    draw.polygon([(sx, y), (sx + 22 * s, y + 10 * s), (sx + 22 * s, y + 20 * s), (sx, y + 10 * s)], fill=color)


def draw_song(draw, fonts, song, theme, W, y, alpha):
    if alpha <= 0:
        return
    title_font = fonts.get("bold", 38)
    artist_font = fonts.get("regular", 32)
    title = song["title"]
    artist = song.get("artist", "")
    sep = "  ·  " if artist else ""
    tw = title_font.getlength(title)
    aw = artist_font.getlength(sep + artist)
    icon_w = 58
    pad_x, h = 40, 84
    total = icon_w + tw + aw + pad_x * 2
    x = (W - total) / 2
    draw.rounded_rectangle([x, y, x + total, y + h], radius=h / 2, fill=rgba("#FFFFFF", 0.08 * alpha),
                           outline=rgba(theme["muted"], 0.5 * alpha), width=2)
    draw_note(draw, x + pad_x, y + 16, rgba(theme["accent"], alpha), 0.9)
    tx = x + pad_x + icon_w
    draw.text((tx, y + h / 2), title, font=title_font, fill=rgba(theme["text"], alpha), anchor="lm")
    draw.text((tx + tw, y + h / 2), sep + artist, font=artist_font, fill=rgba(theme["muted"], alpha), anchor="lm")


def render_frame(cfg, fonts, t):
    W, H = cfg["size"]
    th = cfg["theme"]
    # 배경 사진/영상이 있으면 글자 층만 투명하게 그리고 배경은 ffmpeg 에서 합성한다.
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0) if cfg.get("background") else rgba(th["background"]))
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    dur = float(cfg["duration"])

    if cfg["visual"] == "equalizer":
        draw_equalizer(d, t, th, W)

    if cfg.get("tag"):
        d.text((W / 2, 270), cfg["tag"], font=fonts.get("bold", 30), fill=rgba(th["muted"]), anchor="mm")

    # 1) 훅: 첫 프레임부터 바로 보인다 (빈 화면 0초)
    hook = cfg["hook"]
    a, dy = envelope(t, 0, float(hook.get("end", HOOK_MAX_END)), instant=True)
    if a > 0:
        text_block(d, fonts, hook["text"], int(hook.get("size", 104)), "bold", 700, th, W, a, dy, 1.18)

    # 2) 자막
    for s in cfg.get("subtitles", []):
        a, dy = envelope(t, float(s["start"]), float(s["end"]))
        if a > 0:
            text_block(d, fonts, s["text"], int(s.get("size", 76)), "bold", 700, th, W, a, dy,
                       float(s.get("line_gap", 1.35)))

    # 3) CTA (끝까지 유지)
    cta = cfg.get("cta")
    if cta:
        a, dy = envelope(t, float(cta["start"]), dur, hold_end=True)
        if a > 0:
            y = text_block(d, fonts, cta["title"], int(cta.get("size", 96)), "bold", 640, th, W, a, dy, 1.18)
            if cta.get("text"):
                y = text_block(d, fonts, cta["text"], 64, "bold", y + 90, th, W, a, dy, 1.3)
            if cta.get("sub"):
                text_block(d, fonts, cta["sub"], 40, "regular", y + 70, {**th, "text": "#B8B8B8"}, W, a, dy)

    # 4) 곡 정보 배지
    song = cfg["song"]
    show_from = float(song.get("show_from", 0))
    sa = 1.0 if show_from <= 0 else ease((t - show_from) / 0.4)
    if t >= show_from:
        draw_song(d, fonts, song, th, W, int(song.get("y", 1660)), sa)

    img.alpha_composite(layer)
    return img if cfg.get("background") else img.convert("RGB")


def background_input(cfg):
    """배경 사진/영상의 ffmpeg 입력 인자와 필터(1080x1920 채우기 + 어둡게)를 돌려준다."""
    bg = cfg["background"]
    W, H = cfg["size"]
    fps, dur = int(cfg["fps"]), float(cfg["duration"])
    dim = float(bg.get("dim", 0.45))
    fill = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1"
    if bg.get("video"):
        args = ["-stream_loop", "-1", "-t", str(dur), "-i", bg["video"]]
        chain = f"{fill},fps={fps}"
    else:
        # 사진: 천천히 확대(켄 번즈). 2배로 키운 뒤 zoompan 해서 떨림을 줄인다.
        n = int(round(fps * dur))
        zoom = float(bg.get("zoom", 1.08))
        args = ["-loop", "1", "-framerate", str(fps), "-t", str(dur), "-i", bg["image"]]
        chain = (f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
                 f"zoompan=z='1+{zoom - 1:.4f}*on/{n}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                 f":d=1:s={W}x{H}:fps={fps},setsar=1")
    if dim > 0:
        chain += f",drawbox=x=0:y=0:w=iw:h=ih:color=black@{dim:.2f}:t=fill"
    return args, chain


# ---------------------------------------------------------------- 출력

def need_ffmpeg():
    exe = shutil.which("ffmpeg")
    if not exe:
        raise ConfigError("ffmpeg가 필요합니다. (macOS: brew install ffmpeg)")
    return exe


def encode(cfg, fonts, out):
    ffmpeg = need_ffmpeg()
    W, H = cfg["size"]
    fps, dur = int(cfg["fps"]), float(cfg["duration"])
    song = cfg["song"]
    has_bg = bool(cfg.get("background"))
    cmd = [ffmpeg, "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgba" if has_bg else "rgb24", "-s", f"{W}x{H}", "-r", str(fps),
           "-i", "-"]
    vmap, n_in = "0:v", 1
    if has_bg:
        bg_args, chain = background_input(cfg)
        cmd += bg_args
        cmd += ["-filter_complex", f"[1:v]{chain}[bg];[bg][0:v]overlay=format=auto:shortest=1,format=yuv420p[v]"]
        vmap, n_in = "[v]", 2
    if song.get("audio"):
        cmd += ["-ss", str(song.get("audio_start", 0)), "-t", str(dur), "-i", song["audio"]]
        fade_at = max(0.0, dur - 1.0)
        cmd += ["-map", vmap, "-map", f"{n_in}:a", "-af", f"afade=t=out:st={fade_at}:d=1",
                "-c:a", "aac", "-b:a", "192k", "-shortest"]
    elif cfg.get("silent_audio_track"):
        cmd += ["-f", "lavfi", "-t", str(dur), "-i", "anullsrc=r=44100:cl=stereo",
                "-map", vmap, "-map", f"{n_in}:a", "-c:a", "aac", "-shortest"]
    elif has_bg:
        cmd += ["-map", vmap]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "medium",
            "-movflags", "+faststart", out]
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    n = int(round(fps * dur))
    for i in range(n):
        proc.stdin.write(render_frame(cfg, fonts, i / fps).tobytes())
        if i % fps == 0:
            print(f"\r렌더링 {i / fps:4.1f}s / {dur:g}s", end="", file=sys.stderr)
    proc.stdin.close()
    if proc.wait() != 0:
        raise ConfigError("ffmpeg 인코딩에 실패했습니다.")
    print(f"\r완료: {out} ({W}x{H}, {dur:g}s, {fps}fps)", file=sys.stderr)


def preview_with_background(cfg, frame, t):
    """미리보기 PNG 에 배경(해당 시점 프레임)을 깔아 준다."""
    ffmpeg = need_ffmpeg()
    W, H = cfg["size"]
    bg_args, chain = background_input(cfg)
    proc = subprocess.run([ffmpeg, "-loglevel", "error", *bg_args, "-vf", chain, "-ss", f"{t:.2f}",
                           "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgba", "-"],
                          capture_output=True)
    if proc.returncode != 0 or len(proc.stdout) < W * H * 4:
        raise ConfigError("배경 미리보기 생성에 실패했습니다.")
    base = Image.frombytes("RGBA", (W, H), proc.stdout[:W * H * 4])
    base.alpha_composite(frame)
    return base.convert("RGB")


def main(argv=None):
    ap = argparse.ArgumentParser(description="설정 파일로 1080x1920 릴스 MP4 만들기")
    ap.add_argument("config", help="JSON 설정 파일")
    ap.add_argument("-o", "--output", help="출력 MP4 경로 (기본: 설정의 output)")
    ap.add_argument("--preview", help="이 시점(초)들의 PNG만 저장. 예: 0,3.5,12")
    ap.add_argument("--check", action="store_true", help="설정만 검사하고 끝낸다")
    args = ap.parse_args(argv)
    try:
        cfg = load_config(args.config)
        if args.check:
            print("설정 OK")
            return 0
        fonts = Fonts(cfg["theme"])
        out = args.output or cfg.get("output") or os.path.splitext(args.config)[0] + ".mp4"
        if args.preview:
            base = os.path.splitext(out)[0]
            os.makedirs(os.path.dirname(os.path.abspath(base)), exist_ok=True)
            for s in args.preview.split(","):
                p = f"{base}_preview_{float(s):05.2f}s.png"
                frame = render_frame(cfg, fonts, float(s))
                if cfg.get("background"):
                    frame = preview_with_background(cfg, frame, float(s))
                frame.save(p)
                print("미리보기:", p)
            return 0
        encode(cfg, fonts, out)
        return 0
    except ConfigError as e:
        print("설정 오류:\n" + str(e), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
