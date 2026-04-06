#!/usr/bin/env python3
"""
render_bot.py - Git-Polling Blender Render Manager
Watcher (polls Git) + Executor (runs Blender & FFmpeg)
"""

import os
import sys
import math
import time
import json
import glob
import logging
import argparse
import subprocess
import threading
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

# ==========================================
# ANSI COLOR HELPERS
# ==========================================

class _ANSI:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"

    BLACK   = "\033[30m"
    RED     = "\033[31m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    BLUE    = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN    = "\033[36m"
    WHITE   = "\033[37m"

    BRIGHT_RED     = "\033[91m"
    BRIGHT_GREEN   = "\033[92m"
    BRIGHT_YELLOW  = "\033[93m"
    BRIGHT_BLUE    = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN    = "\033[96m"
    BRIGHT_WHITE   = "\033[97m"

    BG_BLACK  = "\033[40m"
    BG_RED    = "\033[41m"
    BG_GREEN  = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE   = "\033[44m"


def _c(text: str, *codes: str) -> str:
    """Wrap text in ANSI codes (no-op if color is disabled)."""
    if not _COLOR_ENABLED:
        return text
    return "".join(codes) + str(text) + _ANSI.RESET


# Global flag - set by setup_logging()
_COLOR_ENABLED: bool = False


class _ColorFormatter(logging.Formatter):
    """
    Logging formatter that adds colors to level names and messages
    when color output is enabled.
    """
    _LEVEL_STYLES: dict[int, tuple[str, ...]] = {
        logging.DEBUG:    (_ANSI.DIM, _ANSI.WHITE),
        logging.INFO:     (_ANSI.BRIGHT_CYAN,),
        logging.WARNING:  (_ANSI.BRIGHT_YELLOW,),
        logging.ERROR:    (_ANSI.BRIGHT_RED, _ANSI.BOLD),
        logging.CRITICAL: (_ANSI.BG_RED, _ANSI.BRIGHT_WHITE, _ANSI.BOLD),
    }

    _LEVEL_LABELS: dict[int, str] = {
        logging.DEBUG:    " DBG ",
        logging.INFO:     "INFO ",
        logging.WARNING:  "WARN ",
        logging.ERROR:    " ERR ",
        logging.CRITICAL: "CRIT ",
    }

    def format(self, record: logging.LogRecord) -> str:
        ts = self.formatTime(record, "%H:%M:%S")
        label = self._LEVEL_LABELS.get(record.levelno, record.levelname)
        styles = self._LEVEL_STYLES.get(record.levelno, ())
        msg = record.getMessage()

        if _COLOR_ENABLED:
            ts_str    = _c(ts, _ANSI.DIM)
            label_str = _c(label, *styles)
            msg_str   = _c(msg, *styles) if record.levelno >= logging.WARNING else msg
            return f"{ts_str}  {label_str}  {msg_str}"
        else:
            return f"[{ts}] [{label.strip()}] {msg}"


def _make_banner(title: str, width: int = 52) -> str:
    """Return a colored section banner."""
    bar = "─" * width
    if _COLOR_ENABLED:
        return (
            f"\n{_ANSI.BRIGHT_BLUE}{_ANSI.BOLD}╭{bar}╮{_ANSI.RESET}\n"
            f"{_ANSI.BRIGHT_BLUE}{_ANSI.BOLD}│  {title:<{width - 2}}│{_ANSI.RESET}\n"
            f"{_ANSI.BRIGHT_BLUE}{_ANSI.BOLD}╰{bar}╯{_ANSI.RESET}"
        )
    return f"\n{'=' * (width + 2)}\n  {title}\n{'=' * (width + 2)}"


def _make_step(label: str) -> str:
    """Return a colored step label for sub-sections inside a job."""
    if _COLOR_ENABLED:
        return f"{_ANSI.BRIGHT_MAGENTA}{_ANSI.BOLD}  ▶  {label}{_ANSI.RESET}"
    return f"[EXECUTOR] {label}"


def _make_ok(label: str) -> str:
    if _COLOR_ENABLED:
        return f"{_ANSI.BRIGHT_GREEN}{_ANSI.BOLD}  ✔  {label}{_ANSI.RESET}"
    return f"[DONE] {label}"


def _make_warn(label: str) -> str:
    if _COLOR_ENABLED:
        return f"{_ANSI.BRIGHT_YELLOW}{_ANSI.BOLD}  ⚠  {label}{_ANSI.RESET}"
    return f"[WARN] {label}"


# ==========================================
# LOGGING
# ==========================================

def setup_logging(log_level: str = "INFO", log_file: str = None,
                  fancy: bool = False) -> logging.Logger:
    global _COLOR_ENABLED
    _COLOR_ENABLED = fancy and sys.stdout.isatty()

    level = getattr(logging, log_level.upper(), logging.INFO)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(_ColorFormatter())
    handlers: list[logging.Handler] = [console_handler]

    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        # Always plain text in log files
        file_handler.setFormatter(
            logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%H:%M:%S")
        )
        handlers.append(file_handler)

    logging.basicConfig(level=level, handlers=handlers)
    return logging.getLogger("render_bot")


log = logging.getLogger("render_bot")

# ==========================================
# CONSTANTS
# ==========================================

SCRIPT_DIR = Path(__file__).resolve().parent

OUTPUT_CHOICES = ["mp4", "gif", "webm", "frames", "spritesheet", "image"]

# ==========================================
# CONFIG HELPERS
# ==========================================

def load_json_config(path) -> dict:
    """Load a JSON file and return its contents as a dict."""
    p = Path(path)
    if not p.exists():
        log.warning(f"Config file not found: {p}")
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def merge_configs(*configs: dict) -> dict:
    """
    Merge multiple config dicts left to right.
    Later dicts override earlier ones, but None values never overwrite a real value.
    """
    result = {}
    for cfg in configs:
        for k, v in cfg.items():
            if v is not None:
                result[k] = v
    return result


def relative_to_script(path) -> str:
    """Return a path relative to SCRIPT_DIR for use in summary files."""
    try:
        return str(Path(path).resolve().relative_to(SCRIPT_DIR))
    except ValueError:
        return str(path)

# ==========================================
# SHELL HELPERS
# ==========================================

def run_cmd(cmd: list, check: bool = True, cwd=None,
            show_progress: bool = False, dry_run: bool = False,
            timeout: int = None) -> subprocess.CompletedProcess:
    """
    Execute a shell command.
    - show_progress: stream output live instead of capturing.
    - dry_run:       print the command but don't run it.
    - timeout:       kill after N seconds (only when not show_progress).
    """
    log.debug(f"CMD: {' '.join(str(c) for c in cmd)}")

    if dry_run:
        log.info(f"[DRY-RUN] Would execute: {' '.join(str(c) for c in cmd)}")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    if show_progress:
        process = subprocess.Popen(cmd, cwd=cwd)
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            log.error(f"Process timed out after {timeout}s: {' '.join(str(c) for c in cmd)}")
            sys.exit(1)
        returncode = process.returncode
        stdout, stderr = None, None
    else:
        try:
            result = subprocess.run(
                cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout
            )
        except subprocess.TimeoutExpired:
            log.error(f"Process timed out after {timeout}s: {' '.join(str(c) for c in cmd)}")
            sys.exit(1)
        returncode = result.returncode
        stdout, stderr = result.stdout, result.stderr

    if check and returncode != 0:
        log.error(f"Command failed (exit {returncode}): {' '.join(str(c) for c in cmd)}")
        if stdout:
            log.error(f"STDOUT:\n{stdout}")
        if stderr:
            log.error(f"STDERR:\n{stderr}")
        sys.exit(returncode)

    return subprocess.CompletedProcess(cmd, returncode, stdout, stderr)

# ==========================================
# GIT HELPERS
# ==========================================

def git_current_hash(repo_dir) -> str | None:
    res = run_cmd(["git", "rev-parse", "HEAD"], cwd=repo_dir, check=False)
    return res.stdout.strip() if res.returncode == 0 else None


def git_changed_files(repo_dir, old_hash, new_hash) -> list[str]:
    res = run_cmd(["git", "diff", "--name-only", old_hash, new_hash], cwd=repo_dir)
    return [f for f in res.stdout.strip().split("\n") if f]


def git_pull(repo_dir, strategy: str = "merge", remote: str = "origin",
             branch: str = None, dry_run: bool = False):
    """Pull latest changes with the selected strategy."""
    cmd = ["git", "pull"]
    if strategy == "rebase":
        cmd.append("--rebase")
    elif strategy == "ff-only":
        cmd.append("--ff-only")
    if branch:
        cmd.extend([remote, branch])
    run_cmd(cmd, cwd=repo_dir, check=False, dry_run=dry_run)


def git_push_outputs(repo_dir, job_paths: set, n_jobs: int,
                     push_branch: str = None, remote: str = "origin",
                     commit_msg_template: str = None,
                     push_outputs_only: bool = False,
                     dry_run: bool = False):
    """Stage, commit, and push rendered outputs back to the remote."""
    commit_msg = (commit_msg_template or "Auto-Render: {jobs} job(s) completed [{date}]").format(
        jobs=n_jobs,
        files=n_jobs,
        date=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )

    if push_outputs_only:
        # Only add output directories
        for jp in job_paths:
            out_pattern = str(repo_dir / (str(jp) + "_out"))
            run_cmd(["git", "add", out_pattern], cwd=repo_dir, check=False, dry_run=dry_run)
    else:
        run_cmd(["git", "add", "."], cwd=repo_dir, dry_run=dry_run)

    run_cmd(["git", "commit", "-m", commit_msg], cwd=repo_dir, check=False, dry_run=dry_run)

    push_cmd = ["git", "push", remote]
    if push_branch:
        push_cmd.append(push_branch)
    run_cmd(push_cmd, cwd=repo_dir, dry_run=dry_run)
    log.info("Push successful.")

# ==========================================
# BLENDER INTROSPECTION
# ==========================================

BLEND_QUERY_SCRIPT = """
import bpy, json, sys

scene = bpy.context.scene
render = scene.render
data = {
    "fps": render.fps,
    "width": render.resolution_x,
    "height": render.resolution_y,
    "frame_start": scene.frame_start,
    "frame_end": scene.frame_end,
    "frame_step": scene.frame_step,
    "engine": render.engine,
}
print("BLEND_QUERY_RESULT:" + json.dumps(data))
"""


def query_blend_defaults(blend_path: Path, blender: str) -> dict:
    """
    Launch Blender headless to extract scene defaults.
    Returns a dict; values may be used as fallbacks when a job arg is not set.
    """
    tmp_script = blend_path.parent / "_render_bot_query.py"
    tmp_script.write_text(BLEND_QUERY_SCRIPT, encoding="utf-8")
    try:
        result = subprocess.run(
            [blender, "-b", str(blend_path), "--python", str(tmp_script)],
            capture_output=True, text=True, timeout=120,
        )
        for line in result.stdout.splitlines():
            if line.startswith("BLEND_QUERY_RESULT:"):
                data = json.loads(line[len("BLEND_QUERY_RESULT:"):])
                log.debug(f"Blend defaults: {data}")
                return data
    except Exception as e:
        log.warning(f"Could not query blend defaults: {e}")
    finally:
        if tmp_script.exists():
            tmp_script.unlink()
    return {}

# ==========================================
# WEBHOOK NOTIFICATIONS
# ==========================================

def send_webhook(url: str, payload: dict):
    if not url:
        return
        
    try:
        body = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=10) as resp:
            log.debug(f"Webhook OK: {resp.status}")

    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        log.error(f"Webhook HTTP ERROR {e.code}: {error_body}")

    except urllib.error.URLError as e:
        log.error(f"Webhook URL ERROR: {e}")


