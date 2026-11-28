#!/usr/bin/env python3
"""가을 사진 인트로 + 실제 눈 영상 메인 + 가사 자막 릴스 (1080x1920).

0 ~ 2마디: 가을 사진들이 빠르게 지나가며 첫 가사("첫눈이 오기 전에")
2마디 ~ 끝: 눈 내리는 영상을 늘려(슬로모션) 화면을 채우고 나머지 가사와 엔딩

    python3 reel/snow_video_reel.py --video snow.mp4 --photos a.jpg b.jpg ... \
        --audio song.mp3 --audio-start 53.49 -o out.mp4 [--preview 1,8,15,21]
"""
import argparse
import os
import shutil
import subprocess
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import first_snow_reel as base  # noqa: E402
import photo_lyric_reel as pl  # noqa: E402
from first_snow_reel import W, H, FPS, ease, encode  # noqa: E402

BAR = pl.BAR
INTRO = BAR * 2          # 사진 인트로 길이
DUR = pl.DUR             # 약 22.8초


class VideoFrames:
    """영상을 목표 길이로 늘려 30fps 프레임을 순서대로 꺼낸다."""

    def __init__(self, path, target_len):
        src = float(subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path]).strip())
        factor = target_len / src
        vf = (f"setpts={factor:.5f}*PTS,fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase,"
              f"crop={W}:{H},eq=saturation=0.85:brightness=-0.02")
        self.p = subprocess.Popen(
            [shutil.which("ffmpeg"), "-v", "error", "-i", path, "-an", "-vf", vf,
             "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
        self.last = Image.new("RGB", (W, H), (10, 12, 18))
        self.n = 0

    def next(self):
        buf = self.p.stdout.read(W * H * 3)
        if len(buf) == W * H * 3:
            self.last = Image.frombytes("RGB", (W, H), buf)
        self.n += 1
        return self.last


class Reel(pl.Reel):
    def __init__(self, photos, video):
        super().__init__(photos)
        self.video_path = video
        self.vf = None
        self.flakes = []                       # 진짜 눈이 있으니 그래픽 눈은 끔
        self.step = INTRO / len(self.photos)   # 사진 한 장당 시간

    def photo_frame(self, t):
        n = len(self.photos)
        idx = min(int(t // self.step), n - 1)
        im = self.photos[idx]
        z = 1.0 + 0.05 * ease((t - idx * self.step) / self.step)
        bw, bh = im.size
        cw, ch = bw / z, bh / z
        x0, y0 = (bw - cw) / 2, (bh - ch) / 2
        return im.resize((W, H), Image.BILINEAR, box=(x0, y0, x0 + cw, y0 + ch))

    def background(self, t):
        if self.vf is None:
            self.vf = VideoFrames(self.video_path, DUR - INTRO + 0.5)
        if t < INTRO - 0.4:
            return self.photo_frame(t)
        v = self.vf.next().convert("RGBA")
        if t < INTRO:                          # 사진 → 눈 영상 디졸브
            return Image.blend(self.photo_frame(t), v, ease((t - (INTRO - 0.4)) / 0.4))
        return v

    def frame(self, t):
        # 배경만 바꾸고 자막·엔딩은 photo_lyric_reel 그대로 쓴다
        self._bg = self.background(t)
        return super().frame(t)

    def photo_at(self, i, t_in):
        # 부모 frame()이 사진 자리에 부르는 훅: 이번 프레임의 배경을 돌려준다
        # (부모의 사진 전환 블렌딩은 같은 이미지끼리 섞이므로 결과에 영향 없음)
        return self._bg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--photos", nargs="+", required=True)
    ap.add_argument("--audio")
    ap.add_argument("--audio-start", type=float, default=0.0)
    ap.add_argument("-o", "--output", default="reels_out/snow_video.mp4")
    ap.add_argument("--preview")
    a = ap.parse_args()
    reel = Reel(a.photos, a.video)
    base.DUR = DUR
    if a.preview:
        times = sorted(float(s) for s in a.preview.split(","))
        base_name = os.path.splitext(a.output)[0]
        os.makedirs(os.path.dirname(os.path.abspath(base_name)), exist_ok=True)
        i = 0
        for k in range(int(FPS * DUR)):
            t = k / FPS
            img = reel.frame(t)
            if i < len(times) and t >= times[i]:
                img.save(f"{base_name}_{times[i]:05.2f}s.png")
                print(f"{base_name}_{times[i]:05.2f}s.png")
                i += 1
                if i == len(times):
                    break
        return
    encode(reel, a.output, a.audio, a.audio_start)


if __name__ == "__main__":
    main()
