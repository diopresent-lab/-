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

## 유튜브 플레이리스트 영상 (`playlist/`)

설정 파일(JSON)의 곡 목록으로 1920x1080 장시간 플레이리스트 MP4를 만들고,
곡 길이로 계산한 타임스탬프(유튜브 챕터)가 들어간 제목·설명란·고정 댓글 텍스트를 함께 만듭니다.
ffmpeg/ffprobe만 있으면 됩니다 (윈도우: `winget install Gyan.FFmpeg`).

```bash
# 파일 확인 + 타임스탬프만 미리 보기 (렌더링 안 함)
python playlist/make_playlist_video.py playlist/configs/soulful_girl_winter.json --check

# 영상 만들기 → soulful_girl_winter_playlist.mp4 + soulful_girl_winter_playlist_youtube.txt
python playlist/make_playlist_video.py playlist/configs/soulful_girl_winter.json
```
설정 항목: `base_dir`(음원 폴더), `background`(이미지 또는 반복 영상),
`fit`(`crop`: 화면을 꽉 채우고 넘치는 부분 자름 / `blur`: 사진 전체를 보이고 양옆을 흐린 사진으로 채움), `gap_seconds`(곡 사이 무음),
`title`, `intro`, `links`, `hashtags`, `pinned_comment`, `tracks`(artist·title·file).
`file`에는 `전체목록_ISRC_발매일.csv`의 파일 경로(역슬래시)를 그대로 붙여 넣어도 됩니다.

## 릴스 업로드 자동화 (`tools/ig_upload`)

Instagram Graph API(비즈니스·크리에이터 계정)로 릴스 영상과 캡션을 올립니다.

### 준비
1. 계정마다 Facebook 페이지에 연결된 Instagram 비즈니스/크리에이터 계정과,
   `instagram_basic`, `instagram_content_publish`, `pages_read_engagement` 권한이 있는 장기 액세스 토큰이 필요합니다.
2. 계정 목록은 `config/ig_accounts.json` 에 있습니다 (현재 `diopresent`, `aimusic_chart`). 비밀값은 넣지 않습니다.
3. 토큰과 IG 사용자 ID는 환경변수로 넣습니다. 형식은 `.env.example` 참고:
   `IG_<계정키 대문자>_ACCESS_TOKEN`, `IG_<계정키 대문자>_USER_ID`
4. `pip install -r requirements.txt`

### 사용법
```bash
# 실제 업로드 없이 검증과 요청 계획만 확인
python -m tools.ig_upload --account aimusic_chart \
  --video reels_2026-11-21/건축과음악사이_릴스.mp4 --caption-file caption.txt --dry-run

# 실제 업로드 (여러 계정: --account 반복, 또는 --all)
python -m tools.ig_upload --account diopresent --account aimusic_chart --video reel.mp4 --caption "캡션 #해시태그"
```
옵션: `--video-url`(공개 https 주소), `--no-feed`(피드 공유 안 함), `--cover-url`, `--thumb-offset-ms`.

업로드 전 확인 항목: mp4/mov, 300MB 이하, 캡션 2200자·해시태그 30개·멘션 20개 이하.

### 계정 추가
`config/ig_accounts.json` 의 `accounts` 에 키를 하나 추가하고 해당 환경변수 두 개를 설정하면 됩니다.

### 테스트
```bash
python -m pytest -q tests
```
