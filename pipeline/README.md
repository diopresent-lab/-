# 릴스 자동화 파이프라인 (@tiand_official)

```
매일 18:40 KST     ──▶ [prepare]  브리프 선택(없으면 자동 곡 소개) → 배경음악·배경 고르기 → reel/make_reel.py 로 MP4 → 캡션·해시태그 초안 → dry-run 계획
                              │      (토큰 없이 동작. 결과는 Actions 아티팩트 + 실행 요약에 캡션 표시)
                              ▼
                       [publish]  IG_PUBLISH_ENABLED=true 일 때만 실행
                                  → instagram-publish 환경 승인 대기
                                  → 19:00 KST 까지 기다렸다가 tools/ig_upload 로 실제 게시
                                  → pipeline/state/posted.json 에 기록(중복 게시 방지)

매주 월 09:00 KST ──▶ [weekly-report]  tools/insta_report.py --days 7 → reports/weekly/<날짜>_tiand.md
```

## 실제 게시 잠금 (기본: 꺼짐)

실제 게시는 아래가 **모두** 참일 때만 일어납니다. 하나라도 아니면 dry-run 입니다.

1. 저장소 변수 `IG_PUBLISH_ENABLED` = `true` (기본값 없음 → publish job 자체가 건너뜀)
2. GitHub 환경 `instagram-publish` 승인 (Required reviewers 를 본인으로 지정하면 회차마다 승인 버튼)
3. 코드 안에서 다시 `--publish` + `IG_PUBLISH_APPROVED=true` 를 확인
4. 토큰 `IG_TIAND_ACCESS_TOKEN` 이 있어야 함 (없으면 오류로 멈춤)

토큰 재발급이 끝나기 전에는 1번을 켜지 마세요. 그동안은 매 회차 MP4·캡션 초안·dry-run 계획만 만들어집니다.

## 콘텐츠 넣기: 브리프

`pipeline/briefs/tiand/<게시일>_<제목>.json` 하나가 릴스 1개입니다.

```json
{
  "id": "2026-11-23_읽씹금지",
  "publish_date": "2026-11-23",
  "reel": { ...reel/make_reel.py 설정과 같음 (hook, song, subtitles, cta)... },
  "caption": { "hook": "첫 줄", "body": "본문", "cta": "선택" },
  "hashtags": ["읽씹금지", "연애송"]
}
```

- 선택 순서: 오늘 날짜 브리프 → 없으면 날짜가 없거나 지난 미게시 브리프 중 가장 오래된 것. 미래 날짜는 그날 전엔 안 씀.
- 쓸 브리프가 없는 날은 **자동 곡 소개 릴스**를 만듭니다 (아래 '배경음악·배경 자동 선택').
- `caption` 을 비우면 릴스 문구(훅·자막·CTA)로 캡션 초안을 만듭니다.
- 해시태그 = 브리프 해시태그 + `config/pipeline.json` 의 계정 기본 해시태그, 중복 제거, 최대 15개.
- `tag`, CTA 의 `팔로우 → @tiand_official` 은 계정 기본값으로 자동으로 채웁니다.

## 배경음악·배경 자동 선택

매 회차 띠앙드 곡의 30초 하이라이트(후렴 구간)를 배경음악으로, 풍경 사진/영상을 배경으로 깝니다.

| 무엇 | 위치 | 만드는 도구 |
|---|---|---|
| 곡 클립 + 목록 | `pipeline/music/tiand/` (`catalog.json`, `<ISRC>.m4a`) | `tools/extract_highlights.py` |
| 배경 사진·영상 | `pipeline/backgrounds/tiand/` (`backgrounds.json`) | `tools/prepare_backgrounds.py` |

- **브리프 곡이 카탈로그에 있으면** 그 곡 클립을 씁니다. 없으면 무음 그대로 둡니다 (다른 곡을 잘못 붙이지 않게). `song.audio` 를 직접 적으면 그게 우선.
- **브리프가 없는 날**은 카탈로그에서 곡을 골라 훅·자막·CTA·캡션까지 자동으로 만듭니다 (`pipeline/media.py`).
- 곡·배경 고르는 규칙: 게시 기록(`posted.json` 의 `track_id`, `background`)에서 가장 덜 쓴 것 중 날짜 기준으로 돌아가며 선택. 실제 게시가 꺼져 있어도 매일 다른 조합이 나옵니다.
- **미발매곡**(`release_date` 가 비어 있음)은 고르지 않습니다. 발매되면 `catalog.json` 에 날짜를 채우세요.
- 배경을 쓰지 않으려면 브리프에 `"background": false`. 어둡기는 `config/pipeline.json` 의 `background_dim` (기본 0.5).

곡이나 배경을 추가·교체할 때 (PC 에서, 원본 폴더는 읽기만 함):

```bash
python3 tools/extract_highlights.py "E:/앨범/DistroKid 백업" --artist 띠앙드 --display-artist "TIAND(띠앙드)" --out pipeline/music/tiand
python3 tools/prepare_backgrounds.py "E:/앨범/DistroKid 백업/플레이리스트배경사진" --out pipeline/backgrounds/tiand --images 120
```

이미 만든 클립·배경은 건너뛰므로 새 파일만 추가됩니다.

## 로컬 실행

```bash
pip install -r requirements.txt pillow   # + ffmpeg, 한글 글꼴
python -m pipeline prepare --account tiand --out build/reel            # 생성 + 캡션 + dry-run
python -m pipeline publish --manifest build/reel/manifest.json         # 항상 dry-run
```

## 필요한 시크릿·변수 (GitHub → Settings → Secrets and variables → Actions)

| 이름 | 종류 | 어디 | 용도 |
|---|---|---|---|
| `IG_TIAND_ACCESS_TOKEN` | Secret | 환경 `instagram-publish` | `instagram_content_publish` 권한 장기 토큰 (재발급 후 등록) |
| `IG_TIAND_USER_ID` | Secret | 환경 `instagram-publish` | @tiand_official 의 IG 비즈니스 계정 ID |
| `IG_PUBLISH_ENABLED` | Variable | 저장소 | `true` 일 때만 실제 게시. 기본 비워둠 |
| `WINDSOR_API_KEY` | Secret | 저장소 | 주간 성과 리포트 (Windsor.ai) |
| `WINDSOR_IG_ACCOUNT` | Variable | 저장소 | Windsor 에 계정이 여러 개일 때 @tiand_official 계정 ID |
| `IG_API_VERSION`, `IG_GRAPH_HOST` | (선택) | - | Graph API 버전·호스트 바꿀 때만 |
