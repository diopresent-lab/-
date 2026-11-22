# DIO Present Instagram

DIO Present 인스타그램 카드뉴스 작업물과 제작 도구.

## 인스타 릴스 성과 리포트

`tools/insta_report.py`는 Windsor.ai instagram 커넥터에서 최근 30일 데이터를 받아
릴스별 조회수, 3초 이탈률, 평균 시청 시간, 저장/공유와 팔로워 증감을 마크다운으로 정리합니다.
외부 패키지 없이 Python 3.9+ 표준 라이브러리만 씁니다.

```bash
export WINDSOR_API_KEY=...        # 필수: Windsor.ai API 키
export WINDSOR_IG_ACCOUNT=...     # 선택: 연결된 계정이 여러 개일 때 계정 ID
python tools/insta_report.py -o reports/ig_report.md   # --days 14 로 기간 변경

# API 키 없이 샘플 데이터로 확인
python tools/insta_report.py --sample tests/fixtures/windsor_sample.json

# 테스트
python -m unittest discover -s tests
```