def notify(config: dict, event: str, message: str, extra: dict = None):
    """
    Fire a webhook if the event is in notify_on.
    event: 'start' | 'done' | 'error' | 'retry'
    """
    notify_on = config.get("notify_on") or []
    if event not in notify_on:
        return
    url = config.get("notify_webhook")
    if not url:
        return

    job_id = config.get("job_id", "")
    content_parts = ["**[render_bot.py]**"]
    
    if job_id:
        content_parts.append(f"{job_id}")
    
    content_parts.append(f"- **{event.upper()}**")
    
    if message:
        # content_parts.append(message)
        content_parts.append(f"```json\n{message}\n```") # with formatting
    
    payload = {
        "content": " ".join(content_parts),
        "username": "Blender Render Bot",
    }

    if extra:
        payload["embeds"] = [{
            # "description": json.dumps(extra, indent=2)[:4000]
            "description": f"```json\n{json.dumps(extra, indent=2)[:4000]}\n```" # with formatting
        }]
    send_webhook(url, payload)

# ==========================================
# EXECUTOR
# ==========================================

def build_blender_py_overrides(config: dict, blend_defaults: dict) -> str:
    """
    Build a Python expression that overrides scene properties in Blender.
    Only overrides values that were explicitly set in config (not None).
    Falls back to blend_defaults for any unset value.
    """
    lines = ["import bpy"]
    scene = "bpy.context.scene"
    render = f"{scene}.render"

    def _set(expr, key, cfg_key=None):
        cfg_key = cfg_key or key
        val = config.get(cfg_key)
        if val is not None:
            lines.append(f"{expr}={repr(val)}")

    _set(f"{render}.resolution_x", "resolution_x", "width")
    _set(f"{render}.resolution_y", "resolution_y", "height")
    _set(f"{render}.fps", "fps", "fps")
    _set(f"{scene}.frame_start", "frame_start")
    _set(f"{scene}.frame_end", "frame_end")
    _set(f"{scene}.frame_step", "frame_step")
    _set(f"{render}.engine", "engine")
    _set(f"{scene}.cycles.device", "device")
    _set(f"{scene}.cycles.samples", "samples")
    _set(f"{render}.threads", "threads")

    # Active camera override
    camera = config.get("camera")
    if camera:
        lines.append(
            f"cam = bpy.data.objects.get({repr(camera)}); "
            f"{scene}.camera = cam if cam else {scene}.camera"
        )

    # Active scene override
    scene_name = config.get("scene")
    if scene_name:
        lines.append(
            f"bpy.context.window.scene = bpy.data.scenes.get({repr(scene_name)}) "
            f"or bpy.context.scene"
        )

    # Extra user-supplied Python
    extra = config.get("extra_python")
    if extra:
        lines.append(extra)

    if len(lines) == 1:
        return ""  # only "import bpy" - nothing to override
    return "; ".join(lines)


