@echo off
chcp 65001 >nul
rem Soulful Girl 겨울 플레이리스트 영상을 더블클릭 한 번으로 만든다.
cd /d "%~dp0.."

where python >nul 2>nul
if errorlevel 1 (
  echo [1/3] Python 설치 중...
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  set NEED_RESTART=1
)
where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo [2/3] ffmpeg 설치 중...
  winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
  set NEED_RESTART=1
)
if defined NEED_RESTART (
  echo.
  echo 설치가 끝났습니다. 이 창을 닫고 이 파일을 한 번 더 더블클릭하세요.
  pause
  exit /b
)

echo [3/3] 곡 파일 확인 중...
python playlist\make_playlist_video.py playlist\configs\soulful_girl_winter.json --check -o "%USERPROFILE%\Desktop\soulful_girl_winter_playlist.mp4"
if errorlevel 1 (
  echo.
  echo 위 오류 내용을 Claude에게 보내주세요.
  pause
  exit /b
)

echo.
echo 확인 완료. 아무 키나 누르면 영상 만들기를 시작합니다. (10~30분)
pause >nul
python playlist\make_playlist_video.py playlist\configs\soulful_girl_winter.json -o "%USERPROFILE%\Desktop\soulful_girl_winter_playlist.mp4"
if errorlevel 1 (
  echo 영상 만들기에 실패했습니다. 위 오류 내용을 Claude에게 보내주세요.
  pause
  exit /b
)

echo.
echo 완료! 바탕화면에 영상(mp4)과 유튜브 설명란(txt)이 생겼습니다.
start "" "%USERPROFILE%\Desktop"
start "" "https://studio.youtube.com"
pause
