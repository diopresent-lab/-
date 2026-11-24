#!/usr/bin/env python3
"""Soulful Girl 「첫눈이 오기 전에」 릴스 (1080x1920, 18.5초).

사진 한 장을 배경으로 천천히 앞으로 다가가는(push-in) 화면 위에
가사/문구 카드가 차례로 뜨고, 후반부에 첫눈이 내리기 시작한다.

    python3 reel/first_snow_reel.py PHOTO.jpg -o out.mp4 [--audio song.mp3 --audio-start 53.49]
    python3 reel/first_snow_reel.py PHOTO.jpg --preview 0,4,8,12,14.5
"""
import argparse
import math
import os
import random
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

W, H, FPS, DUR = 1080, 1920, 30, 18.5
SERIF_B = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"
SERIF_R = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"
SANS_R = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
SANS_B = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
KR = 1  # Noto CJK .ttc 안의 KR 인덱스

# (시작, 끝, 줄 목록, 글자 크기, 글꼴, 중심 y)
# 가사: 1절 후렴. 음원을 넣을 땐 후렴 첫 줄이 0초에 오도록 --audio-start를 맞춘다.
BAR = 60 / 90.7 * 4  # 약 2.65초 (91 BPM, 4/4)
PH = BAR * 2          # 가사 한 줄 = 2마디
CARDS = [
    (0.0, PH, ["첫눈이 오기 전에"], 104, SERIF_B, 640),
    (PH, PH * 2, ["너를 여기서", "보내 줄게"], 72, SERIF_R, 640),
    (PH * 2, PH * 3, ["붙잡고 있던 마지막 온기까지", "내 손으로 가만히 놓아 줄게"], 60, SERIF_R, 640),
]
END_START = PH * 3  # 이후 엔딩 카드 고정


def font(path, size):
    return ImageFont.truetype(path, size, index=KR)


def ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def text_card(lines, size, path, tracking=0.04, gap=1.45, shadow=True):
    """여러 줄 텍스트를 부드러운 그림자와 함께 RGBA 이미지로 미리 그린다."""
    f = font(path, size)
    sp = size * tracking
    widths = [sum(f.getlength(c) for c in ln) + sp * (len(ln) - 1) for ln in lines]
    lh = int(size * gap)
    pad = 60
    cw, ch = int(max(widths)) + pad * 2, lh * len(lines) + pad * 2
    txt = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    d = ImageDraw.Draw(txt)
    for i, ln in enumerate(lines):
        x = (cw - widths[i]) / 2
        y = pad + i * lh
        for c in ln:
            d.text((x, y), c, font=f, fill=(250, 251, 255, 255))
            x += f.getlength(c) + sp
    if not shadow:
        return txt
    a = txt.split()[3]
    sh = Image.new("RGBA", txt.size, (10, 18, 32, 0))
    sh.putalpha(a.filter(ImageFilter.GaussianBlur(14)).point(lambda v: int(v * 0.75)))
    out = Image.new("RGBA", txt.size, (0, 0, 0, 0))
    out.alpha_composite(sh, (0, 6))
    out.alpha_composite(txt)
    return out


