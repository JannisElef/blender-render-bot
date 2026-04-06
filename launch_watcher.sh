#!/usr/bin/env bash
# ============================================================
#  Blender Render Bot — Watcher Launch Script  (Linux / macOS)
#  Edit the CONFIG section, or import this file in the GUI:
#    render_bot_config.html
# ============================================================

# -------------------------------------------------------
#  PATHS
# -------------------------------------------------------
PYTHON=python3
SCRIPT="$(cd "$(dirname "$0")" && pwd)/render_bot.py"
REPO_DIR="$(dirname "$SCRIPT")"

# -------------------------------------------------------
#  WATCHER
# -------------------------------------------------------
INTERVAL=30
BRANCH=""
REMOTE="origin"
PUSH_BRANCH=""
GIT_PULL_STRATEGY="merge"
MAX_RETRIES=3
RETRY_DELAY=10
MAX_PARALLEL=1
JOB_TIMEOUT=""

# -------------------------------------------------------
#  OUTPUT FORMATS  (space-separated: mp4 gif webm frames spritesheet image)
# -------------------------------------------------------
OUTPUTS="mp4"
BLENDER="blender"
FFMPEG="ffmpeg"

# -------------------------------------------------------
#  IMAGE OUTPUT  (only used when "image" is in OUTPUTS)
# -------------------------------------------------------
IMAGE_FORMAT="PNG"
IMAGE_FRAME=""

# -------------------------------------------------------
#  FLAGS  (true / false)
# -------------------------------------------------------
FLAG_NO_PUSH=false
FLAG_PUSH_OUTPUTS_ONLY=false
FLAG_FANCY=true
FLAG_SHOW_PROGRESS=false
FLAG_SUMMARY=false
FLAG_DRY_RUN=false
FLAG_ONCE=false
FLAG_KEEP_FRAMES=false

# -------------------------------------------------------
#  LOGGING
# -------------------------------------------------------
LOG_LEVEL="INFO"
LOG_FILE=""

# -------------------------------------------------------
#  NOTIFICATIONS
# -------------------------------------------------------
NOTIFY_WEBHOOK=""
NOTIFY_ON="error done"

# -------------------------------------------------------
#  RENDER DEFAULTS  (leave empty to read from .blend)
# -------------------------------------------------------
WIDTH=""
HEIGHT=""
FPS=""
FRAME_START=""
FRAME_END=""
ENGINE=""
DEVICE=""
SAMPLES=""

# ============================================================
#  BUILD COMMAND
# ============================================================
CMD=("$PYTHON" "$SCRIPT" watch)
CMD+=(--repo-dir "$REPO_DIR")
CMD+=(--interval "$INTERVAL")
CMD+=(--remote "$REMOTE")
CMD+=(--git-pull-strategy "$GIT_PULL_STRATEGY")
CMD+=(--max-retries "$MAX_RETRIES")
CMD+=(--retry-delay "$RETRY_DELAY")
CMD+=(--max-parallel "$MAX_PARALLEL")
CMD+=(--log-level "$LOG_LEVEL")
CMD+=(--outputs $OUTPUTS)
CMD+=(--blender "$BLENDER")
CMD+=(--ffmpeg "$FFMPEG")

[ -n "$BRANCH" ]          && CMD+=(--branch "$BRANCH")
[ -n "$PUSH_BRANCH" ]     && CMD+=(--push-branch "$PUSH_BRANCH")
[ -n "$JOB_TIMEOUT" ]     && CMD+=(--job-timeout "$JOB_TIMEOUT")
[ -n "$LOG_FILE" ]        && CMD+=(--log-file "$LOG_FILE")
[ -n "$NOTIFY_WEBHOOK" ]  && CMD+=(--notify-webhook "$NOTIFY_WEBHOOK" --notify-on $NOTIFY_ON)
[ -n "$WIDTH" ]           && CMD+=(--width "$WIDTH")
[ -n "$HEIGHT" ]          && CMD+=(--height "$HEIGHT")
[ -n "$FPS" ]             && CMD+=(--fps "$FPS")
[ -n "$FRAME_START" ]     && CMD+=(--frame-start "$FRAME_START")
[ -n "$FRAME_END" ]       && CMD+=(--frame-end "$FRAME_END")
[ -n "$ENGINE" ]          && CMD+=(--engine "$ENGINE")
[ -n "$DEVICE" ]          && CMD+=(--device "$DEVICE")
[ -n "$SAMPLES" ]         && CMD+=(--samples "$SAMPLES")
[ -n "$IMAGE_FORMAT" ]    && CMD+=(--image-format "$IMAGE_FORMAT")
[ -n "$IMAGE_FRAME" ]     && CMD+=(--image-frame "$IMAGE_FRAME")

$FLAG_NO_PUSH           && CMD+=(--no-push)
$FLAG_PUSH_OUTPUTS_ONLY && CMD+=(--push-outputs-only)
$FLAG_FANCY             && CMD+=(--fancy)
$FLAG_SHOW_PROGRESS     && CMD+=(--show-progress)
$FLAG_SUMMARY           && CMD+=(--summary)
$FLAG_DRY_RUN           && CMD+=(--dry-run)
$FLAG_ONCE              && CMD+=(--once)
$FLAG_KEEP_FRAMES       && CMD+=(--keep-frames)

# ============================================================
#  LAUNCH
# ============================================================
echo ""
echo "  Blender Render Bot | Watcher"
echo "  ──────────────────────────────"
echo "  Repo    : $REPO_DIR"
echo "  Interval: ${INTERVAL}s   Outputs: $OUTPUTS"
echo "  Blender : $BLENDER"
echo ""
echo "  ${CMD[*]}"
echo ""
echo "  Press Ctrl+C to stop."
echo "  ──────────────────────────────────────────────"
echo ""

"${CMD[@]}"

echo ""
echo "  Watcher stopped."
