# Coding Standards — Fighter-ID-Vision3D

Standards specific to this Python computer-vision project. All new code must follow these conventions.

---

## 1. Project Layout

```
Fighter-ID-Vision3D/
├── fighterid_vision_engine/   # All new vision-engine logic goes here
│   ├── config/settings.py     # Single source of truth for configuration
│   ├── camera/capture.py      # Camera stream management
│   ├── detection/             # Pose detection and tracking
│   └── pipeline/              # Processing pipeline (engine, strike, state)
├── main.py                    # Headless CLI entry point (thin wrapper only)
├── app.py                     # Multi-mode launcher (thin wrapper only)
├── three_camera_ui.py         # GUI dashboard
├── fight_manager.py           # Fight workflow and API orchestration
├── fighterid_supabase_bridge.py  # Canonical Supabase/HTTP client
└── tools/                     # Stand-alone utility scripts
```

**Rules:**
- New engine logic → `fighterid_vision_engine/pipeline/` or a new subpackage.
- Entry-point files (`main.py`, `app.py`) must remain thin — import and call, do not implement.
- Do not add new root-level `*.py` files unless they are clearly a standalone tool or entry point.
- Maximum 500 LOC per file. Split modules that grow beyond this.

## 2. Configuration

All configuration is sourced from `.env` and exposed through `fighterid_vision_engine/config/settings.py`.

```python
# CORRECT — read through settings
from fighterid_vision_engine.config.settings import Settings
speed_threshold = Settings.STRIKE_SPEED_MS

# WRONG — raw os.getenv in a library module
import os
speed = float(os.getenv("STRIKE_SPEED_MS", "3.5"))
```

- Add every new tuneable parameter to `settings.py` with a typed property and a sensible default.
- Add the same parameter to `.env.example` with a comment explaining units and valid range.
- Validate physical parameters (must be positive, within plausible range) in `settings.py`.

## 3. Logging

Internal modules use Python's `logging` module; `print()` is reserved for entry-point/UI files only.

```python
# CORRECT — library module
import logging
logger = logging.getLogger(__name__)
logger.info("Motor started — fight_id=%s device=%s", fight_id, device_id)

# WRONG — library module using print
print(f"[ENGINE] Motor started: {fight_id}")
```

Log level guidance:
- `DEBUG` — per-frame values, tracker assignments, raw keypoint data.
- `INFO` — lifecycle events (session start/stop, camera open, fight created).
- `WARNING` — degraded state (CPU fallback, low confidence, retrying).
- `ERROR` — recoverable failure (API call failed, camera dropped a frame).
- `CRITICAL` — unrecoverable failure requiring process exit.

## 4. Type Annotations

All public APIs must be fully annotated. Private helpers (`_name`) may omit annotations but should remain clear.

```python
# CORRECT
def compute_velocity(positions: deque[tuple[float, float]], fps: float) -> float:
    ...

# WRONG — unannotated public method
def compute_velocity(positions, fps):
    ...
```

- Use `Optional[X]` (or `X | None` on Python 3.10+) for nullable returns.
- Prefer concrete types over `Any`; use `Any` only when interfacing with untyped third-party code.

## 5. Error Handling

```python
# CORRECT — specific exception with context
try:
    response = requests.post(url, json=payload, timeout=5)
    response.raise_for_status()
except requests.RequestException as exc:
    logger.error("Strike event push failed: %s", exc)

# WRONG — bare except swallows everything
try:
    requests.post(url, json=payload)
except:
    pass
```

- Never use bare `except:`.
- Camera failures must log at `ERROR` level and raise or set a clear error flag — never return `None` silently.
- API calls to Supabase edge functions should include a timeout and handle `requests.Timeout` separately.
- Transient failures (network errors) should retry with exponential back-off before giving up.

## 6. Threading

```python
# CORRECT — always acquire lock before mutating shared state
def record_hit(self, fighter_id: str) -> None:
    with self._lock:
        self._state[fighter_id]["hits"] += 1

# WRONG — mutation without lock
def record_hit(self, fighter_id):
    self._state[fighter_id]["hits"] += 1  # race condition
```

- Every write to `FightersState` fields must be inside `with self._lock:`.
- Worker threads must be daemon threads or implement a clean shutdown via a `threading.Event`.
- Use `queue.Queue(maxsize=N)` for inter-thread frame passing — never a plain list.
- Avoid `time.sleep()` in hot paths; use `queue.get(timeout=...)` instead.

## 7. GPU / Inference

Follow the established fallback chain defined in `fighterid_vision_engine/detection/pose.py`:

```
DirectML (AMD) → CUDA (NVIDIA) → CPU
```

- GPU detection code lives only in `pose.py`. Do not duplicate detection logic in other modules.
- Log the chosen provider at `INFO` level on startup: `logger.info("ONNX provider: %s", provider)`.
- Respect the `FORCE_CPU` environment variable by checking `Settings.FORCE_CPU` before attempting GPU.

## 8. API / Supabase Client

- Use `fighterid_supabase_bridge.py` (`FighterIDAPI`) as the canonical HTTP client for all new code.
- Do not instantiate `supabase_client.py` (legacy) in new code.
- All edge-function calls follow the contract: `start → event* → stop`.
- Session IDs must be valid UUIDs; validate with `uuid.UUID(session_id)` before sending.

## 9. Naming Conventions

| Entity | Convention | Example |
|--------|------------|---------|
| Module | `snake_case` | `temporal_strike.py` |
| Class | `PascalCase` | `TemporalStrikeAnalyzer` |
| Function / method | `snake_case` | `detect_punch_type` |
| Constant | `UPPER_SNAKE_CASE` | `STRIKE_COOL_S` |
| Private attribute | `_leading_underscore` | `self._lock` |
| Type alias | `PascalCase` | `PoseKeypoints = list[tuple[float, float]]` |

## 10. Commit & PR Guidelines

- Commit messages: imperative mood, ≤72 chars subject line. Example: `Add retry logic to strike event push`.
- One logical change per commit; do not mix refactors with feature additions.
- PR must pass the `lint.yml` CI checks before requesting review.
- PRs touching `settings.py` or `.env.example` require a note in the PR description listing all new/changed variables.
- PRs touching `temporal_strike.py` must include updated or new unit tests.
