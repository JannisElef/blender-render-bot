# Blender Render Bot

Remote Blender rendering manager using git. Configure a render job, set defaults and parameters, push it with your .blend source-file and let a remote PC render and push the output back to your git.

You can configure your render job [here](https://janniselef.github.io/blender-render-bot/).

---

Drop it next to your repo of `.blend` files, start the **Watcher**, and every push that touches a `.blend` or its matching `.json` job config automatically triggers a headless render - then pushes the outputs back.


---

## Requirements

- Python 3.10+
- [Blender](https://www.blender.org/) (any version with CLI support)
- [FFmpeg](https://ffmpeg.org/)
- Git

---

## Quick Start

```bash

# Start the watcher on a repo with --fancy console output
python render_bot.py watch --repo-dir /path/to/repo --interval 60 --fancy

# Start the watcher with blender not in `PATH`
python render_bot.py watch --blender "C:\Program Files\Blender Foundation\Blender 5.0\blender.exe" --fancy 

# Render a single file right now
python render_bot.py execute my_scene.blend

# Render to MP4 + GIF, GPU, with a colored terminal
python render_bot.py execute my_scene.blend \
    --outputs mp4 gif \
    --device GPU \
    --fancy

```

---

## How it Works

```
Git Remote
    │
    │  git push  (new/changed .blend or .json)
    ▼
┌────────────────────────────────────────────────────┐
│  WATCHER  (polls Git)                              │
│  • git pull                                        │
│  • detects changed .blend / .json files            │
│  • loads per-job JSON config (or CLI defaults)     │
│  • dispatches Executor per changed job             │
│  • git commit + push rendered outputs              │
└─────────────────────┬──────────────────────────────┘
                      │  merged config dict
                      ▼
┌────────────────────────────────────────────────────┐
│  EXECUTOR  (renders one job)                       │
│  • queries .blend for any unset scene values       │
│  • launches Blender headless                       │
│  • runs FFmpeg for every requested output format   │
│  • writes optional summary.json                    │
└────────────────────────────────────────────────────┘
```

**Config priority - lowest to highest:**

```
--config global JSON file
        ↓
CLI arguments
        ↓
per-job .json file   (execute --json  /  auto-discovered by watcher)
```

Any Blender scene parameter left unset at all three levels is read **live from the `.blend`** - no duplicating settings between your file and your config.

---

## Repository Layout

```
my-blender-repo/
├── render_bot.py
├── render_bot.json          ← optional: org-wide defaults
│
├── scenes/
│   ├── hero_shot.blend
│   ├── hero_shot.json       ← optional: per-job overrides
│   └── hero_shot_out/       ← generated
│       ├── hero_shot.mp4
│       ├── hero_shot.gif
│       └── summary.json
│
└── props/
    ├── prop_a.blend
    └── prop_a_out/
        └── prop_a.mp4
```

The watcher pairs every changed `.blend` with a same-name `.json` if one exists. If no JSON is found, CLI / global defaults apply.

---

## Job Config File (JSON)

Place a `<blend_stem>.json` next to the `.blend`. All keys are **optional** - omitting a key means the value comes from the `.blend` scene.

```json
{
    "outputs":           ["mp4", "gif"],

    "width":             1920,
    "height":            1080,
    "fps":               30,
    "frame_start":       1,
    "frame_end":         250,
    "frame_step":        1,
    "scene":             "Main",
    "camera":            "Camera.Render",
    "samples":           128,
    "engine":            "CYCLES",
    "device":            "GPU",
    "threads":           0,
    "frame_format":      "PNG",
    "extra_python":      "import bpy; bpy.context.scene.cycles.use_denoising = True",
    "blender_args":      [],

    "mp4_crf":           20,
    "mp4_preset":        "slow",
    "mp4_fps":           30,
    "mp4_codec":         "libx264",
    "mp4_audio":         null,
    "mp4_extra_args":    [],

    "gif_fps":           24,
    "gif_width":         800,
    "gif_loop":          0,
    "gif_dither":        "bayer",

    "webm_crf":          28,
    "webm_fps":          null,

    "spritesheet_cols":  8,
    "spritesheet_scale": null,

    "keep_frames":       false,
    "output_dir":        null,
    "output_name":       null,

    "summary":           true,
    "job_id":            "shot_042",
    "tags":              ["hero-shot", "v2"],

    "notify_webhook":    "https://discord.com/api/webhooks/...",
    "notify_on":         ["start", "done", "error"]
}
```

---

## CLI Reference

### `execute` - Render a Single File

```bash
python render_bot.py execute <blend_file> [options]
```

| Argument | Default | Description |
|---|---|---|
| `blend_file` | *(required)* | Path to the `.blend` file. |
| `--json PATH` | `None` | Job JSON config (overrides all CLI args for this run). |
| `--output-dir PATH` | `<stem>_out/` next to `.blend` | Override the output directory. |
| `--output-name NAME` | *(blend stem)* | Override the base name for generated files. |

All shared arguments below also apply.

**Examples:**

```bash
# Minimal - all settings from the .blend
python render_bot.py execute hero_shot.blend --fancy

# GPU render, multiple outputs
python render_bot.py execute hero_shot.blend \
    --outputs mp4 gif webm \
    --engine CYCLES --device GPU --samples 256 \
    --mp4-crf 16 --mp4-preset slow \
    --gif-fps 30 --gif-width 1280 \
    --summary --tags cinematic final

# Load everything from a job file
python render_bot.py execute hero_shot.blend --json hero_shot.json

# Dry run - see every command without running anything
python render_bot.py execute hero_shot.blend --dry-run --log-level DEBUG
```

---

### `watch` - Start the Git Watcher

```bash
python render_bot.py watch [options]
```

All shared arguments below also apply.

#### Repository & Git

| Argument | Default | Description |
|---|---|---|
| `--repo-dir PATH` | `.` | Path to the Git repository to watch. |
| `--interval INT` | `30` | Polling interval in seconds. |
| `--branch NAME` | *(current)* | Only watch this remote branch. |
| `--remote NAME` | `origin` | Git remote for pull and push. |
| `--push-branch NAME` | `None` | Push outputs to a different branch (e.g. `renders`). |
| `--no-push` | `False` | Skip committing and pushing rendered outputs. |
| `--push-outputs-only` | `False` | Only `git add` output directories, not the whole working tree. |
| `--git-pull-strategy` | `merge` | `git pull` strategy: `merge`, `rebase`, `ff-only`. |
| `--commit-message TMPL` | *(auto)* | Commit message template. Placeholders: `{jobs}`, `{files}`, `{date}`. |

#### File Detection

| Argument | Default | Description |
|---|---|---|
| `--watch-patterns PAT …` | `*.blend *.json` | Glob patterns for files that trigger a render. |
| `--ignore-patterns PAT …` | `[]` | Glob patterns to exclude even if they match watch patterns. |

#### Reliability & Parallelism

| Argument | Default | Description |
|---|---|---|
| `--max-retries INT` | `3` | Times to retry a failed job before giving up. |
| `--retry-delay INT` | `10` | Seconds between retries. |
| `--job-timeout INT` | `None` | Kill a job after N seconds (`None` = no limit). |
| `--max-parallel INT` | `1` | Maximum concurrent render jobs. |
| `--once` | `False` | Check for changes exactly once then exit - useful for CI. |

#### State & Lock

| Argument | Default | Description |
|---|---|---|
| `--lock-file PATH` | `.render_bot.lock` | Prevents duplicate watcher instances. |
| `--state-file PATH` | `.render_bot_state.json` | Persists last Git hash for crash recovery. |
---

### Shared Arguments

These apply to both `execute` and `watch`.

#### Tool Paths

| Argument | Default | Description |
|---|---|---|
| `--blender PATH` | `blender` | Path to the Blender executable. |
| `--ffmpeg PATH` | `ffmpeg` | Path to the FFmpeg executable. |

#### Behaviour

| Argument | Default | Description |
|---|---|---|
| `--fancy` | `False` | Colored, formatted terminal output with banners and step indicators. Requires a real TTY; log files always stay plain text. |
| `--dry-run` | `False` | Print all commands but do not run anything. |
| `--show-progress` | `False` | Stream live stdout/stderr from Blender and FFmpeg. |
| `--log-level` | `INFO` | Verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `--log-file PATH` | `None` | Also write logs to this file (always plain text). |
| `--config PATH` | `None` | Base-layer JSON config file (lowest priority). |

#### Output Formats

| Argument | Default | Description |
|---|---|---|
| `--outputs FORMAT …` | `mp4` | Formats to produce: `mp4`, `gif`, `webm`, `frames`, `spritesheet`. |

#### Blender / Scene Overrides

All optional. If not set, the value is read live from the `.blend` scene.

| Argument | Default | Description |
|---|---|---|
| `--width INT` | *(from .blend)* | Override render width in pixels. |
| `--height INT` | *(from .blend)* | Override render height in pixels. |
| `--fps INT` | *(from .blend)* | Override frame rate. |
| `--frame-start INT` | *(from .blend)* | First frame to render. |
| `--frame-end INT` | *(from .blend)* | Last frame to render. |
| `--frame-step INT` | *(from .blend)* | Render every Nth frame (`2` = every other). |
| `--scene NAME` | *(from .blend)* | Activate this Blender scene by name. |
| `--camera NAME` | *(from .blend)* | Use this camera object by name. |
| `--samples INT` | *(from .blend)* | Override render samples (Cycles / EEVEE). |
| `--engine ENGINE` | *(from .blend)* | `CYCLES`, `BLENDER_EEVEE_NEXT`, `BLENDER_WORKBENCH`. |
| `--device DEVICE` | *(from .blend)* | `CPU`, `GPU`, `OPTIX`, `HIP`, `METAL` (Cycles only). |
| `--threads INT` | *(from .blend)* | CPU thread count (`0` = auto-detect). |
| `--frame-format FMT` | `PNG` | Intermediate frame format: `PNG`, `EXR`, `JPEG`. |
| `--extra-python EXPR` | `None` | Python expression run inside Blender after all other overrides. |
| `--blender-args ARG …` | `[]` | Raw arguments passed directly to the Blender CLI. |

#### MP4

| Argument | Default | Description |
|---|---|---|
| `--mp4-crf INT` | `18` | Quality (CRF). `0` = lossless, `51` = worst. |
| `--mp4-preset PRESET` | `medium` | x264/x265 speed preset: `ultrafast` … `veryslow`. |
| `--mp4-fps INT` | *(from --fps / .blend)* | Override MP4 frame rate. |
| `--mp4-codec CODEC` | `libx264` | `libx264`, `libx265`, `libvpx-vp9`. |
| `--mp4-audio PATH` | `None` | Audio file to mux into the MP4. |
| `--mp4-extra-args ARG …` | `[]` | Extra raw FFmpeg arguments for the MP4 pass. |

#### GIF

| Argument | Default | Description |
|---|---|---|
| `--gif-fps INT` | `15` | GIF frame rate. |
| `--gif-width INT` | `640` | Output width in pixels (`-1` = keep original). |
| `--gif-loop INT` | `0` | Loop count (`0` = infinite). |
| `--gif-dither METHOD` | `bayer` | `bayer`, `floyd_steinberg`, `none`. |

#### WebM

| Argument | Default | Description |
|---|---|---|
| `--webm-crf INT` | `30` | VP9 quality (CRF). |
| `--webm-fps INT` | *(from --fps / .blend)* | Override WebM frame rate. |

#### Spritesheet

| Argument | Default | Description |
|---|---|---|
| `--spritesheet-cols INT` | `8` | Columns in the spritesheet grid. |
| `--spritesheet-scale INT` | `None` | Width of each frame tile in pixels. |

#### Frames & Metadata

| Argument | Default | Description |
|---|---|---|
| `--keep-frames` | `False` | Keep intermediate frames (PNG / EXR / JPEG, matching `--frame-format`) after post-processing. Implied when `frames` is in `--outputs`. |
| `--job-id ID` | `None` | Identifier included in the summary and webhook payloads. |
| `--tags TAG …` | `[]` | Labels stored in `summary.json`. |
| `--summary` | `False` | Write `summary.json` to the output directory. |

#### Notifications

| Argument | Default | Description |
|---|---|---|
| `--notify-webhook URL` | `None` | Webhook endpoint (Discord / Slack compatible). |
| `--notify-on EVENT …` | `error done` | Events: `start`, `done`, `error`, `retry`. |

---

## Output Formats

Pass one or more to `--outputs` (or `"outputs"` in JSON):

| Format | Description |
|---|---|
| `mp4` | H.264 / H.265 / VP9 video via FFmpeg. |
| `gif` | Palette-optimised GIF with configurable dithering. |
| `webm` | VP9 WebM - supports alpha channel. |
| `frames` | Keep the individual rendered frames (PNG / EXR / JPEG). Implies `--keep-frames`. |
| `spritesheet` | Single tiled PNG of all frames - useful for game assets. |

Multiple formats at once: `--outputs mp4 gif spritesheet`

---

## Summary File

Written to the output directory when `--summary` is set. All paths are relative to the script's own directory.

```json
{
    "job_id": "shot_042",
    "job_name": "hero_shot",
    "blend_file": "scenes/hero_shot.blend",
    "output_directory": "scenes/hero_shot_out",
    "outputs_requested": ["mp4", "gif"],
    "outputs_generated": [
        "scenes/hero_shot_out/hero_shot.mp4",
        "scenes/hero_shot_out/hero_shot.gif"
    ],
    "blend_defaults_used": {
        "fps": 24,
        "width": 1920,
        "height": 1080,
        "frame_start": 1,
        "frame_end": 250,
        "frame_step": 1,
        "engine": "CYCLES"
    },
    "settings": { "...": "effective merged config" },
    "tags": ["hero-shot", "v2"],
    "stats": {
        "duration_seconds": 482.3,
        "timestamp": "2025-06-01 14:22:10"
    }
}
```

---

## Notifications (Discord / Slack)

```bash
python render_bot.py watch \
    --notify-webhook "https://discord.com/api/webhooks/TOKEN/ID" \
    --notify-on start done error retry
```

| Event | Fires when |
|---|---|
| `start` | A render job begins. |
| `done` | A render job completes successfully. |
| `error` | A job fails all retries. |
| `retry` | A job fails but has retries remaining. |

---

## Notes

- **Lock file** - on startup the watcher writes `.render_bot.lock` with its PID and removes it on exit. Stale locks (dead PID) are cleared automatically.
- **State file** - `.render_bot_state.json` persists the last processed Git hash. A restarted watcher continues from where it left off instead of skipping commits.
- **Blend defaults query** - Blender is launched once in a lightweight Python-only mode before the actual render to read any unset scene values. This adds a few seconds per job but means zero duplicated config.
- **`--fancy` + `--log-file`** - color codes appear only in the terminal stream; the log file always receives plain text regardless.
- **`--dry-run` + `--log-level DEBUG`** - prints every command that would run, including the full Blender Python expression, without touching the filesystem or spawning any processes.
- **`null` in JSON** - a key set to `null` is ignored during config merging; it will not clear a value set at a lower priority level.


See more information [here](https://janniselef.github.io/projects/blender-render-bot/).