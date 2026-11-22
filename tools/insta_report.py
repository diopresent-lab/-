"""Instagram 릴스 성과 리포트 (Windsor.ai instagram 커넥터).

최근 N일(기본 30일) 동안 올린 릴스별 조회수, 3초 이탈률, 평균 시청 시간,
저장·공유 수와 기간 중 팔로워 증감을 마크다운 리포트로 만듭니다.

사용법:
    export WINDSOR_API_KEY=...            # Windsor.ai API 키 (필수)
    export WINDSOR_IG_ACCOUNT=...         # 선택: 여러 계정이 연결된 경우 계정 ID
    python tools/insta_report.py                      # 표준출력으로 리포트
    python tools/insta_report.py -o reports/ig.md     # 파일로 저장
    python tools/insta_report.py --days 14
    python tools/insta_report.py --sample tests/fixtures/windsor_sample.json  # API 없이

외부 패키지 없이 표준 라이브러리만 사용합니다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta

API_URL = "https://connectors.windsor.ai/instagram"
API_KEY_ENV = "WINDSOR_API_KEY"
ACCOUNT_ENV = "WINDSOR_IG_ACCOUNT"

# Windsor.ai instagram 커넥터 필드 ID (get_fields로 확인한 값)
MEDIA_FIELDS = [
    "date",
    "timestamp",
    "media_id",
    "media_permalink",
    "media_caption",
    "media_type",
    "media_product_type",
    "media_views",
    "media_reach",
    "media_reel_skip_rate",
    "media_reel_avg_watch_time",
    "media_saved",
    "media_shares",
    "media_like_count",
    "media_comments_count",
]
FOLLOWER_FIELDS = ["date", "follower_count", "followers_count"]


# --------------------------------------------------------------------------- #
# 데이터 가져오기
# --------------------------------------------------------------------------- #
def fetch(fields: list[str], date_from: date, date_to: date, api_key: str,
          account: str | None = None, timeout: int = 60) -> list[dict]:
    params = {
        "api_key": api_key,
        "fields": ",".join(fields),
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
    }
    if account:
        params["select_accounts"] = f"instagram__{account}"
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "insta-report/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as e:
        # URL에 API 키가 들어 있으므로 에러 메시지에 URL을 노출하지 않음
        raise RuntimeError(f"Windsor.ai 요청 실패: HTTP {e.code}") from None
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"] or []
    if isinstance(payload, list):
        return payload
    raise RuntimeError(f"예상하지 못한 응답 형식: {str(payload)[:200]}")


# --------------------------------------------------------------------------- #
# 계산
# --------------------------------------------------------------------------- #
def _num(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def is_reel(row: dict) -> bool:
    product = str(row.get("media_product_type") or "").upper()
    mtype = str(row.get("media_type") or "").upper()
    return product in ("REELS", "REEL", "CLIPS") or mtype == "REEL"


@dataclass
class Reel:
    media_id: str
    date: str
    caption: str
    permalink: str
    views: float
    reach: float
    skip_rate: float | None   # 0~100 (%)
    avg_watch_sec: float | None
    saves: float
    shares: float
    likes: float
    comments: float

    @property
    def save_share_rate(self) -> float | None:
        """조회수 대비 (저장+공유) 비율 %."""
        if not self.views:
            return None
        return (self.saves + self.shares) / self.views * 100


def build_reels(rows: list[dict]) -> list[Reel]:
    """미디어 행을 릴스 단위로 합칩니다(같은 media_id가 여러 행으로 올 수 있음)."""
    merged: dict[str, dict] = {}
    for r in rows:
        if not is_reel(r):
            continue
        mid = str(r.get("media_id") or "")
        if not mid:
            continue
        cur = merged.setdefault(mid, {})
        for k, v in r.items():
            if v not in (None, "") and k not in cur:
                cur[k] = v

    reels = []
    for mid, r in merged.items():
        skip = _num(r.get("media_reel_skip_rate"))
        if skip is not None and skip <= 1:  # 0~1 비율로 오는 경우 %로 변환
            skip *= 100
        watch_ms = _num(r.get("media_reel_avg_watch_time"))
        caption = str(r.get("media_caption") or "").replace("\n", " ").strip()
        reels.append(Reel(
            media_id=mid,
            date=str(r.get("date") or str(r.get("timestamp") or "")[:10]),
            caption=caption,
            permalink=str(r.get("media_permalink") or ""),
            views=_num(r.get("media_views")) or 0,
            reach=_num(r.get("media_reach")) or 0,
            skip_rate=skip,
            avg_watch_sec=watch_ms / 1000 if watch_ms is not None else None,
            saves=_num(r.get("media_saved")) or 0,
            shares=_num(r.get("media_shares")) or 0,
            likes=_num(r.get("media_like_count")) or 0,
            comments=_num(r.get("media_comments_count")) or 0,
        ))
    reels.sort(key=lambda x: x.views, reverse=True)
    return reels


@dataclass
class FollowerSummary:
    new_followers: float | None   # 기간 중 신규 팔로워 합 (follower_count 일별 합)
    current: float | None         # 현재 총 팔로워
    daily: list[tuple[str, float]]

    @property
    def start_estimate(self) -> float | None:
        if self.current is None or self.new_followers is None:
            return None
        return self.current - self.new_followers


def build_followers(rows: list[dict]) -> FollowerSummary:
    daily: dict[str, float] = {}
    current = None
    for r in rows:
        d = str(r.get("date") or "")
        nf = _num(r.get("follower_count"))
        if d and nf is not None:
            daily[d] = daily.get(d, 0) + nf
        fc = _num(r.get("followers_count"))
        if fc is not None:
            current = fc if current is None else max(current, fc)
    series = sorted(daily.items())
    total = sum(v for _, v in series) if series else None
    return FollowerSummary(new_followers=total, current=current, daily=series)


# --------------------------------------------------------------------------- #
# 마크다운
# --------------------------------------------------------------------------- #
def _fmt_int(v: float | None) -> str:
    return "-" if v is None else f"{int(round(v)):,}"


def _fmt_pct(v: float | None) -> str:
    return "-" if v is None else f"{v:.1f}%"


def _fmt_sec(v: float | None) -> str:
    return "-" if v is None else f"{v:.1f}초"


def _signed(v: float | None) -> str:
    if v is None:
        return "-"
    return f"{'+' if v >= 0 else ''}{int(round(v)):,}"


def _short(text: str, n: int = 24) -> str:
    text = text.replace("|", "／")
    return text if len(text) <= n else text[: n - 1] + "…"


def _avg(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def render_markdown(reels: list[Reel], followers: FollowerSummary,
                    date_from: date, date_to: date) -> str:
    out = []
    out.append(f"# 인스타그램 릴스 성과 리포트")
    out.append("")
    out.append(f"기간: {date_from.isoformat()} ~ {date_to.isoformat()} "
               f"({(date_to - date_from).days + 1}일) · 릴스 {len(reels)}개")
    out.append("")

    # 요약
    total_views = sum(r.views for r in reels)
    out.append("## 요약")
    out.append("")
    out.append("| 항목 | 값 |")
    out.append("|---|---|")
    out.append(f"| 총 조회수 | {_fmt_int(total_views)} |")
    out.append(f"| 릴스당 평균 조회수 | {_fmt_int(total_views / len(reels) if reels else None)} |")
    out.append(f"| 평균 3초 이탈률 | {_fmt_pct(_avg(r.skip_rate for r in reels))} |")
    out.append(f"| 평균 시청 시간 | {_fmt_sec(_avg(r.avg_watch_sec for r in reels))} |")
    out.append(f"| 총 저장 | {_fmt_int(sum(r.saves for r in reels))} |")
    out.append(f"| 총 공유 | {_fmt_int(sum(r.shares for r in reels))} |")
    out.append(f"| 신규 팔로워 | {_signed(followers.new_followers)} |")
    out.append(f"| 현재 팔로워 | {_fmt_int(followers.current)} |")
    out.append("")

    # 릴스별 표
    out.append("## 릴스별 성과 (조회수 순)")
    out.append("")
    if not reels:
        out.append("이 기간에 올린 릴스가 없습니다.")
    else:
        out.append("| # | 게시일 | 릴스 | 조회수 | 도달 | 3초 이탈률 | 평균 시청 | 저장 | 공유 | 저장+공유율 |")
        out.append("|---|---|---|--:|--:|--:|--:|--:|--:|--:|")
        for i, r in enumerate(reels, 1):
            title = _short(r.caption) or r.media_id
            link = f"[{title}]({r.permalink})" if r.permalink else title
            out.append(
                f"| {i} | {r.date} | {link} | {_fmt_int(r.views)} | {_fmt_int(r.reach)} | "
                f"{_fmt_pct(r.skip_rate)} | {_fmt_sec(r.avg_watch_sec)} | "
                f"{_fmt_int(r.saves)} | {_fmt_int(r.shares)} | {_fmt_pct(r.save_share_rate)} |"
            )
    out.append("")

    # 하이라이트
    if reels:
        out.append("## 하이라이트")
        out.append("")
        best = reels[0]
        out.append(f"- 조회수 1위: {_short(best.caption, 40) or best.media_id} ({_fmt_int(best.views)})")
        with_skip = [r for r in reels if r.skip_rate is not None]
        if with_skip:
            hook = min(with_skip, key=lambda r: r.skip_rate)
            out.append(f"- 이탈률이 가장 낮은 훅: {_short(hook.caption, 40) or hook.media_id} "
                       f"({_fmt_pct(hook.skip_rate)})")
        with_watch = [r for r in reels if r.avg_watch_sec is not None]
        if with_watch:
            w = max(with_watch, key=lambda r: r.avg_watch_sec)
            out.append(f"- 평균 시청 시간 최장: {_short(w.caption, 40) or w.media_id} "
                       f"({_fmt_sec(w.avg_watch_sec)})")
        with_ss = [r for r in reels if r.save_share_rate is not None]
        if with_ss:
            s = max(with_ss, key=lambda r: r.save_share_rate)
            out.append(f"- 저장+공유율 최고: {_short(s.caption, 40) or s.media_id} "
                       f"({_fmt_pct(s.save_share_rate)})")
        out.append("")

    # 팔로워
    out.append("## 팔로워 증감")
    out.append("")
    if followers.daily:
        out.append(f"기간 시작 추정 {_fmt_int(followers.start_estimate)} → "
                   f"현재 {_fmt_int(followers.current)} ({_signed(followers.new_followers)})")
        out.append("")
        out.append("| 날짜 | 신규 팔로워 |")
        out.append("|---|--:|")
        for d, v in followers.daily:
            out.append(f"| {d} | {_signed(v)} |")
    else:
        out.append("일별 팔로워 데이터가 없습니다. (Instagram은 팔로워 100명 미만 계정이나 "
                   "30일보다 오래된 날짜에 대해 이 값을 주지 않습니다.)")
    out.append("")
    out.append("> 3초 이탈률은 처음 3초 안에 넘긴 조회 비율, 평균 시청 시간은 Instagram이 "
               "제공하는 릴스 평균 재생 시간입니다. 데이터: Windsor.ai instagram 커넥터.")
    out.append("")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def period(days: int, today: date | None = None) -> tuple[date, date]:
    """오늘은 데이터가 덜 쌓였으므로 어제까지 days일."""
    today = today or date.today()
    end = today - timedelta(days=1)
    return end - timedelta(days=days - 1), end


def generate(days: int = 30, sample: str | None = None, today: date | None = None) -> str:
    date_from, date_to = period(days, today)
    if sample:
        with open(sample, encoding="utf-8") as f:
            data = json.load(f)
        media_rows, follower_rows = data.get("media", []), data.get("followers", [])
        if "date_from" in data and "date_to" in data:
            date_from = date.fromisoformat(data["date_from"])
            date_to = date.fromisoformat(data["date_to"])
    else:
        api_key = os.environ.get(API_KEY_ENV)
        if not api_key:
            raise SystemExit(f"환경변수 {API_KEY_ENV} 가 없습니다. Windsor.ai API 키를 설정하세요.")
        account = os.environ.get(ACCOUNT_ENV) or None
        media_rows = fetch(MEDIA_FIELDS, date_from, date_to, api_key, account)
        follower_rows = fetch(FOLLOWER_FIELDS, date_from, date_to, api_key, account)
    return render_markdown(build_reels(media_rows), build_followers(follower_rows),
                           date_from, date_to)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Windsor.ai 데이터로 인스타 릴스 성과 리포트 생성")
    p.add_argument("--days", type=int, default=30, help="최근 며칠 (기본 30)")
    p.add_argument("-o", "--output", help="저장할 마크다운 파일 경로 (없으면 표준출력)")
    p.add_argument("--sample", help="API 대신 읽을 샘플 JSON ({media:[...], followers:[...]})")
    args = p.parse_args(argv)

    md = generate(args.days, args.sample)
    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"리포트 저장: {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