def youtube_button(label):
    """빨간 재생 아이콘 + 문구가 들어간 알약 모양 버튼 (유튜브 유입용 CTA)."""
    f = font(SANS_B, 44)
    tw = f.getlength(label)
    icon_w, pad, h = 76, 40, 108
    w = int(pad + icon_w + 22 + tw + pad)
    img = Image.new("RGBA", (w + 40, h + 40), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([20, 26, 20 + w, 26 + h], radius=h / 2, fill=(0, 0, 0, 90))  # 그림자
    img = img.filter(ImageFilter.GaussianBlur(8))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([20, 20, 20 + w, 20 + h], radius=h / 2, fill=(255, 255, 255, 240))
    ix, iy = 20 + pad, 20 + (h - 54) / 2
    d.rounded_rectangle([ix, iy, ix + icon_w, iy + 54], radius=14, fill=(255, 0, 0, 255))
    cx, cy = ix + icon_w / 2 + 3, iy + 27
    d.polygon([(cx - 11, cy - 14), (cx - 11, cy + 14), (cx + 14, cy)], fill=(255, 255, 255, 255))
    d.text((ix + icon_w + 22, 20 + h / 2), label, font=f, fill=(20, 20, 24, 255), anchor="lm")
    return img


def load_background(photo):
    """사진을 세로 9:16로 자르고 Soulful Girl 톤(차가운 저채도)으로 보정한다."""
    im = ImageOps.exif_transpose(Image.open(photo)).convert("RGB")
    bw, bh = int(W * 1.12), int(H * 1.12)
    im = ImageOps.fit(im, (bw, bh), Image.LANCZOS, centering=(0.5, 0.45))
    im = ImageEnhance.Color(im).enhance(0.5)
    im = ImageEnhance.Brightness(im).enhance(0.86)
    im = ImageEnhance.Contrast(im).enhance(0.92)
    cool = Image.new("RGB", im.size, (120, 145, 185))
    im = Image.blend(im, cool, 0.16)
    # 비네트 + 아래쪽 어둡게 (자막 가독성)
    mask = Image.new("L", im.size, 0)
    md = ImageDraw.Draw(mask)
    for i in range(60):
        k = i / 60
        md.rectangle([k * bw * 0.35, k * bh * 0.30, bw - k * bw * 0.35, bh - k * bh * 0.30],
                     fill=int(255 * (1 - k) ** 2 * 0.55))
    mask = mask.filter(ImageFilter.GaussianBlur(80))
    im = Image.composite(Image.new("RGB", im.size, (8, 12, 22)), im, mask)
    return im


def make_flakes(n=170, seed=7):
    rnd = random.Random(seed)
    flakes = []
    for _ in range(n):
        flakes.append({
            "x": rnd.uniform(-40, W + 40),
            "y0": rnd.uniform(-120, H * 0.75),
            "speed": rnd.uniform(110, 240),
            "r": rnd.choice([2, 2, 3, 3, 4, 5, 7]),
            "sway": rnd.uniform(14, 40),
            "freq": rnd.uniform(0.6, 1.4),
            "phase": rnd.uniform(0, 6.28),
            "born": rnd.uniform(9.8, 17.0),  # 둘째 줄 끝무렵부터 첫눈이 하나둘
        })
    # 맨 처음 한 송이: 9.0초 화면 중앙 근처
    flakes.append({"x": W * 0.56, "y0": 380, "speed": 150, "r": 6, "sway": 22,
                   "freq": 0.8, "phase": 0, "born": 9.2})
    return flakes


def draw_snow(t, flakes):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for f in flakes:
        if t < f["born"]:
            continue
        age = t - f["born"]
        y = f["y0"] + age * f["speed"]
        if y > H + 20:
            continue
        x = f["x"] + math.sin(age * f["freq"] + f["phase"]) * f["sway"]
        a = int(235 * ease(age / 0.8))
        r = f["r"]
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, a))
    return layer.filter(ImageFilter.GaussianBlur(1.3))


