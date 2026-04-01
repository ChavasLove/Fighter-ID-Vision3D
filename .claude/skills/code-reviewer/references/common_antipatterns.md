# Common Antipatterns — Fighter-ID-Vision3D

Known patterns to avoid in this codebase, based on issues identified during analysis. Each entry explains the problem, shows a concrete example, and gives the correct alternative.

---

## 1. Duplicate `FighterIDAPI` Class

**Problem:** `FighterIDAPI` is defined in both `fighterid_vision_engine/pipeline/engine.py` and `fighterid_supabase_bridge.py`. The two implementations can drift, causing subtle behavioural differences between headless and GUI modes.

**Antipattern:**
```python
# engine.py — defines its own HTTP client
class FighterIDAPI:
    def push_event(self, payload): ...

# fighterid_supabase_bridge.py — defines another one
class FighterIDAPI:
    def push_event(self, payload): ...  # different retry logic!
```

**Fix:** Remove the inline `FighterIDAPI` from `engine.py` and import from `fighterid_supabase_bridge`:
```python
from fighterid_supabase_bridge import FighterIDAPI
```

---

## 2. Legacy Duplicate Module (`vision_motor_v1.py`)

**Problem:** `vision_motor_v1.py` (635 lines) is a near-copy of the modularised `fighterid_vision_engine/pipeline/engine.py`. Keeping both means bug fixes must be applied in two places.

**Antipattern:** Modifying `vision_motor_v1.py` to fix a bug that also exists in `engine.py`.

**Fix:** Confirm all features from `vision_motor_v1.py` exist in the modularised engine, then delete `vision_motor_v1.py`. Any external references should be updated to import from `fighterid_vision_engine.pipeline.engine`.

---

## 3. Silent Camera Failure

**Problem:** When no camera backend succeeds, `CameraStream` logs an error and continues, returning `None` frames. Downstream consumers then crash with unhelpful `NoneType` attribute errors far from the actual failure point.

**Antipattern:**
```python
def _open_camera(self):
    for backend in self._backends:
        cap = cv2.VideoCapture(self.index, backend)
        if cap.isOpened():
            return cap
    print(f"[ERROR] Camera {self.index} could not be opened")
    return None  # silent failure propagates
```

**Fix:** Raise a descriptive exception immediately:
```python
def _open_camera(self) -> cv2.VideoCapture:
    for backend in self._backends:
        cap = cv2.VideoCapture(self.index, backend)
        if cap.isOpened():
            logger.info("Camera %d opened with backend %s", self.index, backend)
            return cap
    raise RuntimeError(
        f"Camera {self.index} could not be opened with any backend: {self._backends}"
    )
```

---

## 4. Unprotected `FightersState` Mutations

**Problem:** Some code paths read or write `FightersState` fields without acquiring `self._lock`, creating race conditions between the vision pipeline thread and the telemetry push thread.

**Antipattern:**
```python
# Called from a worker thread — no lock
def increment_xp(self, fighter_id: str, amount: int) -> None:
    self._state[fighter_id]["xp"] += amount
```

**Fix:** Always use the context manager:
```python
def increment_xp(self, fighter_id: str, amount: int) -> None:
    with self._lock:
        self._state[fighter_id]["xp"] += amount
```

---

## 5. Bare `except:` Clauses

**Problem:** Bare `except:` catches `KeyboardInterrupt`, `SystemExit`, and `GeneratorExit` in addition to real errors. This prevents Ctrl-C from stopping the process cleanly.

**Antipattern:**
```python
try:
    self._api.push_event(payload)
except:
    pass  # swallows everything, including keyboard interrupt
```

**Fix:**
```python
try:
    self._api.push_event(payload)
except Exception as exc:
    logger.error("Event push failed: %s", exc)
```

---

## 6. Raw Configuration Access Outside `settings.py`

**Problem:** Calling `os.getenv()` directly in library modules scatters configuration logic, makes it hard to validate values, and silently uses `None` when a variable is missing.

**Antipattern:**
```python
# In engine.py
STRIKE_SPEED = float(os.getenv("STRIKE_SPEED_MS", "3.5"))
PIX_PER_M = float(os.getenv("PIX_PER_M", "200"))
```

**Fix:** Add properties to `settings.py` with validation:
```python
# In settings.py
@property
def STRIKE_SPEED_MS(self) -> float:
    val = float(os.getenv("STRIKE_SPEED_MS", "3.5"))
    if val <= 0:
        raise ValueError("STRIKE_SPEED_MS must be positive")
    return val
```

Then in consumers:
```python
from fighterid_vision_engine.config.settings import Settings
speed = Settings.STRIKE_SPEED_MS
```

---

## 7. Hardcoded Credentials in Source Files

**Problem:** Real Supabase URLs and publishable keys appearing in Python source files (outside `.env`) will be committed to git history and may be exposed in logs or stack traces.

**Antipattern:**
```python
SUPABASE_URL = "https://abcxyz123.supabase.co"
API_KEY = "sb_publishable_abcdef..."
```

**Fix:** Store in `.env`, read through `settings.py`. The CI `lint.yml` job will flag any regressions.

---

## 8. Inconsistent GPU Detection

**Problem:** GPU provider detection logic is duplicated in `vision_motor_v1.py`, `pose.py`, and `fighterid_supabase_bridge.py` with different error messages and fallback behaviours.

**Antipattern:** Adding another copy of DirectML/CUDA detection in a new module.

**Fix:** GPU detection lives exclusively in `fighterid_vision_engine/detection/pose.py`. All other modules that need inference must instantiate `PoseDetector` from there, not roll their own provider selection.

---

## 9. `print()` in Engine/Library Modules

**Problem:** `print()` statements in library code bypass the logging framework, cannot be filtered by log level, and pollute stdout in production deployments where only structured logs are consumed.

**Antipattern:**
```python
# In fighterid_vision_engine/pipeline/engine.py
print(f"[ENGINE] Strike detected: {punch_type} confidence={conf:.2f}")
```

**Fix:**
```python
logger = logging.getLogger(__name__)
logger.debug("Strike detected: %s confidence=%.2f", punch_type, conf)
```

---

## 10. Missing Unit Tests for Algorithm Code

**Problem:** `temporal_strike.py` contains a 3-layer kinematic punch-detection algorithm with 10+ configurable thresholds. With no unit tests, threshold changes or refactors have no safety net.

**Antipattern:** Merging changes to `temporal_strike.py` or any file under `fighterid_vision_engine/detection/` or `fighterid_vision_engine/pipeline/` without a corresponding test.

**Fix:** Create `tests/pipeline/test_temporal_strike.py` covering:
- Jab, cross, hook, uppercut detection with synthetic wrist-position sequences.
- Miss scenario (velocity below threshold).
- Cooldown enforcement (second strike within cooldown window must be suppressed).
- Threshold boundary conditions (just above / just below `STRIKE_SPEED_MS`).
