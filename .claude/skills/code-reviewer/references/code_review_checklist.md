# Code Review Checklist — Fighter-ID-Vision3D

Use this checklist when reviewing any PR or branch in this Python computer-vision project.

---

## 1. Security

- [ ] No credentials, API keys, or JWT tokens hardcoded in source files.
- [ ] `.env` is listed in `.gitignore` and never committed.
- [ ] `.env.example` uses placeholder values only (e.g. `https://your-project.supabase.co`), never real keys.
- [ ] Supabase URL and anon key are read exclusively from environment variables via `settings.py`.
- [ ] `settings.py` URL validation helper is used before any HTTP call.
- [ ] CI lint job (`lint.yml`) passes — it scans for `sb_publishable_*` keys and JWT patterns.

## 2. Threading & Concurrency

- [ ] All mutations of shared state in `FightersState` go through `FightersState._lock`.
- [ ] New worker threads are daemon threads (`thread.daemon = True`) or have an explicit shutdown signal.
- [ ] Camera capture threads (`CameraStream`) release the frame lock after every read/write cycle.
- [ ] No bare `time.sleep()` loops used as substitutes for proper synchronisation primitives.
- [ ] The heartbeat worker in `engine.py` cleanly exits when `stop()` is called (check the `_running` flag).

## 3. Error Handling

- [ ] No bare `except:` clauses — use `except Exception:` or a specific exception type.
- [ ] Camera failure raises an exception or logs a clear `ERROR`-level message; it does not silently return `None` frames.
- [ ] Supabase/HTTP calls wrap failures with at minimum `logging.error(...)` and do not swallow exceptions silently.
- [ ] API edge-function calls that may fail transiently include retry logic or are documented as fire-and-forget.
- [ ] `fight_manager.py` handles the case where `discover_fight_id()` returns `None`.

## 4. Type Safety

- [ ] All public functions and methods in `fighterid_vision_engine/` have parameter and return type annotations.
- [ ] No use of implicit `Any` types where a concrete type is known.
- [ ] `Optional[X]` (or `X | None`) is used where `None` is a valid return value.

## 5. Testing

- [ ] Every module under `fighterid_vision_engine/` has a corresponding `tests/test_<module>.py`.
- [ ] `temporal_strike.py` strike-detection logic has unit tests covering: jab, cross, hook, uppercut, miss, and cooldown cases.
- [ ] Supabase bridge tests mock the HTTP layer — no live network calls in CI.
- [ ] Tests cover the Hungarian tracker's RED/BLUE assignment stability across occlusion frames.
- [ ] New features include at least one happy-path and one failure-path test.

## 6. Performance

- [ ] Frame processing stays under the target latency budget (≤33 ms at 30 fps, ≤17 ms at 60 fps).
- [ ] ONNX model is loaded once at startup, not per frame.
- [ ] Rolling deque buffers in `temporal_strike.py` are bounded (`maxlen` set).
- [ ] No unbounded lists used as frame queues between threads — use `queue.Queue` with a `maxsize`.
- [ ] Heatmap and replay buffers do not grow unbounded over a full fight session.

## 7. Architecture & Modularity

- [ ] No duplicate class names across files (particularly `FighterIDAPI`).
- [ ] `vision_motor_v1.py` is not modified — it is legacy code pending removal.
- [ ] New vision-engine logic goes under `fighterid_vision_engine/pipeline/`, not in root-level files.
- [ ] `supabase_client.py` (legacy REST wrapper) is not used by new code; route through `fighterid_supabase_bridge.py`.
- [ ] File size stays under 500 LOC; split modules that exceed this.

## 8. Configuration

- [ ] New tuneable parameters are added to `.env.example` with a sensible default and a brief comment.
- [ ] `settings.py` reads and validates the new parameter; raw `os.getenv()` is not called outside `settings.py`.
- [ ] Physical thresholds (`STRIKE_SPEED_MS`, `PIX_PER_M`, etc.) are validated to be positive numbers.

## 9. Logging

- [ ] Library and engine modules use `logging.getLogger(__name__)`, not `print()`.
- [ ] Log levels are appropriate: `DEBUG` for per-frame data, `INFO` for lifecycle events, `WARNING`/`ERROR` for failures.
- [ ] No sensitive values (keys, PII) appear in log output.

## 10. Documentation

- [ ] Public classes and functions have docstrings explaining purpose, parameters, and return values.
- [ ] Significant algorithm choices (e.g. Hungarian assignment thresholds) include an inline comment with rationale.
- [ ] `CHANGELOG` or PR description notes breaking changes to the `.env` schema or API contract.
