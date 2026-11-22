import json
import os
import sys
import unittest
from datetime import date
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import insta_report as ir  # noqa: E402

SAMPLE = os.path.join(ROOT, "tests", "fixtures", "windsor_sample.json")


def load():
    with open(SAMPLE, encoding="utf-8") as f:
        return json.load(f)


class BuildReelsTest(unittest.TestCase):
    def setUp(self):
        self.reels = ir.build_reels(load()["media"])

    def test_only_reels_and_dedup(self):
        self.assertEqual([r.media_id for r in self.reels], ["1801", "1803", "1802"])

    def test_skip_rate_fraction_converted_to_percent(self):
        by_id = {r.media_id: r for r in self.reels}
        self.assertAlmostEqual(by_id["1802"].skip_rate, 52.0)
        self.assertAlmostEqual(by_id["1801"].skip_rate, 38.5)

    def test_watch_time_in_seconds_and_rates(self):
        r = {r.media_id: r for r in self.reels}["1803"]
        self.assertAlmostEqual(r.avg_watch_sec, 9.8)
        self.assertAlmostEqual(r.save_share_rate, (95 + 60) / 8900 * 100)


class FollowersTest(unittest.TestCase):
    def test_sum_and_start(self):
        f = ir.build_followers(load()["followers"])
        self.assertEqual(f.new_followers, 90)
        self.assertEqual(f.current, 1530)
        self.assertEqual(f.start_estimate, 1440)

    def test_empty(self):
        f = ir.build_followers([])
        self.assertIsNone(f.new_followers)
        self.assertIsNone(f.start_estimate)


class RenderTest(unittest.TestCase):
    def test_markdown_from_sample(self):
        md = ir.generate(sample=SAMPLE)
        self.assertIn("기간: 2026-10-22 ~ 2026-11-20 (30일) · 릴스 3개", md)
        self.assertIn("| 총 조회수 | 26,600 |", md)
        self.assertIn("| 신규 팔로워 | +90 |", md)
        self.assertIn("(https://www.instagram.com/reel/AAA111/)", md)
        self.assertIn("52.0%", md)
        self.assertIn("9.8초", md)
        self.assertIn("1,440 → 현재 1,530 (+90)", md)
        self.assertNotIn("카드뉴스 표지", md)
        # 캡션의 | 문자가 표를 깨지 않아야 함
        for line in md.splitlines():
            if line.startswith("| 1 |"):
                self.assertEqual(line.count("|"), 11)

    def test_no_reels(self):
        md = ir.render_markdown([], ir.build_followers([]), date(2026, 11, 1), date(2026, 11, 30))
        self.assertIn("이 기간에 올린 릴스가 없습니다.", md)
        self.assertIn("일별 팔로워 데이터가 없습니다", md)


class PeriodAndApiTest(unittest.TestCase):
    def test_period_ends_yesterday(self):
        self.assertEqual(ir.period(30, date(2026, 11, 22)), (date(2026, 10, 23), date(2026, 11, 21)))

    def test_requires_api_key(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SystemExit):
                ir.generate()

    def test_uses_env_key_and_fields(self):
        calls = []

        def fake_fetch(fields, date_from, date_to, api_key, account=None):
            calls.append((fields, api_key, account))
            data = load()
            return data["media"] if "media_id" in fields else data["followers"]

        env = {ir.API_KEY_ENV: "test-key", ir.ACCOUNT_ENV: "123"}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(ir, "fetch", side_effect=fake_fetch):
            md = ir.generate(today=date(2026, 11, 21))
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(c[1] == "test-key" and c[2] == "123" for c in calls))
        self.assertIn("릴스 3개", md)

    def test_fetch_builds_url_and_parses(self):
        captured = {}

        class Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self, *a):
                return json.dumps({"data": [{"media_id": "1"}]}).encode()

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            return Resp()

        with mock.patch.object(ir.urllib.request, "urlopen", fake_urlopen):
            rows = ir.fetch(["date", "media_id"], date(2026, 11, 1), date(2026, 11, 2), "k", "99")
        self.assertEqual(rows, [{"media_id": "1"}])
        self.assertIn("api_key=k", captured["url"])
        self.assertIn("fields=date%2Cmedia_id", captured["url"])
        self.assertIn("date_from=2026-11-01", captured["url"])
        self.assertIn("select_accounts=instagram__99", captured["url"])


if __name__ == "__main__":
    unittest.main()
