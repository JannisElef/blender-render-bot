@echo off
setlocal EnableDelayedExpansion
title Blender Render Bot — Watcher

:: ============================================================
::  Blender Render Bot — Watcher Launch Script  (Windows)
::  Edit the CONFIG section, or import this file in the GUI:
::    render_bot_config.html
:: ============================================================

:: -------------------------------------------------------
::  PATHS
:: -------------------------------------------------------
set PYTHON=python
set SCRIPT=%~dp0render_bot.py
set REPO_DIR=%~dp0

:: -------------------------------------------------------
::  WATCHER
:: -------------------------------------------------------
set INTERVAL=30
set BRANCH=
set REMOTE=origin
set PUSH_BRANCH=
set GIT_PULL_STRATEGY=merge
set MAX_RETRIES=3
set RETRY_DELAY=10
set MAX_PARALLEL=1
set JOB_TIMEOUT=

:: -------------------------------------------------------
::  OUTPUT FORMATS  (space-separated: mp4 gif webm frames spritesheet image)
:: -------------------------------------------------------
set OUTPUTS=mp4
set BLENDER=blender
set FFMPEG=ffmpeg

:: -------------------------------------------------------
::  IMAGE OUTPUT  (only used when "image" is in OUTPUTS)
:: -------------------------------------------------------
set IMAGE_FORMAT=PNG
set IMAGE_FRAME=

:: -------------------------------------------------------
::  FLAGS  (1 = on, 0 = off)
:: -------------------------------------------------------
set FLAG_NO_PUSH=0
set FLAG_PUSH_OUTPUTS_ONLY=0
set FLAG_FANCY=1
set FLAG_SHOW_PROGRESS=0
set FLAG_SUMMARY=0
set FLAG_DRY_RUN=0
set FLAG_ONCE=0
set FLAG_KEEP_FRAMES=0

:: -------------------------------------------------------
::  LOGGING
:: -------------------------------------------------------
set LOG_LEVEL=INFO
set LOG_FILE=

:: -------------------------------------------------------
::  NOTIFICATIONS
:: -------------------------------------------------------
set NOTIFY_WEBHOOK=
set NOTIFY_ON=error done

:: -------------------------------------------------------
::  RENDER DEFAULTS  (blank = read from .blend)
:: -------------------------------------------------------
set WIDTH=
set HEIGHT=
set FPS=
set FRAME_START=
set FRAME_END=
set ENGINE=
set DEVICE=
set SAMPLES=

:: ============================================================
::  BUILD COMMAND
:: ============================================================
set CMD=%PYTHON% "%SCRIPT%" watch
set CMD=%CMD% --repo-dir "%REPO_DIR%"
set CMD=%CMD% --interval %INTERVAL%
set CMD=%CMD% --remote %REMOTE%
set CMD=%CMD% --git-pull-strategy %GIT_PULL_STRATEGY%
set CMD=%CMD% --max-retries %MAX_RETRIES%
set CMD=%CMD% --retry-delay %RETRY_DELAY%
set CMD=%CMD% --max-parallel %MAX_PARALLEL%
set CMD=%CMD% --log-level %LOG_LEVEL%
set CMD=%CMD% --outputs %OUTPUTS%
set CMD=%CMD% --blender "%BLENDER%"
set CMD=%CMD% --ffmpeg "%FFMPEG%"

if not "%BRANCH%"==""         set CMD=%CMD% --branch %BRANCH%
if not "%PUSH_BRANCH%"==""    set CMD=%CMD% --push-branch %PUSH_BRANCH%
if not "%JOB_TIMEOUT%"==""    set CMD=%CMD% --job-timeout %JOB_TIMEOUT%
if not "%LOG_FILE%"==""       set CMD=%CMD% --log-file "%LOG_FILE%"
if not "%NOTIFY_WEBHOOK%"=""  set CMD=%CMD% --notify-webhook "%NOTIFY_WEBHOOK%"
if not "%NOTIFY_ON%"==""      set CMD=%CMD% --notify-on %NOTIFY_ON%
if not "%WIDTH%"==""          set CMD=%CMD% --width %WIDTH%
if not "%HEIGHT%"==""         set CMD=%CMD% --height %HEIGHT%
if not "%FPS%"==""            set CMD=%CMD% --fps %FPS%
if not "%FRAME_START%"==""    set CMD=%CMD% --frame-start %FRAME_START%
if not "%FRAME_END%"==""      set CMD=%CMD% --frame-end %FRAME_END%
if not "%ENGINE%"==""         set CMD=%CMD% --engine %ENGINE%
if not "%DEVICE%"==""         set CMD=%CMD% --device %DEVICE%
if not "%SAMPLES%"==""        set CMD=%CMD% --samples %SAMPLES%
if not "%IMAGE_FORMAT%"==""   set CMD=%CMD% --image-format %IMAGE_FORMAT%
if not "%IMAGE_FRAME%"==""    set CMD=%CMD% --image-frame %IMAGE_FRAME%

if %FLAG_NO_PUSH%==1           set CMD=%CMD% --no-push
if %FLAG_PUSH_OUTPUTS_ONLY%==1 set CMD=%CMD% --push-outputs-only
if %FLAG_FANCY%==1             set CMD=%CMD% --fancy
if %FLAG_SHOW_PROGRESS%==1     set CMD=%CMD% --show-progress
if %FLAG_SUMMARY%==1           set CMD=%CMD% --summary
if %FLAG_DRY_RUN%==1           set CMD=%CMD% --dry-run
if %FLAG_ONCE%==1              set CMD=%CMD% --once
if %FLAG_KEEP_FRAMES%==1       set CMD=%CMD% --keep-frames

:: ============================================================
::  LAUNCH
:: ============================================================
echo.
echo  Blender Render Bot  ^|  Watcher
echo  ──────────────────────────────
echo  Repo    : %REPO_DIR%
echo  Interval: %INTERVAL%s   Outputs: %OUTPUTS%
echo  Blender : %BLENDER%
echo.
echo  %CMD%
echo.
echo  Press Ctrl+C to stop.
echo  ──────────────────────────────────────────────
echo.

%CMD%

echo.
echo  Watcher stopped.
pause
