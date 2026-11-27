import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "playlist"))

import make_playlist_video as mpv  # noqa: E402

CONFIG = os.path.join(ROOT, "playlist", "configs", "soulful_girl_winter.json")
TRACKS = [{"artist": "A", "title": f"곡{i}"} for i in range(3)]


class FormatTest(unittest.TestCase):
    def test_format_ts(self):
        self.assertEqual(mpv.format_ts(0, False), "00:00")
        self.assertEqual(mpv.format_ts(754.9, False), "12:34")
        self.assertEqual(mpv.format_ts(3725, True), "1:02:05")

    def test_windows_path_is_normalized(self):
        p = mpv.resolve_path("E:/앨범/DistroKid 백업", "Soulful Girl\\2026-11-24 입김\\01 입김.wav")
        self.assertEqual(p, "E:/앨범/DistroKid 백업/Soulful Girl/2026-11-24 입김/01 입김.wav")
        self.assertEqual(mpv.resolve_path("E:/x", "C:\\bg.jpg"), "C:/bg.jpg")


class ChapterTest(unittest.TestCase):
    def test_chapters_include_gaps_except_after_last(self):
        chapters, total = mpv.build_chapters(TRACKS, [200, 180.5, 240], gap_seconds=2)
        self.assertEqual([c[0] for c in chapters], [0, 202, 384.5])
        self.assertAlmostEqual(total, 624.5)
        self.assertEqual(mpv.chapter_lines(chapters, total)[1], "03:22 A - 곡1")

    def test_hours_format_used_for_long_playlists(self):
        chapters, total = mpv.build_chapters(TRACKS, [1800, 1800, 60])
        self.assertEqual(mpv.chapter_lines(chapters, total)[0], "0:00:00 A - 곡0")

    def test_short_track_rejected(self):
        with self.assertRaises(mpv.ConfigError):
            mpv.build_chapters(TRACKS, [200, 5, 200])


class ConfigTest(unittest.TestCase):
    def test_bundled_config_loads(self):
        cfg = mpv.load_config(CONFIG)
        self.assertEqual(len(cfg["tracks"]), 15)
        self.assertTrue(cfg["tracks"][0]["path"].startswith("E:/앨범/DistroKid 백업/Soulful Girl/"))

    def test_too_few_tracks_rejected(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump({"background": "bg.jpg", "tracks": TRACKS[:2]}, f)
        try:
            with self.assertRaises(mpv.ConfigError):
                mpv.load_config(f.name)
        finally:
            os.unlink(f.name)


class CommandTest(unittest.TestCase):
    def test_image_background_command(self):
        cfg = {"background_path": "bg.jpg", "fps": 24, "gap_seconds": 2,
               "tracks": [{"path": f"{i}.wav"} for i in range(3)]}
        cmd = mpv.build_ffmpeg_cmd(cfg, 600, "out.mp4")
        self.assertEqual(cmd[cmd.index("-loop") + 1], "1")
        graph = cmd[cmd.index("-filter_complex") + 1]
        self.assertEqual(graph.count("apad=pad_dur=2"), 2)
        self.assertIn("concat=n=3:v=0:a=1[aout]", graph)
        self.assertIn("-tune", cmd)
        self.assertEqual(cmd[-1], "out.mp4")

    def test_video_background_loops(self):
        cfg = {"background_path": "bg.mp4", "fps": 24, "gap_seconds": 0,
               "tracks": [{"path": f"{i}.wav"} for i in range(3)]}
        cmd = mpv.build_ffmpeg_cmd(cfg, 600, "out.mp4")
        self.assertIn("-stream_loop", cmd)
        self.assertNotIn("-tune", cmd)
        self.assertNotIn("apad", cmd[cmd.index("-filter_complex") + 1])


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg 필요")
class RenderTest(unittest.TestCase):
    def test_end_to_end_render(self):
        with tempfile.TemporaryDirectory() as d:
            def run(*args):
                subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)
            run("-f", "lavfi", "-i", "color=c=navy:s=640x360", "-frames:v", "1", os.path.join(d, "bg.png"))
            tracks = []
            for i, (rate, sec) in enumerate([(44100, 11), (48000, 12), (44100, 10.5)]):
                name = f"t{i}.wav"
                run("-f", "lavfi", "-i", f"sine=frequency={300 + i * 100}:sample_rate={rate}:duration={sec}",
                    os.path.join(d, name))
                tracks.append({"artist": "SG", "title": f"곡 {i}", "file": name})
            cfg_path = os.path.join(d, "cfg.json")
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump({"base_dir": d, "background": "bg.png", "gap_seconds": 1, "fps": 2,
                           "title": "테스트", "tracks": tracks}, f, ensure_ascii=False)
            out = os.path.join(d, "out.mp4")
            mpv.main([cfg_path, "-o", out])
            self.assertAlmostEqual(mpv.probe_duration(out), 35.5, delta=0.6)
            with open(os.path.join(d, "out_youtube.txt"), encoding="utf-8") as f:
                desc = f.read()
            self.assertIn("00:00 SG - 곡 0", desc)
            self.assertIn("00:12 SG - 곡 1", desc)
            self.assertIn("00:25 SG - 곡 2", desc)


if __name__ == "__main__":
    unittest.main()
