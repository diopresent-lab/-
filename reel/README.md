# 릴스 생성기 (`reel/make_reel.py`)

설정 파일(JSON) 하나로 인스타그램 릴스용 **1080x1920 MP4**를 만듭니다.
첫 3초 훅 문구, 곡 정보, 자막, 마지막 CTA만 바꾸면 같은 디자인으로 매주 릴스를 뽑을 수 있습니다.

> 배경: @diopresent.official 최근 30일 릴스는 **첫 3초 이탈 80%, 평균 시청 4.3초**였습니다.
> 그래서 이 도구는 훅을 0초 첫 프레임부터 바로 보여주고(빈 화면 없음), 훅이 3초를 넘으면 설정 오류로 막습니다.

## 준비

- Python 3.9 이상, [Pillow](https://pypi.org/project/pillow/): `pip install pillow`
- ffmpeg: macOS `brew install ffmpeg` / Ubuntu `sudo apt install ffmpeg` / Windows `winget install ffmpeg`
- 한글 글꼴: Noto Sans CJK KR, Apple SD 산돌고딕 Neo, 맑은 고딕, 나눔고딕 중 하나를 자동으로 찾습니다.
  다른 글꼴을 쓰려면 설정의 `theme.font_bold`, `theme.font_regular`에 파일 경로를 적으세요.

## 사용법

```bash
# 1) 설정만 검사 (훅 3초 초과, 자막 겹침, 곡 제목 누락 등)
python3 reel/make_reel.py reel/configs/example.json --check

# 2) 원하는 시점만 PNG로 미리보기 (빠름)
python3 reel/make_reel.py reel/configs/example.json --preview 0,4,8,13

# 3) MP4 만들기 (15초 기준 약 15초 소요)
python3 reel/make_reel.py reel/configs/example.json
python3 reel/make_reel.py reel/configs/example.json -o reels_out/이번주.mp4
```

새 릴스는 `reel/configs/example.json`을 복사해 `reel/configs/2026-11-29_곡제목.json`처럼 저장하고 내용을 바꾸면 됩니다.
출력 기본 폴더 `reels_out/`은 git에 올라가지 않습니다. 올릴 완성본만 날짜 폴더(예: `reels_2026-11-21/`)로 옮겨 커밋하세요.

## 설정 항목

| 키 | 필수 | 설명 |
|---|---|---|
| `output` | | 출력 경로. 없으면 설정 파일 이름 + `.mp4` |
| `duration` / `fps` | | 기본 15초 / 30fps |
| `tag` | | 화면 위쪽 작은 머리글 (예: `DIO PRESENT · 건축과 음악 사이`) |
| `hook.text` | ✅ | 첫 화면 훅 문구. 0초부터 바로 보입니다 |
| `hook.end` | | 훅이 사라지는 시점. 기본 3.0, **3초를 넘기면 오류** |
| `hook.size` | | 글자 크기(px). 기본 104, 두 줄 문장은 80~90 권장 |
| `song.title` | ✅ | 곡 제목. 화면 아래 ♪ 배지로 표시 |
| `song.artist` | | 아티스트 |
| `song.audio` | | 음원 파일(mp3/wav/m4a). 없으면 무음 영상 |
| `song.audio_start` | | 음원에서 몇 초 지점부터 쓸지 (후렴 시작점 등) |
| `song.show_from` | | 곡 배지가 나타나는 시점. 기본 0 |
| `subtitles[]` | | `{start, end, text}` 목록. 시간이 겹치거나 훅과 겹치면 오류 |
| `subtitles[].size` / `line_gap` | | 자막 글자 크기(기본 76) / 줄 간격(기본 1.35) |
| `cta.start` | | CTA가 나타나 끝까지 유지되는 시점 |
| `cta.title` / `cta.text` / `cta.sub` | | 큰 제목 / 중간 문구 / 작은 안내 (예: 팔로우 안내) |
| `theme.*` | | `background`, `text`, `accent`, `muted` 색과 글꼴 경로 |
| `visual` | | `equalizer`(도면 그리드 → 이퀄라이저 배경) 또는 `none` |
| `silent_audio_track` | | `true`면 음원이 없을 때 무음 오디오 트랙을 넣음 (일부 업로드 도구용) |

### 글자 강조와 줄바꿈

- `[단어]`로 감싸면 강조색(`theme.accent`)으로 칠합니다. 예: `낮에는 [도면]을 그리고`
- `\n`은 줄바꿈입니다. 너무 긴 줄은 어절 단위로 자동 줄바꿈되어 단어가 쪼개지지 않습니다.
- 자막이 초당 9자를 넘으면 "읽기엔 빠를 수 있다"는 경고를 띄웁니다.

## 음원에 대해

인스타그램 앱의 음악 라이브러리 곡을 쓰려면 `song.audio`를 비워 무음으로 만든 뒤 업로드할 때 앱에서 곡을 붙이세요.
자작곡(예: 띠앙드 신곡)을 넣을 때만 `song.audio`에 파일 경로를 적습니다. 마지막 1초는 자동으로 페이드아웃됩니다.

## 참고

`tools/make_reel.py`는 2026-11-21 「건축과 음악 사이」 릴스 한 편을 만들 때 쓴 일회성 스크립트(HTML+Playwright, 문구 고정)입니다.
같은 릴스를 이 도구로 다시 만드는 설정이 `reel/configs/example.json`입니다.
