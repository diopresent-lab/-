#!/usr/bin/env python3
"""사진 여러 장 + 가사 자막 릴스 (1080x1920).

사진이 한 마디마다 바뀌고, 가사 한 줄이 두 마디씩 뜬다.
가을 사진에서 시작해 점점 차갑게 보정되고, 끝에서 첫눈이 내린다.

    python3 reel/photo_lyric_reel.py --audio song.mp3 --audio-start 53.49 \
        --photos a.jpg b.jpg ... -o out.mp4
    python3 reel/photo_lyric_reel.py ... --preview 1,6,12,19
"""
import argparse
import os
import sys

from PIL import Image, ImageEnhance, ImageOps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from first_snow_reel import (  # noqa: E402
    SANS_R, SERIF_B, SERIF_R, W, H, FPS,
    draw_snow, ease, encode, make_flakes, text_card, youtube_button,
)
import first_snow_reel as base  # noqa: E402

BAR = 60 / 90.7 * 4          # 약 2.65초
LINES = [                    # (가사, 시작 마디, 끝 마디)
    (["첫눈이 오기 전에"], 0, 2),
    (["너를 여기서 보내 줄게"], 2, 4),
    (["붙잡고 있던", "마지막 온기까지"], 4, 6),
    (["내 손으로 가만히", "놓아 줄게"], 6, 7.4),
]
END_BAR = 7.4
DUR = BAR * 8.6              # 약 22.8초
XFADE = 0.35                 # 사진 전환 시간(초)


def grade(im, k):
    """k=0 따뜻한 원본 → k=1 차갑고 어두운 겨울 톤."""
    im = ImageEnhance.Color(im).enhance(1.0 - 0.5 * k)
    im = ImageEnhance.Brightness(im).enhance(0.95 - 0.25 * k)
    cool = Image.new("RGB", im.size, (110, 135, 180))
    return Image.blend(im, cool, 0.05 + 0.18 * k)


class Reel:
    def __init__(self, photos):
        n = len(photos)
        self.photos = []
        for i, p in enumerate(photos):
            im = ImageOps.exif_transpose(Image.open(p)).convert("RGB")
            im = ImageOps.fit(im, (int(W * 1.08), int(H * 1.08)), Image.LANCZOS)
            self.photos.append(grade(im, i / max(1, n - 1)).convert("RGBA"))
        self.cards = [(text_card(l, 68 if len(l) == 1 else 62, SERIF_R), a * BAR, b * BAR)
                      for l, a, b in LINES]
        self.tag = text_card(["Soulful Girl  ·  첫눈이 오기 전에"], 30, SANS_R, tracking=0.08)
        self.end_title = text_card(["첫눈이 오기 전에"], 92, SERIF_B)
        self.end_artist = text_card(["Soulful Girl"], 44, SERIF_R, tracking=0.12)
        self.end_cta = youtube_button("YouTube에서 전곡 듣기")
        self.end_sub = text_card(["싱글 「첫눈이 오기 전에」  ·  @Soulfulgirl_dio"], 32, SANS_R, tracking=0.02)
        self.flakes = make_flakes()
        # 눈은 6번째 사진(앙상한 나무)부터
        for f in self.flakes:
            f["born"] = f["born"] - 9.0 + BAR * 5.3

    def photo_at(self, i, t_in):
        im = self.photos[i]
        z = 1.0 + 0.06 * ease(t_in / (BAR + XFADE))
        bw, bh = im.size
        cw, ch = bw / z, bh / z
        x0, y0 = (bw - cw) / 2, (bh - ch) / 2
        return im.resize((W, H), Image.BILINEAR, box=(x0, y0, x0 + cw, y0 + ch))

    def frame(self, t):
        n = len(self.photos)
        idx = min(int(t // BAR), n - 1)
        img = self.photo_at(idx, t - idx * BAR)
        nxt = idx + 1
        if nxt < n and t > nxt * BAR - XFADE:
            k = ease((t - (nxt * BAR - XFADE)) / XFADE)
            img = Image.blend(img, self.photo_at(nxt, 0), k)
        # 아래쪽 어둡게 (자막 가독성)
        shade = Image.linear_gradient("L").resize((W, H)).point(lambda v: int(v * 0.55))
        img = Image.composite(Image.new("RGBA", (W, H), (6, 10, 20, 255)), img, shade)

        paste = base.Reel.paste
        paste(img, self.tag, 230, 0.85)
        for card, a, b in self.cards:
            if a <= t < b:
                k_in = 1.0 if a == 0 else ease((t - a) / 0.5)
                k_out = ease((b - t) / 0.4)
                paste(img, card, 1240 + (1 - k_in) * 24, min(k_in, k_out))

        img.alpha_composite(draw_snow(t, self.flakes))

        te = END_BAR * BAR
        if t >= te:
            k = ease((t - te) / 0.8)
            img = Image.blend(img, Image.new("RGBA", (W, H), (8, 12, 22, 255)), 0.35 * k)
            paste(img, self.end_title, 760 + (1 - k) * 24, k)
            paste(img, self.end_artist, 890 + (1 - k) * 24, k)
            k2 = ease((t - te - 0.5) / 0.8)
            paste(img, self.end_cta, 1540, k2)
            paste(img, self.end_sub, 1660, k2 * 0.9)
        if t > DUR - 0.4:
            img = Image.blend(img, Image.new("RGBA", (W, H), (0, 0, 0, 255)),
                              ease((t - (DUR - 0.4)) / 0.4) * 0.5)
        return img.convert("RGB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--photos", nargs="+", required=True)
    ap.add_argument("--audio")
    ap.add_argument("--audio-start", type=float, default=0.0)
    ap.add_argument("-o", "--output", default="reels_out/photo_lyric.mp4")
    ap.add_argument("--preview")
    a = ap.parse_args()
    reel = Reel(a.photos)
    if a.preview:
        base_name = os.path.splitext(a.output)[0]
        os.makedirs(os.path.dirname(os.path.abspath(base_name)), exist_ok=True)
        for s in a.preview.split(","):
            path = f"{base_name}_{float(s):05.2f}s.png"
            reel.frame(float(s)).save(path)
            print(path)
        return
    base.DUR = DUR
    encode(reel, a.output, a.audio, a.audio_start)


if __name__ == "__main__":
    main()