def effective_fps(config: dict, blend_defaults: dict) -> int:
    """Return the effective FPS: config beats blend_defaults beats 24."""
    return config.get("fps") or blend_defaults.get("fps") or 24


def execute_job(blend_path, config: dict, dry_run: bool = False) -> list[str]:
    """
    Worker: renders a .blend file and produces the requested output formats.

    Returns a list of generated output file paths.
    """
    blend_path = Path(blend_path).resolve()
    if not blend_path.exists():
        log.error(f"Blend file not found: {blend_path}")
        return []

    name = config.get("output_name") or blend_path.stem
    out_dir_arg = config.get("output_dir")
    if out_dir_arg:
        out_dir = Path(out_dir_arg).resolve()
    else:
        out_dir = blend_path.parent / f"{name}_out"

    out_dir.mkdir(parents=True, exist_ok=True)

    blender = config.get("blender", "blender")
    ffmpeg = config.get("ffmpeg", "ffmpeg")
    show_progress = config.get("show_progress", False)
    job_timeout = config.get("job_timeout")
    outputs = config.get("outputs") or ["mp4"]
    frame_fmt = config.get("frame_format", "PNG").upper()
    # keep_frames applies to any intermediate frame format (PNG / EXR / JPEG).
    # It is also implicitly True when "frames" is listed as an output format.
    keep_frames = config.get("keep_frames", False) or "frames" in outputs

    log.info(_make_banner(f"RENDERING: {name}"))
    log.info(f"Output formats : {', '.join(outputs)}")
    log.info(f"Frame format   : {frame_fmt}  |  keep_frames: {keep_frames}")

    # ----- Query .blend for defaults (only if something is unset) -----
    needs_blend_query = any(
        config.get(k) is None
        for k in ("fps", "width", "height", "frame_start", "frame_end", "frame_step")
    )
    blend_defaults = {}
    if needs_blend_query and not dry_run:
        log.info("Querying .blend for scene defaults...")
        blend_defaults = query_blend_defaults(blend_path, blender)

    fps = effective_fps(config, blend_defaults)

    start_time = time.time()
    generated = []

    # =========================================================
    # 1. BLENDER RENDER → PNG frames
    # =========================================================
    log.info(_make_step("Starting Blender render..."))

    ext_map = {"PNG": "png", "EXR": "exr", "JPEG": "jpg"}
    frame_ext = ext_map.get(frame_fmt, "png")
    frame_pattern = str(out_dir / "frame_####")

    py_expr = build_blender_py_overrides(config, blend_defaults)

    blender_cmd = [blender, "-b", str(blend_path)]

    if py_expr:
        blender_cmd.extend(["--python-expr", py_expr])

    # Passthrough extra blender args
    for arg in (config.get("blender_args") or []):
        blender_cmd.append(arg)

    blender_cmd.extend(["-o", frame_pattern, "-F", frame_fmt, "-a"])

    notify(config, "start", f"Render started: `{name}`")
    run_cmd(blender_cmd, show_progress=show_progress, dry_run=dry_run, timeout=job_timeout)

    # =========================================================
    # 2. POST-PROCESSING
    # =========================================================
    frame_glob = str(out_dir / f"frame_*.{frame_ext}")
    frame_input = str(out_dir / f"frame_%04d.{frame_ext}")

    # ---- MP4 ----
    if "mp4" in outputs:
        log.info(_make_step("Creating MP4..."))
        mp4_out = out_dir / f"{name}.mp4"
        mp4_fps = config.get("mp4_fps") or fps
        mp4_crf = config.get("mp4_crf", 18)
        mp4_preset = config.get("mp4_preset", "medium")
        mp4_codec = config.get("mp4_codec", "libx264")

        mp4_cmd = [
            ffmpeg, "-y",
            "-framerate", str(mp4_fps),
            "-i", frame_input,
            "-c:v", mp4_codec,
            "-crf", str(mp4_crf),
            "-preset", mp4_preset,
            "-pix_fmt", "yuv420p",
        ]

        audio = config.get("mp4_audio")
        if audio and Path(audio).exists():
            mp4_cmd.extend(["-i", audio, "-c:a", "aac", "-shortest"])

        for arg in (config.get("mp4_extra_args") or []):
            mp4_cmd.append(arg)

        mp4_cmd.append(str(mp4_out))
        run_cmd(mp4_cmd, show_progress=show_progress, dry_run=dry_run)
        generated.append(str(mp4_out))

    # ---- GIF ----
    if "gif" in outputs:
        log.info(_make_step("Creating GIF..."))
        gif_out = out_dir / f"{name}.gif"
        palette_out = out_dir / "palette.png"
        gif_fps = config.get("gif_fps", 15)
        gif_width = config.get("gif_width", 640)
        gif_loop = config.get("gif_loop", 0)
        gif_dither = config.get("gif_dither", "bayer")

        if gif_width and gif_width > 0:
            gif_scale = f"scale={gif_width}:-1:flags=lanczos"
        else:
            gif_scale = "scale=trunc(iw/2)*2:-1:flags=lanczos"

        palette_vf = f"fps={gif_fps},{gif_scale},palettegen"
        run_cmd(
            [ffmpeg, "-y", "-i", frame_input, "-vf", palette_vf, str(palette_out)],
            show_progress=show_progress, dry_run=dry_run,
        )

        gif_filter = f"fps={gif_fps},{gif_scale}[x];[x][1:v]paletteuse=dither={gif_dither}"
        run_cmd(
            [
                ffmpeg, "-y", "-i", frame_input, "-i", str(palette_out),
                "-filter_complex", gif_filter,
                "-loop", str(gif_loop),
                str(gif_out),
            ],
            show_progress=show_progress, dry_run=dry_run,
        )

        if palette_out.exists() and not dry_run:
            palette_out.unlink()
        generated.append(str(gif_out))

    # ---- WebM ----
    if "webm" in outputs:
        log.info(_make_step("Creating WebM..."))
        webm_out = out_dir / f"{name}.webm"
        webm_fps = config.get("webm_fps") or fps
        webm_crf = config.get("webm_crf", 30)

        webm_cmd = [
            ffmpeg, "-y",
            "-framerate", str(webm_fps),
            "-i", frame_input,
            "-c:v", "libvpx-vp9",
            "-crf", str(webm_crf),
            "-b:v", "0",
            "-pix_fmt", "yuva420p",
            str(webm_out),
        ]
        run_cmd(webm_cmd, show_progress=show_progress, dry_run=dry_run)
        generated.append(str(webm_out))

    # ---- Spritesheet ----
    if "spritesheet" in outputs:
        log.info(_make_step("Creating Spritesheet..."))
        cols = config.get("spritesheet_cols", 8)
        sprite_scale = config.get("spritesheet_scale")

        frame_files = sorted(glob.glob(frame_glob))
        rows = math.ceil(len(frame_files) / cols) if frame_files else 1

        scale_filter = f"scale={sprite_scale}:-1," if sprite_scale else ""
        tile_filter = f"{scale_filter}tile={cols}x{rows}"

        sprite_out = out_dir / f"{name}_spritesheet.png"
        sprite_cmd = [
            ffmpeg, "-y",
            "-i", frame_input,
            "-vf", tile_filter,
            "-frames:v", "1",
            str(sprite_out),
        ]
        run_cmd(sprite_cmd, show_progress=show_progress, dry_run=dry_run)
        generated.append(str(sprite_out))


    # ---- Image (single still frame) ----
    if "image" in outputs:
        img_fmt = config.get("image_format", "PNG").upper()
        img_frame = config.get("image_frame")

        # Determine which frame to render - use image_frame if set, else frame_start
        if img_frame is None:
            img_frame = blend_defaults.get("frame_start") or 1

        log.info(_make_step(f"Rendering still image (frame {img_frame}, format {img_fmt})..."))

        ext_still_map = {"PNG": "png", "JPEG": "jpg", "JPG": "jpg",
                         "EXR": "exr", "TIFF": "tif", "BMP": "bmp", "WEBP": "webp"}
        img_ext = ext_still_map.get(img_fmt, img_fmt.lower())
        img_out = out_dir / f"{name}.{img_ext}"

        # Build a python expression that also sets frame + image format
        img_py_parts = []
        base_py = build_blender_py_overrides(config, blend_defaults)
        if base_py:
            img_py_parts.append(base_py)
        img_py_parts.append(
            f"import bpy; "
            f"bpy.context.scene.render.image_settings.file_format={repr(img_fmt)}; "
            f"bpy.context.scene.frame_set({img_frame}); "
            f"bpy.context.scene.render.filepath={repr(str(img_out))}; "
            f"bpy.ops.render.render(write_still=True)"
        )
        img_py = "; ".join(img_py_parts)

        img_cmd = [blender, "-b", str(blend_path), "--python-expr", img_py]
        run_cmd(img_cmd, show_progress=show_progress, dry_run=dry_run, timeout=job_timeout)
        generated.append(str(img_out))

    # ---- Frames (keep) ----
    if "frames" in outputs:
        frame_files = sorted(glob.glob(frame_glob))
        generated.extend(frame_files)
        log.info(_make_step(f"Keeping {len(frame_files)} {frame_fmt} frame(s) in: {out_dir}"))

    # ---- Cleanup frames ----
    if not keep_frames and not dry_run:
        for f in glob.glob(frame_glob):
            os.remove(f)

    # =========================================================
    # 3. SUMMARY
    # =========================================================
    duration = round(time.time() - start_time, 2)

    if config.get("summary"):
        summary_data = {
            "job_id": config.get("job_id"),
            "job_name": name,
            "blend_file": relative_to_script(blend_path),
            "output_directory": relative_to_script(out_dir),
            "outputs_requested": outputs,
            "outputs_generated": [relative_to_script(p) for p in generated],
            "blend_defaults_used": blend_defaults,
            "settings": {
                k: v for k, v in config.items()
                if k not in ("blender", "ffmpeg", "notify_webhook")
            },
            "tags": config.get("tags", []),
            "stats": {
                "duration_seconds": duration,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
        }
        summary_file = out_dir / "summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary_data, f, indent=4)
        log.info(f"Summary written to: {relative_to_script(summary_file)}")

    log.info(_make_ok(f"{name} - done in {duration}s"))
    notify(config, "done", f"Render complete: `{name}` in {duration}s", {"outputs": generated})
    return generated

# ==========================================
# WATCHER
# ==========================================

def load_state(state_file: Path) -> dict:
    if state_file.exists():
        try:
            return json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_state(state_file: Path, state: dict):
    state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")


def acquire_lock(lock_file: Path) -> bool:
    """Returns True if lock was acquired (we are the only instance)."""
    if lock_file.exists():
        try:
            pid = int(lock_file.read_text().strip())
            # Check if that PID is still alive
            os.kill(pid, 0)
            return False  # Another process is running
        except (ProcessLookupError, ValueError):
            pass  # Stale lock - overwrite it
    lock_file.write_text(str(os.getpid()))
    return True


def release_lock(lock_file: Path):
    if lock_file.exists():
        lock_file.unlink()


def find_jobs_in_changed_files(changed_files: list[str], repo_dir: Path,
                               watch_patterns: list[str],
                               ignore_patterns: list[str]) -> set[Path]:
    """
    Given a list of changed file paths (relative to repo root),
    return a set of job base paths (stem without extension) whose
    .blend or .json file changed.
    """
    job_paths = set()
    for file in changed_files:
        p = Path(file)
        # Check ignore patterns
        if any(p.match(pat) for pat in (ignore_patterns or [])):
            continue
        if p.suffix in (".blend", ".json"):
            job_paths.add(p.with_suffix(""))
    return job_paths


def run_job_with_retries(blend_file: Path, job_config: dict,
                         max_retries: int, retry_delay: int,
                         dry_run: bool) -> list[str]:
    """Run execute_job up to max_retries times."""
    for attempt in range(1, max_retries + 1):
        try:
            outputs = execute_job(blend_file, job_config, dry_run=dry_run)
            return outputs
        except SystemExit as e:
            if attempt < max_retries:
                log.warning(
                    f"Job failed (attempt {attempt}/{max_retries}). "
                    f"Retrying in {retry_delay}s..."
                )
                notify(job_config, "retry",
                       f"Retry {attempt}/{max_retries} for `{blend_file.name}`")
                time.sleep(retry_delay)
            else:
                log.error(f"Job failed after {max_retries} attempts: {blend_file.name}")
                notify(job_config, "error",
                       f"Job FAILED after {max_retries} attempts: `{blend_file.name}`")
    return []


def watch_repo(repo_dir, interval: int, default_config: dict,
               no_push: bool = False, dry_run: bool = False):
    """
    Watcher: polls Git for changes, dispatches Executor jobs,
    and pushes results back.
    """
    repo_dir = Path(repo_dir).resolve()
    lock_file = repo_dir / (default_config.get("lock_file") or ".render_bot.lock")
    state_file = repo_dir / (default_config.get("state_file") or ".render_bot_state.json")
    once = default_config.get("once", False)

    log.info(_make_banner("render_bot  WATCHER"))
    log.info(f"Repo     : {repo_dir}")
    log.info(f"Interval : {interval}s  |  Outputs: {default_config.get('outputs', ['mp4'])}")

    if not dry_run:
        if not acquire_lock(lock_file):
            log.error(f"Another render_bot instance is running (lock: {lock_file}). Exiting.")
            sys.exit(1)

    try:
        # Restore last known hash from state file (crash recovery)
        state = load_state(state_file)
        last_known_hash = state.get("last_hash")

        max_retries = default_config.get("max_retries", 3)
        retry_delay = default_config.get("retry_delay", 10)
        max_parallel = default_config.get("max_parallel", 1)
        watch_patterns = default_config.get("watch_patterns") or ["*.blend", "*.json"]
        ignore_patterns = default_config.get("ignore_patterns") or []
        remote = default_config.get("remote", "origin")
        branch = default_config.get("branch")
        push_branch = default_config.get("push_branch")
        git_strategy = default_config.get("git_pull_strategy", "merge")
        push_outputs_only = default_config.get("push_outputs_only", False)
        commit_msg_tpl = default_config.get("commit_message")

        while True:
            old_hash = last_known_hash or git_current_hash(repo_dir)

            git_pull(repo_dir, strategy=git_strategy, remote=remote,
                     branch=branch, dry_run=dry_run)
            new_hash = git_current_hash(repo_dir)

            if old_hash and new_hash and old_hash != new_hash:
                log.info(f"New commits: {old_hash[:7]} → {new_hash[:7]}")
                changed_files = git_changed_files(repo_dir, old_hash, new_hash)
                log.debug(f"Changed files: {changed_files}")

                job_stems = find_jobs_in_changed_files(
                    changed_files, repo_dir, watch_patterns, ignore_patterns
                )

                generated_files = []
                completed_jobs = set()

                if max_parallel > 1:
                    threads = []
                    results_lock = threading.Lock()

                    def _run(jp):
                        blend_file = repo_dir / (str(jp) + ".blend")
                        json_file = repo_dir / (str(jp) + ".json")
                        if not blend_file.exists():
                            return
                        job_config = default_config.copy()
                        if json_file.exists():
                            log.info(f"Loading job config: {json_file.name}")
                            job_config = merge_configs(job_config, load_json_config(json_file))
                        outputs = run_job_with_retries(
                            blend_file, job_config, max_retries, retry_delay, dry_run
                        )
                        with results_lock:
                            generated_files.extend(outputs)
                            completed_jobs.add(jp)

                    for jp in job_stems:
                        t = threading.Thread(target=_run, args=(jp,), daemon=True)
                        threads.append(t)
                        if len(threads) >= max_parallel:
                            for th in threads:
                                th.start()
                            for th in threads:
                                th.join()
                            threads = []
                    for th in threads:
                        th.start()
                    for th in threads:
                        th.join()
                else:
                    for jp in job_stems:
                        blend_file = repo_dir / (str(jp) + ".blend")
                        json_file = repo_dir / (str(jp) + ".json")
                        if not blend_file.exists():
                            log.warning(f"No .blend found for job: {jp}")
                            continue
                        job_config = default_config.copy()
                        if json_file.exists():
                            log.info(f"Loading job config: {json_file.name}")
                            job_config = merge_configs(job_config, load_json_config(json_file))
                        else:
                            log.info(f"No JSON config for {blend_file.name}, using defaults.")
                        outputs = run_job_with_retries(
                            blend_file, job_config, max_retries, retry_delay, dry_run
                        )
                        generated_files.extend(outputs)
                        completed_jobs.add(jp)

                # Persist new hash
                last_known_hash = new_hash
                if not dry_run:
                    save_state(state_file, {"last_hash": new_hash})

                # Push results
                if generated_files and not no_push:
                    log.info("Committing and pushing outputs...")
                    git_push_outputs(
                        repo_dir, completed_jobs, len(completed_jobs),
                        push_branch=push_branch, remote=remote,
                        commit_msg_template=commit_msg_tpl,
                        push_outputs_only=push_outputs_only,
                        dry_run=dry_run,
                    )
                elif no_push:
                    log.info("Skipping push (--no-push).")
                else:
                    log.info("No renderable jobs found in this commit.")
            else:
                log.info(f"No changes at {time.strftime('%H:%M:%S')}. Next check in {interval}s.")

            if once:
                log.info("--once flag set. Exiting.")
                break

            time.sleep(interval)

    finally:
        if not dry_run:
            release_lock(lock_file)

# ==========================================
# CLI
# ==========================================

def build_common_parser() -> argparse.ArgumentParser:
    """Shared arguments for both execute and watch subcommands."""
    p = argparse.ArgumentParser(add_help=False)

    # --- Tool Paths ---
    p.add_argument("--blender", default="blender",
                   help="Path to the Blender executable. (default: 'blender')")
    p.add_argument("--ffmpeg", default="ffmpeg",
                   help="Path to the FFmpeg executable. (default: 'ffmpeg')")

    # --- Global Behaviour ---
    p.add_argument("--dry-run", action="store_true",
                   help="Simulate execution; no processes are actually started.")
    p.add_argument("--show-progress", action="store_true",
                   help="Stream live output from Blender and FFmpeg to the terminal.")
    p.add_argument("--log-level", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                   help="Logging verbosity. (default: INFO)")
    p.add_argument("--log-file", default=None,
                   help="Optional path to write logs to a file.")
    p.add_argument("--config", default=None,
                   help="Path to a global JSON config file (base layer, lowest priority).")
    p.add_argument("--fancy", action="store_true", default=False,
                   help="Enable colored, formatted CLI output. "
                        "Requires a TTY; log files always stay plain text.")

    # --- Output Formats ---
    p.add_argument("--outputs", nargs="+", default=["mp4"],
                   choices=OUTPUT_CHOICES,
                   help="Which output formats to produce. (default: mp4)")

    # --- Blender / Scene Overrides (all optional; unset = use .blend value) ---
    p.add_argument("--width", type=int, default=None,
                   help="Override render width in pixels.")
    p.add_argument("--height", type=int, default=None,
                   help="Override render height in pixels.")
    p.add_argument("--fps", type=int, default=None,
                   help="Override frame rate.")
    p.add_argument("--frame-start", type=int, default=None, dest="frame_start",
                   help="Override first frame to render.")
    p.add_argument("--frame-end", type=int, default=None, dest="frame_end",
                   help="Override last frame to render.")
    p.add_argument("--frame-step", type=int, default=None, dest="frame_step",
                   help="Render every Nth frame (e.g. 2 = every other frame).")
    p.add_argument("--scene", default=None,
                   help="Name of the Blender scene to activate.")
    p.add_argument("--camera", default=None,
                   help="Name of the Blender camera object to use.")
    p.add_argument("--samples", type=int, default=None,
                   help="Override render samples (Cycles / EEVEE).")
    p.add_argument("--engine", default=None,
                   choices=["CYCLES", "BLENDER_EEVEE_NEXT", "BLENDER_WORKBENCH"],
                   help="Override render engine.")
    p.add_argument("--device", default=None,
                   choices=["CPU", "GPU", "OPTIX", "HIP", "METAL"],
                   help="Override render device (Cycles only).")
    p.add_argument("--threads", type=int, default=None,
                   help="Number of CPU threads (0 = auto-detect).")
    p.add_argument("--frame-format", default="PNG", dest="frame_format",
                   choices=["PNG", "EXR", "JPEG"],
                   help="Intermediate frame format for Blender output. (default: PNG)")
    p.add_argument("--extra-python", default=None, dest="extra_python",
                   help="Extra Python expression to run inside Blender (appended to overrides).")
    p.add_argument("--blender-args", nargs="*", default=[], dest="blender_args",
                   help="Additional raw arguments passed directly to Blender CLI.")

    # --- MP4 ---
    p.add_argument("--mp4-crf", type=int, default=18, dest="mp4_crf",
                   help="MP4 quality (CRF). 0=lossless, 51=worst. (default: 18)")
    p.add_argument("--mp4-preset", default="medium", dest="mp4_preset",
                   choices=["ultrafast","superfast","veryfast","faster","fast",
                             "medium","slow","slower","veryslow"],
                   help="MP4 x264/x265 encoding speed preset. (default: medium)")
    p.add_argument("--mp4-fps", type=int, default=None, dest="mp4_fps",
                   help="Override MP4 frame rate (defaults to --fps).")
    p.add_argument("--mp4-codec", default="libx264", dest="mp4_codec",
                   choices=["libx264", "libx265", "libvpx-vp9"],
                   help="MP4 video codec. (default: libx264)")
    p.add_argument("--mp4-audio", default=None, dest="mp4_audio",
                   help="Path to an audio file to mux into the MP4.")
    p.add_argument("--mp4-extra-args", nargs="*", default=[], dest="mp4_extra_args",
                   help="Extra raw FFmpeg arguments for MP4 output.")

    # --- GIF ---
    p.add_argument("--gif-fps", type=int, default=15, dest="gif_fps",
                   help="GIF frame rate. (default: 15)")
    p.add_argument("--gif-width", type=int, default=640, dest="gif_width",
                   help="GIF output width in pixels (-1 = original). (default: 640)")
    p.add_argument("--gif-loop", type=int, default=0, dest="gif_loop",
                   help="GIF loop count (0 = infinite). (default: 0)")
    p.add_argument("--gif-dither", default="bayer", dest="gif_dither",
                   choices=["bayer", "floyd_steinberg", "none"],
                   help="GIF dithering algorithm. (default: bayer)")

    # --- WebM ---
    p.add_argument("--webm-crf", type=int, default=30, dest="webm_crf",
                   help="WebM VP9 quality (CRF). (default: 30)")
    p.add_argument("--webm-fps", type=int, default=None, dest="webm_fps",
                   help="Override WebM frame rate (defaults to --fps).")

    # --- Spritesheet ---
    p.add_argument("--spritesheet-cols", type=int, default=8, dest="spritesheet_cols",
                   help="Number of columns in the spritesheet. (default: 8)")
    p.add_argument("--spritesheet-scale", type=int, default=None, dest="spritesheet_scale",
                   help="Width of each frame in the spritesheet (None = original).")


    # --- Image output ---
    p.add_argument("--image-format", default="PNG", dest="image_format",
                   choices=["PNG", "JPEG", "EXR", "TIFF", "BMP", "WEBP"],
                   help="Output format for single-image renders. (default: PNG)")
    p.add_argument("--image-frame", type=int, default=None, dest="image_frame",
                   help="Which frame to render as a still image (defaults to frame_start or .blend value).")

    # --- Frames ---
    p.add_argument("--keep-frames", action="store_true", dest="keep_frames",
                   help="Keep intermediate frames (PNG / EXR / JPEG, depending on "
                        "--frame-format) after post-processing. Implied when 'frames' "
                        "is included in --outputs.")

    # --- Job Metadata ---
    p.add_argument("--job-id", default=None, dest="job_id",
                   help="Arbitrary job identifier for tracking and webhook payloads.")
    p.add_argument("--tags", nargs="*", default=[], dest="tags",
                   help="Tags to include in the summary JSON.")
    p.add_argument("--summary", action="store_true",
                   help="Write a summary.json file to the output directory.")

    # --- Notifications ---
    p.add_argument("--notify-webhook", default=None, dest="notify_webhook",
                   help="HTTP webhook URL for job notifications (Discord/Slack compatible).")
    p.add_argument("--notify-on", nargs="+", default=["error", "done"],
                   dest="notify_on",
                   choices=["start", "done", "error", "retry"],
                   help="Which events trigger a webhook notification. (default: error done)")

    return p


def args_to_config(args: argparse.Namespace) -> dict:
    """Convert parsed CLI args to a plain dict, excluding subcommand-specific keys."""
    skip = {"command", "blend_file", "json", "repo_dir", "interval", "no_push"}
    return {k: v for k, v in vars(args).items() if k not in skip}


def main():
    root_parser = argparse.ArgumentParser(
        prog="render_bot",
        description="Git-polling Blender render manager.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    sub = root_parser.add_subparsers(dest="command", required=True)
    common = build_common_parser()

    # ---- EXECUTE subcommand ----
    exec_parser = sub.add_parser(
        "execute",
        parents=[common],
        help="Render a single .blend file immediately.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    exec_parser.add_argument("blend_file", help="Path to the .blend file.")
    exec_parser.add_argument(
        "--json", default=None,
        help="Path to a JSON job config file (overrides CLI args).",
    )
    exec_parser.add_argument(
        "--output-dir", default=None, dest="output_dir",
        help="Override output directory (default: <blend_stem>_out/ next to .blend).",
    )
    exec_parser.add_argument(
        "--output-name", default=None, dest="output_name",
        help="Override base name for generated files (default: .blend stem).",
    )

    # ---- WATCH subcommand ----
    watch_parser = sub.add_parser(
        "watch",
        parents=[common],
        help="Start the Git-polling watcher.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    watch_parser.add_argument(
        "--repo-dir", default=".", dest="repo_dir",
        help="Path to the Git repository to watch.",
    )
    watch_parser.add_argument(
        "--interval", type=int, default=30,
        help="Git polling interval in seconds.",
    )
    watch_parser.add_argument(
        "--no-push", action="store_true", dest="no_push",
        help="Do not push rendered outputs back to Git.",
    )
    watch_parser.add_argument(
        "--branch", default=None,
        help="Watch a specific remote branch (default: current branch).",
    )
    watch_parser.add_argument(
        "--remote", default="origin",
        help="Git remote name to pull from / push to.",
    )
    watch_parser.add_argument(
        "--push-branch", default=None, dest="push_branch",
        help="Push outputs to a different branch (e.g. 'renders').",
    )
    watch_parser.add_argument(
        "--commit-message", default=None, dest="commit_message",
        help="Template for the auto-commit message. "
             "Placeholders: {jobs}, {files}, {date}.",
    )
    watch_parser.add_argument(
        "--watch-patterns", nargs="+", default=["*.blend", "*.json"],
        dest="watch_patterns",
        help="Glob patterns for files that trigger a render job.",
    )
    watch_parser.add_argument(
        "--ignore-patterns", nargs="*", default=[], dest="ignore_patterns",
        help="Glob patterns for files to ignore (even if they match watch-patterns).",
    )
    watch_parser.add_argument(
        "--max-retries", type=int, default=3, dest="max_retries",
        help="How many times to retry a failed job.",
    )
    watch_parser.add_argument(
        "--retry-delay", type=int, default=10, dest="retry_delay",
        help="Seconds to wait between retries.",
    )
    watch_parser.add_argument(
        "--job-timeout", type=int, default=None, dest="job_timeout",
        help="Kill a job after this many seconds (None = no limit).",
    )
    watch_parser.add_argument(
        "--max-parallel", type=int, default=1, dest="max_parallel",
        help="Number of jobs to run concurrently.",
    )
    watch_parser.add_argument(
        "--lock-file", default=".render_bot.lock", dest="lock_file",
        help="Path to the lock file (prevents duplicate watcher instances).",
    )
    watch_parser.add_argument(
        "--state-file", default=".render_bot_state.json", dest="state_file",
        help="Path to the state file (persists last Git hash for crash recovery).",
    )
    watch_parser.add_argument(
        "--git-pull-strategy", default="merge", dest="git_pull_strategy",
        choices=["merge", "rebase", "ff-only"],
        help="Strategy for 'git pull'.",
    )
    watch_parser.add_argument(
        "--push-outputs-only", action="store_true", dest="push_outputs_only",
        help="Only add output directories to the commit (not the whole repo).",
    )
    watch_parser.add_argument(
        "--once", action="store_true",
        help="Check for changes exactly once, then exit.",
    )

    args = root_parser.parse_args()
    setup_logging(args.log_level, args.log_file, fancy=args.fancy)

    # Build config: global file < CLI args < per-job JSON (only in execute)
    global_cfg = load_json_config(args.config) if args.config else {}
    cli_cfg = args_to_config(args)
    base_config = merge_configs(global_cfg, cli_cfg)

    if args.command == "execute":
        job_config = base_config.copy()
        if args.json:
            job_config = merge_configs(job_config, load_json_config(args.json))
        execute_job(args.blend_file, job_config, dry_run=args.dry_run)

    elif args.command == "watch":
        watch_repo(
            repo_dir=args.repo_dir,
            interval=args.interval,
            default_config=base_config,
            no_push=args.no_push,
            dry_run=args.dry_run,
        )


if __name__ == "__main__":
    main()