class Reel:
    def __init__(self, photo):
        self.bg = load_background(photo)
        self.cards = [(a, b, text_card(lines, size, path), y) for a, b, lines, size, path, y in CARDS]
        self.end_title = text_card(["첫눈이 오기 전에"], 96, SERIF_B)
        self.end_artist = text_card(["Soulful Girl"], 46, SERIF_R, tracking=0.12)
        self.end_cta = youtube_button("YouTube에서 전곡 듣기")
        self.end_handle = text_card(["YouTube  @diopresent  ·  '첫눈이 오기 전에' 검색"], 32, SANS_R, tracking=0.02)
        self.tag = text_card(["Soulful Girl  ·  눈 시리즈"], 30, SANS_R, tracking=0.1)
        self.flakes = make_flakes()

    def frame(self, t):
        # 1) 배경: 천천히 앞으로 다가감 (운전하며 다리로 향하는 느낌)
        z = 1.0 + 0.10 * ease(t / DUR)
        bw, bh = self.bg.size
        cw, ch = bw / z, bh / z
        cx = bw / 2
        cy = min(max(bh * 0.52, ch / 2), bh - ch / 2)
        box = (cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2)
        img = self.bg.resize((W, H), Image.BILINEAR, box=box).convert("RGBA")
        # 후반부: 눈이 오면서 아주 조금 더 차갑고 어두워짐
        if t > 9.8:
            k = ease((t - 9.8) / 3.0) * 0.22
            img = Image.blend(img, Image.new("RGBA", (W, H), (30, 42, 66, 255)), k)

        # 2) 상단 태그 (계정 톤 유지)
        self.paste(img, self.tag, 250, 0.85)

        # 3) 문구 카드: 0초부터 제목이 바로 보인다
        for a, b, card, y in self.cards:
            if a <= t < b:
                k_in = 1.0 if a == 0 else ease((t - a) / 0.6)
                k_out = ease((b - t) / 0.45)
                self.paste(img, card, y + (1 - k_in) * 30, min(k_in, k_out))

        # 4) 첫눈
        img.alpha_composite(draw_snow(t, self.flakes))

        # 5) 엔딩 카드
        if t >= END_START:
            k = ease((t - END_START) / 0.8)
            self.paste(img, self.end_title, 760 + (1 - k) * 30, k)
            self.paste(img, self.end_artist, 900 + (1 - k) * 30, k * 0.95)
            k2 = ease((t - END_START - 0.5) / 0.8)
            self.paste(img, self.end_cta, 1560 + (1 - k2) * 20, k2)
            self.paste(img, self.end_handle, 1680, k2 * 0.9)

        # 6) 마지막 0.4초는 살짝 어둡게 닫기 (반복 재생 시 자연스럽게)
        if t > DUR - 0.4:
            img = Image.blend(img, Image.new("RGBA", (W, H), (0, 0, 0, 255)),
                              ease((t - (DUR - 0.4)) / 0.4) * 0.5)
        return img.convert("RGB")

    @staticmethod
    def paste(img, card, y_center, alpha):
        if alpha <= 0.01:
            return
        c = card
        if alpha < 0.999:
            c = card.copy()
            c.putalpha(card.split()[3].point(lambda v: int(v * alpha)))
        img.alpha_composite(c, (int((W - c.width) / 2), int(y_center - c.height / 2)))


def encode(reel, out, audio=None, audio_start=0.0):
    ffmpeg = shutil.which("ffmpeg") or sys.exit("ffmpeg가 필요합니다.")
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-"]
    if audio:
        cmd += ["-ss", str(audio_start), "-t", str(DUR), "-i", audio, "-map", "0:v", "-map", "1:a",
                "-af", f"afade=t=in:d=0.3,afade=t=out:st={DUR - 1.2}:d=1.2",
                "-c:a", "aac", "-b:a", "192k", "-shortest"]
    else:
        cmd += ["-f", "lavfi", "-t", str(DUR), "-i", "anullsrc=r=44100:cl=stereo",
                "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-shortest"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "medium",
            "-r", str(FPS), "-movflags", "+faststart", out]
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    n = int(FPS * DUR)
    for i in range(n):
        p.stdin.write(reel.frame(i / FPS).tobytes())
        if i % FPS == 0:
            print(f"\r렌더링 {i / FPS:4.1f}s / {DUR:g}s", end="", file=sys.stderr)
    p.stdin.close()
    if p.wait():
        sys.exit("ffmpeg 인코딩 실패")
    print(f"\r완료: {out}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("photo")
    ap.add_argument("-o", "--output", default="reels_out/첫눈이오기전에.mp4")
    ap.add_argument("--audio")
    ap.add_argument("--audio-start", type=float, default=0.0)
    ap.add_argument("--preview")
    a = ap.parse_args()
    reel = Reel(a.photo)
    if a.preview:
        base = os.path.splitext(a.output)[0]
        os.makedirs(os.path.dirname(os.path.abspath(base)), exist_ok=True)
        for s in a.preview.split(","):
            path = f"{base}_{float(s):05.2f}s.png"
            reel.frame(float(s)).save(path)
            print(path)
        return
    encode(reel, a.output, a.audio, a.audio_start)


if __name__ == "__main__":
    main()
