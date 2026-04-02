# Code Review Report — Fighter-ID-Vision3D

_Generated: 2026-04-02 22:20 UTC_  
_Target: `/home/user/Fighter-ID-Vision3D`_

---

## Executive Summary

| Category | HIGH | MEDIUM | LOW | Total |
|----------|------|--------|-----|-------|
| Code Quality | 30 | 17 | 572 | 619 |
| PR Changes | 0 | 0 | 0 | 0 |
| **Combined** | **30** | **17** | **572** | **619** |

> **49** Python files scanned.

---

## High Priority Issues

These issues carry the highest risk and should be addressed before merging.

| Severity | File | Line | Issue |
|----------|------|------|-------|
| HIGH | `check_system.py` | 78 | Hardcoded Supabase URL appears hardcoded. Use environment variables instead. |
| HIGH | `fighterid_supabase_bridge.py` | 74 | Class `FighterIDAPI` defined in multiple files: fighterid_supabase_bridge.py:74, fighterid_vision_engine/pipeline/engine.py:112, vision_motor_v1.py:98. Consolidate to one location. |
| HIGH | `fighterid_vision_engine/camera/capture.py` | — | No test file found for `capture`. Expected `tests/test_capture.py`. Critical algorithm code needs unit tests. |
| HIGH | `fighterid_vision_engine/camera/capture.py` | 16 | Class `CameraStream` defined in multiple files: fighterid_vision_engine/camera/capture.py:16, vision_motor_v1.py:175. Consolidate to one location. |
| HIGH | `fighterid_vision_engine/config/settings.py` | — | No test file found for `settings`. Expected `tests/test_settings.py`. Critical algorithm code needs unit tests. |
| HIGH | `fighterid_vision_engine/detection/pose.py` | — | No test file found for `pose`. Expected `tests/test_pose.py`. Critical algorithm code needs unit tests. |
| HIGH | `fighterid_vision_engine/detection/pose.py` | 80 | Class `PoseDetector` defined in multiple files: fighterid_vision_engine/detection/pose.py:80, vision_motor_v1.py:246. Consolidate to one location. |
| HIGH | `fighterid_vision_engine/detection/tracker.py` | — | No test file found for `tracker`. Expected `tests/test_tracker.py`. Critical algorithm code needs unit tests. |
| HIGH | `fighterid_vision_engine/detection/tracker.py` | 153 | Class `SimpleTracker` defined in multiple files: fighterid_vision_engine/detection/tracker.py:153, vision_motor_v1.py:377. Consolidate to one location. |
| HIGH | `fighterid_vision_engine/events/factory.py` | — | No test file found for `factory`. Expected `tests/test_factory.py`. Critical algorithm code needs unit tests. |
| HIGH | `fighterid_vision_engine/events/models.py` | — | No test file found for `models`. Expected `tests/test_models.py`. Critical algorithm code needs unit tests. |
| HIGH | `fighterid_vision_engine/events/validators.py` | — | No test file found for `validators`. Expected `tests/test_validators.py`. Critical algorithm code needs unit tests. |
| HIGH | `fighterid_vision_engine/features/flags.py` | — | No test file found for `flags`. Expected `tests/test_flags.py`. Critical algorithm code needs unit tests. |
| HIGH | `fighterid_vision_engine/observability/logger.py` | — | No test file found for `logger`. Expected `tests/test_logger.py`. Critical algorithm code needs unit tests. |
| HIGH | `fighterid_vision_engine/pipeline/engine.py` | — | No test file found for `engine`. Expected `tests/test_engine.py`. Critical algorithm code needs unit tests. |
| HIGH | `fighterid_vision_engine/pipeline/engine.py` | 349 | Class `VisionMotorV1` defined in multiple files: fighterid_vision_engine/pipeline/engine.py:349, vision_motor_v1.py:487. Consolidate to one location. |
| HIGH | `fighterid_vision_engine/pipeline/fighters_state.py` | — | No test file found for `fighters_state`. Expected `tests/test_fighters_state.py`. Critical algorithm code needs unit tests. |
| HIGH | `fighterid_vision_engine/pipeline/heatmap.py` | — | No test file found for `heatmap`. Expected `tests/test_heatmap.py`. Critical algorithm code needs unit tests. |
| HIGH | `fighterid_vision_engine/pipeline/recorder.py` | — | No test file found for `recorder`. Expected `tests/test_recorder.py`. Critical algorithm code needs unit tests. |
| HIGH | `fighterid_vision_engine/pipeline/recorder.py` | 14 | Class `VideoRecorder` defined in multiple files: fighterid_vision_engine/pipeline/recorder.py:14, vision_motor_v1.py:460. Consolidate to one location. |
| HIGH | `fighterid_vision_engine/pipeline/replay.py` | — | No test file found for `replay`. Expected `tests/test_replay.py`. Critical algorithm code needs unit tests. |
| HIGH | `fighterid_vision_engine/pipeline/strike.py` | — | No test file found for `strike`. Expected `tests/test_strike.py`. Critical algorithm code needs unit tests. |
| HIGH | `fighterid_vision_engine/pipeline/strike.py` | 24 | Class `StrikeDetector` defined in multiple files: fighterid_vision_engine/pipeline/strike.py:24, vision_motor_v1.py:399. Consolidate to one location. |
| HIGH | `fighterid_vision_engine/pipeline/temporal_strike.py` | — | No test file found for `temporal_strike`. Expected `tests/test_temporal_strike.py`. Critical algorithm code needs unit tests. |
| HIGH | `fighterid_vision_engine/sync/retry_queue.py` | — | No test file found for `retry_queue`. Expected `tests/test_retry_queue.py`. Critical algorithm code needs unit tests. |
| HIGH | `supabase_client.py` | 7 | Hardcoded Supabase URL appears hardcoded. Use environment variables instead. |
| HIGH | `supabase_client.py` | 8 | Possible JWT token appears hardcoded. Use environment variables instead. |
| HIGH | `vision_motor_v1.py` | 62 | Hardcoded Supabase URL appears hardcoded. Use environment variables instead. |
| HIGH | `vision_motor_v1.py` | 64 | Possible JWT token appears hardcoded. Use environment variables instead. |
| HIGH | `vision_motor_v1.py` | 65 | Possible JWT token appears hardcoded. Use environment variables instead. |

## Medium Priority Issues

Address these in the current sprint or immediately after merging.

| Severity | File | Line | Issue |
|----------|------|------|-------|
| MEDIUM | `fight_manager.py` | — | File has a syntax error and could not be parsed. |
| MEDIUM | `fighterid_supabase_bridge.py` | 910 | File has 910 lines (>500). Consider splitting into smaller modules. |
| MEDIUM | `fighterid_vision_engine/main.py` | 22 | Bare `except:` catches all exceptions including KeyboardInterrupt/SystemExit. Use `except Exception:` or be specific. |
| MEDIUM | `fighterid_vision_engine/pipeline/engine.py` | 772 | File has 772 lines (>500). Consider splitting into smaller modules. |
| MEDIUM | `tests/test_regression.py` | 515 | File has 515 lines (>500). Consider splitting into smaller modules. |
| MEDIUM | `three_camera_ui.py` | 112 | Bare `except:` catches all exceptions including KeyboardInterrupt/SystemExit. Use `except Exception:` or be specific. |
| MEDIUM | `three_camera_ui.py` | 174 | Bare `except:` catches all exceptions including KeyboardInterrupt/SystemExit. Use `except Exception:` or be specific. |
| MEDIUM | `three_camera_ui.py` | 443 | Bare `except:` catches all exceptions including KeyboardInterrupt/SystemExit. Use `except Exception:` or be specific. |
| MEDIUM | `three_camera_ui.py` | 728 | Bare `except:` catches all exceptions including KeyboardInterrupt/SystemExit. Use `except Exception:` or be specific. |
| MEDIUM | `three_camera_ui.py` | 1115 | Bare `except:` catches all exceptions including KeyboardInterrupt/SystemExit. Use `except Exception:` or be specific. |
| MEDIUM | `three_camera_ui.py` | 1680 | Bare `except:` catches all exceptions including KeyboardInterrupt/SystemExit. Use `except Exception:` or be specific. |
| MEDIUM | `three_camera_ui.py` | 1728 | Bare `except:` catches all exceptions including KeyboardInterrupt/SystemExit. Use `except Exception:` or be specific. |
| MEDIUM | `three_camera_ui.py` | 1740 | File has 1740 lines (>500). Consider splitting into smaller modules. |
| MEDIUM | `tools/annotate_dataset.py` | 589 | File has 589 lines (>500). Consider splitting into smaller modules. |
| MEDIUM | `tools/calibrate_cameras.py` | 562 | File has 562 lines (>500). Consider splitting into smaller modules. |
| MEDIUM | `tools/tune_thresholds.py` | 541 | File has 541 lines (>500). Consider splitting into smaller modules. |
| MEDIUM | `vision_motor_v1.py` | 635 | File has 635 lines (>500). Consider splitting into smaller modules. |

## Low Priority Issues

<details>
<summary>Expand low-priority findings</summary>

| Severity | File | Line | Issue |
|----------|------|------|-------|
| LOW | `app.py` | 6 | Function `run_engine`: args missing annotations: fight_id, show; missing return type. |
| LOW | `app.py` | 6 | Function `run_engine` is missing a docstring. |
| LOW | `app.py` | 19 | Function `run_ui`: missing return type. |
| LOW | `app.py` | 19 | Function `run_ui` is missing a docstring. |
| LOW | `app.py` | 24 | Function `run_fight`: args missing annotations: show; missing return type. |
| LOW | `app.py` | 67 | Function `main`: missing return type. |
| LOW | `app.py` | 67 | Function `main` is missing a docstring. |
| LOW | `fighterid_supabase_bridge.py` | 74 | Class `FighterIDAPI` is missing a docstring. |
| LOW | `fighterid_supabase_bridge.py` | 135 | Function `fight_id`: missing return type. |
| LOW | `fighterid_supabase_bridge.py` | 135 | Function `fight_id` is missing a docstring. |
| LOW | `fighterid_supabase_bridge.py` | 137 | Function `fight_id`: args missing annotations: v; missing return type. |
| LOW | `fighterid_supabase_bridge.py` | 137 | Function `fight_id` is missing a docstring. |
| LOW | `fighterid_supabase_bridge.py` | 140 | Function `round_number`: missing return type. |
| LOW | `fighterid_supabase_bridge.py` | 140 | Function `round_number` is missing a docstring. |
| LOW | `fighterid_supabase_bridge.py` | 142 | Function `round_number`: args missing annotations: v; missing return type. |
| LOW | `fighterid_supabase_bridge.py` | 142 | Function `round_number` is missing a docstring. |
| LOW | `fighterid_supabase_bridge.py` | 159 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 176 | Function `fetch_active_session`: missing return type. |
| LOW | `fighterid_supabase_bridge.py` | 193 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 204 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 210 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 227 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 229 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 231 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 260 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 265 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 271 | Function `list_fighter_profiles`: missing return type. |
| LOW | `fighterid_supabase_bridge.py` | 289 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 318 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 378 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 382 | Function `create_fight_session`: args missing annotations: red_id, blue_id, total_rounds, model_version; missing return type. |
| LOW | `fighterid_supabase_bridge.py` | 394 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 420 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 426 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 429 | Function `start_session_test`: missing return type. |
| LOW | `fighterid_supabase_bridge.py` | 442 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 459 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 461 | Function `connect_engine`: args missing annotations: session_token; missing return type. |
| LOW | `fighterid_supabase_bridge.py` | 476 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 486 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 491 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 506 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 513 | Function `start_session`: args missing annotations: fight_id, fighter_a_name, fighter_b_name, mode; missing return type. |
| LOW | `fighterid_supabase_bridge.py` | 513 | Function `start_session` is missing a docstring. |
| LOW | `fighterid_supabase_bridge.py` | 557 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 559 | Function `end_fight`: args missing annotations: winner, red_stats, blue_stats, round_results; missing return type. |
| LOW | `fighterid_supabase_bridge.py` | 559 | Function `end_fight` is missing a docstring. |
| LOW | `fighterid_supabase_bridge.py` | 561 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 580 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 583 | Function `advance_round`: args missing annotations: round_number; missing return type. |
| LOW | `fighterid_supabase_bridge.py` | 583 | Function `advance_round` is missing a docstring. |
| LOW | `fighterid_supabase_bridge.py` | 586 | Function `resolve_fighter`: args missing annotations: track_id; missing return type. |
| LOW | `fighterid_supabase_bridge.py` | 597 | Function `send_event`: args missing annotations: fighter_id, confidence; missing return type. |
| LOW | `fighterid_supabase_bridge.py` | 604 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 621 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 623 | Function `listen_fight_changes`: missing return type. |
| LOW | `fighterid_supabase_bridge.py` | 633 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 636 | Function `handle`: args missing annotations: payload; missing return type. |
| LOW | `fighterid_supabase_bridge.py` | 636 | Function `handle` is missing a docstring. |
| LOW | `fighterid_supabase_bridge.py` | 640 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 646 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 655 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 660 | Function `send`: args missing annotations: fighter_id, punch_type, speed, extension, hit, face_hit, body_hit, elbow_angle; missing return type. |
| LOW | `fighterid_supabase_bridge.py` | 660 | Function `send` is missing a docstring. |
| LOW | `fighterid_supabase_bridge.py` | 740 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 743 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 759 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 763 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 802 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 803 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 804 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 806 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 857 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 862 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 875 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_supabase_bridge.py` | 901 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/camera/capture.py` | 48 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/camera/capture.py` | 52 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/camera/capture.py` | 54 | Function `start` is missing a docstring. |
| LOW | `fighterid_vision_engine/camera/capture.py` | 76 | Function `read`: missing return type. |
| LOW | `fighterid_vision_engine/camera/capture.py` | 81 | Function `is_open` is missing a docstring. |
| LOW | `fighterid_vision_engine/camera/capture.py` | 84 | Function `stop` is missing a docstring. |
| LOW | `fighterid_vision_engine/config/settings.py` | 22 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/config/settings.py` | 24 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/config/settings.py` | 37 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/detection/pose.py` | 35 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/detection/pose.py` | 44 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/detection/pose.py` | 47 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/detection/pose.py` | 53 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/detection/pose.py` | 55 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/detection/pose.py` | 57 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/detection/pose.py` | 59 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/detection/pose.py` | 61 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/detection/pose.py` | 118 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/detection/pose.py` | 122 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/detection/pose.py` | 123 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/detection/pose.py` | 124 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/detection/pose.py` | 131 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/detection/pose.py` | 135 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/detection/pose.py` | 138 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/detection/pose.py` | 144 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/detection/pose.py` | 148 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/detection/pose.py` | 157 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/detection/pose.py` | 201 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/detection/tracker.py` | 160 | Function `assign` is missing a docstring. |
| LOW | `fighterid_vision_engine/events/factory.py` | 45 | Function `hit_detected` is missing a docstring. |
| LOW | `fighterid_vision_engine/events/factory.py` | 78 | Function `knockdown` is missing a docstring. |
| LOW | `fighterid_vision_engine/events/factory.py` | 108 | Function `round_start` is missing a docstring. |
| LOW | `fighterid_vision_engine/events/factory.py` | 129 | Function `round_end` is missing a docstring. |
| LOW | `fighterid_vision_engine/events/factory.py` | 150 | Function `fighter_identified` is missing a docstring. |
| LOW | `fighterid_vision_engine/events/factory.py` | 173 | Function `invalid_hit` is missing a docstring. |
| LOW | `fighterid_vision_engine/events/factory.py` | 203 | Function `referee_intervention` is missing a docstring. |
| LOW | `fighterid_vision_engine/events/models.py` | 106 | Function `to_dict` is missing a docstring. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 96 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 99 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 101 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 127 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 128 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 143 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 168 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 169 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 178 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 194 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 215 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 217 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 243 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 245 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 266 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 268 | Function `resolve_fighter`: missing return type. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 364 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 399 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 401 | Function `start` is missing a docstring. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 424 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 433 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 437 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 446 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 458 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 464 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 477 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 494 | TODO comment: # Replay: buffer todo frame antes de procesar |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 522 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 576 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 757 | Function `stop` is missing a docstring. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 771 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 772 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/fighters_state.py` | 57 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/recorder.py` | 27 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/recorder.py` | 29 | Function `write` is missing a docstring. |
| LOW | `fighterid_vision_engine/pipeline/recorder.py` | 33 | Function `stop` is missing a docstring. |
| LOW | `fighterid_vision_engine/pipeline/recorder.py` | 35 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/replay.py` | 107 | Function `is_playing` is missing a docstring. |
| LOW | `fighterid_vision_engine/pipeline/strike.py` | 38 | Function `detect`: missing return type. |
| LOW | `fighterid_vision_engine/pipeline/strike.py` | 38 | Function `detect` is missing a docstring. |
| LOW | `fighterid_vision_engine/scoring/rules_engine.py` | 262 | Function `evaluate` is missing a docstring. |
| LOW | `fighterid_vision_engine/sync/event_producer.py` | 93 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/sync/event_producer.py` | 192 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/sync/retry_queue.py` | 120 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/sync/retry_queue.py` | 131 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/sync/retry_queue.py` | 149 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `find_unused.py` | 14 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `find_unused.py` | 18 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `main.py` | 35 | Function `main` is missing a docstring. |
| LOW | `supabase_client.py` | 16 | Function `formatear_peleador`: args missing annotations: f; missing return type. |
| LOW | `supabase_client.py` | 16 | Function `formatear_peleador` is missing a docstring. |
| LOW | `supabase_client.py` | 34 | Function `buscar_peleador`: args missing annotations: nombre; missing return type. |
| LOW | `supabase_client.py` | 34 | Function `buscar_peleador` is missing a docstring. |
| LOW | `supabase_client.py` | 46 | Function `seleccionar_peleador`: missing return type. |
| LOW | `supabase_client.py` | 46 | Function `seleccionar_peleador` is missing a docstring. |
| LOW | `supabase_client.py` | 52 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `supabase_client.py` | 55 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `supabase_client.py` | 58 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `supabase_client.py` | 64 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `supabase_client.py` | 70 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `supabase_client.py` | 79 | Function `crear_contexto_pelea`: args missing annotations: fighter_a, fighter_b; missing return type. |
| LOW | `supabase_client.py` | 79 | Function `crear_contexto_pelea` is missing a docstring. |
| LOW | `supabase_client.py` | 91 | Function `iniciar_camara`: args missing annotations: contexto; missing return type. |
| LOW | `supabase_client.py` | 91 | Function `iniciar_camara` is missing a docstring. |
| LOW | `supabase_client.py` | 95 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `supabase_client.py` | 98 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `supabase_client.py` | 140 | Function `main`: missing return type. |
| LOW | `supabase_client.py` | 140 | Function `main` is missing a docstring. |
| LOW | `supabase_client.py` | 141 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `supabase_client.py` | 142 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `supabase_client.py` | 143 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `supabase_client.py` | 148 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `supabase_client.py` | 149 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `supabase_client.py` | 150 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `supabase_client.py` | 154 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tests/test_event_model.py` | 23 | Class `TestCombatEventImmutability` is missing a docstring. |
| LOW | `tests/test_event_model.py` | 24 | Function `test_event_is_frozen` is missing a docstring. |
| LOW | `tests/test_event_model.py` | 33 | Function `test_metadata_is_accessible` is missing a docstring. |
| LOW | `tests/test_event_model.py` | 43 | Function `test_to_dict_is_serializable` is missing a docstring. |
| LOW | `tests/test_event_model.py` | 56 | Class `TestCombatEventFactory` is missing a docstring. |
| LOW | `tests/test_event_model.py` | 57 | Function `test_hit_detected_has_required_fields` is missing a docstring. |
| LOW | `tests/test_event_model.py` | 71 | Function `test_knockdown_event` is missing a docstring. |
| LOW | `tests/test_event_model.py` | 79 | Function `test_round_start_event` is missing a docstring. |
| LOW | `tests/test_event_model.py` | 89 | Function `test_round_end_event` is missing a docstring. |
| LOW | `tests/test_event_model.py` | 96 | Function `test_fighter_identified_event` is missing a docstring. |
| LOW | `tests/test_event_model.py` | 104 | Function `test_invalid_hit_event` is missing a docstring. |
| LOW | `tests/test_event_model.py` | 113 | Function `test_referee_intervention_event` is missing a docstring. |
| LOW | `tests/test_event_model.py` | 123 | Class `TestEventValidation` is missing a docstring. |
| LOW | `tests/test_event_model.py` | 133 | Function `test_valid_event_passes` is missing a docstring. |
| LOW | `tests/test_event_model.py` | 137 | Function `test_empty_fight_id_fails` is missing a docstring. |
| LOW | `tests/test_event_model.py` | 146 | Function `test_confidence_out_of_range_fails` is missing a docstring. |
| LOW | `tests/test_event_model.py` | 161 | Function `test_negative_confidence_fails` is missing a docstring. |
| LOW | `tests/test_event_model.py` | 174 | Function `test_invalid_corner_fails` is missing a docstring. |
| LOW | `tests/test_event_model.py` | 189 | Function `test_invalid_event_type_fails` is missing a docstring. |
| LOW | `tests/test_event_model.py` | 202 | Function `test_missing_metadata_fields_fails` is missing a docstring. |
| LOW | `tests/test_event_model.py` | 215 | Function `test_invalid_version_format_fails` is missing a docstring. |
| LOW | `tests/test_event_model.py` | 230 | Function `test_invalid_timestamp_fails` is missing a docstring. |
| LOW | `tests/test_event_producer.py` | 39 | Class `TestRetryQueue` is missing a docstring. |
| LOW | `tests/test_event_producer.py` | 40 | Function `test_enqueue_writes_to_buffer` is missing a docstring. |
| LOW | `tests/test_event_producer.py` | 57 | Function `test_successful_send_removes_from_buffer` is missing a docstring. |
| LOW | `tests/test_event_producer.py` | 67 | Function `mock_send`: args missing annotations: e; missing return type. |
| LOW | `tests/test_event_producer.py` | 67 | Function `mock_send` is missing a docstring. |
| LOW | `tests/test_event_producer.py` | 80 | Function `test_pending_count_reflects_buffer` is missing a docstring. |
| LOW | `tests/test_event_producer.py` | 91 | Class `TestEventProducer` is missing a docstring. |
| LOW | `tests/test_regression.py` | 151 | Function `test_all_events_have_fight_id` is missing a docstring. |
| LOW | `tests/test_regression.py` | 156 | Function `test_all_events_are_valid` is missing a docstring. |
| LOW | `tests/test_regression.py` | 161 | Function `test_12_rounds_scored` is missing a docstring. |
| LOW | `tests/test_regression.py` | 165 | Function `test_no_duplicate_round_numbers` is missing a docstring. |
| LOW | `tests/test_regression.py` | 188 | Function `test_all_round_scores_have_versions` is missing a docstring. |
| LOW | `tests/test_regression.py` | 256 | Function `test_no_event_has_empty_fight_id` is missing a docstring. |
| LOW | `tests/test_regression.py` | 275 | Function `test_knockdown_overrides_round_winner` is missing a docstring. |
| LOW | `tests/test_regression.py` | 293 | Function `test_knockdown_event_is_valid` is missing a docstring. |
| LOW | `tests/test_regression.py` | 297 | Function `test_knockdown_event_has_correct_type` is missing a docstring. |
| LOW | `tests/test_regression.py` | 301 | Function `test_knockdown_processed_correctly` is missing a docstring. |
| LOW | `tests/test_regression.py` | 345 | Function `test_supabase_failure_saves_to_buffer` is missing a docstring. |
| LOW | `tests/test_regression.py` | 461 | Class `TestDataIntegrity` is missing a docstring. |
| LOW | `tests/test_rules_engine.py` | 53 | Class `TestConfidenceFilter` is missing a docstring. |
| LOW | `tests/test_rules_engine.py` | 54 | Function `test_high_confidence_accepted` is missing a docstring. |
| LOW | `tests/test_rules_engine.py` | 61 | Function `test_exact_threshold_accepted` is missing a docstring. |
| LOW | `tests/test_rules_engine.py` | 67 | Function `test_below_threshold_rejected` is missing a docstring. |
| LOW | `tests/test_rules_engine.py` | 74 | Function `test_zero_confidence_rejected` is missing a docstring. |
| LOW | `tests/test_rules_engine.py` | 81 | Class `TestTargetZoneFilter` is missing a docstring. |
| LOW | `tests/test_rules_engine.py` | 82 | Function `test_head_target_accepted` is missing a docstring. |
| LOW | `tests/test_rules_engine.py` | 88 | Function `test_body_target_accepted` is missing a docstring. |
| LOW | `tests/test_rules_engine.py` | 94 | Function `test_unknown_target_rejected` is missing a docstring. |
| LOW | `tests/test_rules_engine.py` | 101 | Function `test_empty_target_rejected` is missing a docstring. |
| LOW | `tests/test_rules_engine.py` | 108 | Class `TestDeduplification` is missing a docstring. |
| LOW | `tests/test_rules_engine.py` | 154 | Class `TestScoring` is missing a docstring. |
| LOW | `tests/test_rules_engine.py` | 155 | Function `test_clean_hit_gives_1_point` is missing a docstring. |
| LOW | `tests/test_rules_engine.py` | 162 | Function `test_dominant_hit_gives_2_points` is missing a docstring. |
| LOW | `tests/test_rules_engine.py` | 169 | Function `test_knockdown_gives_10_points` is missing a docstring. |
| LOW | `tests/test_rules_engine.py` | 180 | Function `test_non_scoring_event_gives_0_points` is missing a docstring. |
| LOW | `tests/test_rules_engine.py` | 190 | Class `TestComputeRoundScore` is missing a docstring. |
| LOW | `tests/test_rules_engine.py` | 242 | Function `test_empty_events_gives_zero_score` is missing a docstring. |
| LOW | `three_camera_ui.py` | 115 | Function `detect_cameras`: missing return type. |
| LOW | `three_camera_ui.py` | 265 | Class `StereoFuser` is missing a docstring. |
| LOW | `three_camera_ui.py` | 274 | Function `triangulate`: args missing annotations: u_a, v_a, u_b, v_b; missing return type. |
| LOW | `three_camera_ui.py` | 308 | Function `depth_from_single`: args missing annotations: u, v, z; missing return type. |
| LOW | `three_camera_ui.py` | 308 | Function `depth_from_single` is missing a docstring. |
| LOW | `three_camera_ui.py` | 311 | Function `fuse_keypoints`: args missing annotations: kp_a, kp_b, cf_a, cf_b; missing return type. |
| LOW | `three_camera_ui.py` | 311 | Function `fuse_keypoints` is missing a docstring. |
| LOW | `three_camera_ui.py` | 337 | Class `InferThread` is missing a docstring. |
| LOW | `three_camera_ui.py` | 343 | Function `submit`: args missing annotations: frame; missing return type. |
| LOW | `three_camera_ui.py` | 343 | Function `submit` is missing a docstring. |
| LOW | `three_camera_ui.py` | 347 | Function `result`: missing return type. |
| LOW | `three_camera_ui.py` | 347 | Function `result` is missing a docstring. |
| LOW | `three_camera_ui.py` | 350 | Function `stop`: missing return type. |
| LOW | `three_camera_ui.py` | 350 | Function `stop` is missing a docstring. |
| LOW | `three_camera_ui.py` | 352 | Function `run`: missing return type. |
| LOW | `three_camera_ui.py` | 352 | Function `run` is missing a docstring. |
| LOW | `three_camera_ui.py` | 389 | Function `read`: missing return type. |
| LOW | `three_camera_ui.py` | 389 | Function `read` is missing a docstring. |
| LOW | `three_camera_ui.py` | 393 | Function `stop`: missing return type. |
| LOW | `three_camera_ui.py` | 393 | Function `stop` is missing a docstring. |
| LOW | `three_camera_ui.py` | 396 | Function `run`: missing return type. |
| LOW | `three_camera_ui.py` | 396 | Function `run` is missing a docstring. |
| LOW | `three_camera_ui.py` | 413 | Function `glow`: args missing annotations: img, c, r, col, n; missing return type. |
| LOW | `three_camera_ui.py` | 413 | Function `glow` is missing a docstring. |
| LOW | `three_camera_ui.py` | 417 | Function `classify_glove`: args missing annotations: frame, x, y, r; missing return type. |
| LOW | `three_camera_ui.py` | 417 | Function `classify_glove` is missing a docstring. |
| LOW | `three_camera_ui.py` | 430 | Function `bare_torso`: args missing annotations: frame, kp; missing return type. |
| LOW | `three_camera_ui.py` | 430 | Function `bare_torso` is missing a docstring. |
| LOW | `three_camera_ui.py` | 446 | Function `torso_center_3d`: args missing annotations: pts3d; missing return type. |
| LOW | `three_camera_ui.py` | 446 | Function `torso_center_3d` is missing a docstring. |
| LOW | `three_camera_ui.py` | 451 | Function `dist3d`: args missing annotations: a, b; missing return type. |
| LOW | `three_camera_ui.py` | 451 | Function `dist3d` is missing a docstring. |
| LOW | `three_camera_ui.py` | 458 | Class `HeadTracker` is missing a docstring. |
| LOW | `three_camera_ui.py` | 464 | Function `reset`: missing return type. |
| LOW | `three_camera_ui.py` | 464 | Function `reset` is missing a docstring. |
| LOW | `three_camera_ui.py` | 469 | Function `update`: args missing annotations: pos3d, pos2d, t; missing return type. |
| LOW | `three_camera_ui.py` | 469 | Function `update` is missing a docstring. |
| LOW | `three_camera_ui.py` | 483 | Function `agility`: missing return type. |
| LOW | `three_camera_ui.py` | 483 | Function `agility` is missing a docstring. |
| LOW | `three_camera_ui.py` | 489 | Class `Fighter` is missing a docstring. |
| LOW | `three_camera_ui.py` | 501 | Function `reset`: missing return type. |
| LOW | `three_camera_ui.py` | 501 | Function `reset` is missing a docstring. |
| LOW | `three_camera_ui.py` | 510 | Function `accuracy`: missing return type. |
| LOW | `three_camera_ui.py` | 510 | Function `accuracy` is missing a docstring. |
| LOW | `three_camera_ui.py` | 528 | Function `update_punch`: args missing annotations: wp3, left, sp3, t; missing return type. |
| LOW | `three_camera_ui.py` | 528 | Function `update_punch` is missing a docstring. |
| LOW | `three_camera_ui.py` | 593 | Class `RoleDetector` is missing a docstring. |
| LOW | `three_camera_ui.py` | 604 | Function `update`: args missing annotations: pid, w_ok, r_ok, b_ok; missing return type. |
| LOW | `three_camera_ui.py` | 604 | Function `update` is missing a docstring. |
| LOW | `three_camera_ui.py` | 609 | Function `try_confirm`: missing return type. |
| LOW | `three_camera_ui.py` | 609 | Function `try_confirm` is missing a docstring. |
| LOW | `three_camera_ui.py` | 629 | Function `clear`: missing return type. |
| LOW | `three_camera_ui.py` | 629 | Function `clear` is missing a docstring. |
| LOW | `three_camera_ui.py` | 633 | Function `force_test`: args missing annotations: pid; missing return type. |
| LOW | `three_camera_ui.py` | 633 | Function `force_test` is missing a docstring. |
| LOW | `three_camera_ui.py` | 634 | Function `force_red`: args missing annotations: pid; missing return type. |
| LOW | `three_camera_ui.py` | 634 | Function `force_red` is missing a docstring. |
| LOW | `three_camera_ui.py` | 637 | Function `force_blue`: args missing annotations: pid; missing return type. |
| LOW | `three_camera_ui.py` | 637 | Function `force_blue` is missing a docstring. |
| LOW | `three_camera_ui.py` | 642 | Function `ready`: missing return type. |
| LOW | `three_camera_ui.py` | 642 | Function `ready` is missing a docstring. |
| LOW | `three_camera_ui.py` | 649 | Class `VisionEngine` is missing a docstring. |
| LOW | `three_camera_ui.py` | 700 | Function `tm`: missing return type. |
| LOW | `three_camera_ui.py` | 700 | Function `tm` is missing a docstring. |
| LOW | `three_camera_ui.py` | 790 | Function `cmd_start`: missing return type. |
| LOW | `three_camera_ui.py` | 790 | Function `cmd_start` is missing a docstring. |
| LOW | `three_camera_ui.py` | 799 | Function `cmd_pause`: missing return type. |
| LOW | `three_camera_ui.py` | 799 | Function `cmd_pause` is missing a docstring. |
| LOW | `three_camera_ui.py` | 806 | Function `cmd_end_round`: missing return type. |
| LOW | `three_camera_ui.py` | 806 | Function `cmd_end_round` is missing a docstring. |
| LOW | `three_camera_ui.py` | 810 | Function `cmd_force_test`: args missing annotations: pid; missing return type. |
| LOW | `three_camera_ui.py` | 810 | Function `cmd_force_test` is missing a docstring. |
| LOW | `three_camera_ui.py` | 814 | Function `cmd_force_red`: args missing annotations: pid; missing return type. |
| LOW | `three_camera_ui.py` | 814 | Function `cmd_force_red` is missing a docstring. |
| LOW | `three_camera_ui.py` | 818 | Function `cmd_force_blue`: args missing annotations: pid; missing return type. |
| LOW | `three_camera_ui.py` | 818 | Function `cmd_force_blue` is missing a docstring. |
| LOW | `three_camera_ui.py` | 822 | Function `cmd_clear`: missing return type. |
| LOW | `three_camera_ui.py` | 822 | Function `cmd_clear` is missing a docstring. |
| LOW | `three_camera_ui.py` | 823 | Function `cmd_stop`: missing return type. |
| LOW | `three_camera_ui.py` | 823 | Function `cmd_stop` is missing a docstring. |
| LOW | `three_camera_ui.py` | 825 | Function `get_frames`: missing return type. |
| LOW | `three_camera_ui.py` | 825 | Function `get_frames` is missing a docstring. |
| LOW | `three_camera_ui.py` | 828 | Function `get_stats`: missing return type. |
| LOW | `three_camera_ui.py` | 828 | Function `get_stats` is missing a docstring. |
| LOW | `three_camera_ui.py` | 831 | Function `get_logs`: missing return type. |
| LOW | `three_camera_ui.py` | 831 | Function `get_logs` is missing a docstring. |
| LOW | `three_camera_ui.py` | 835 | Function `run`: missing return type. |
| LOW | `three_camera_ui.py` | 835 | Function `run` is missing a docstring. |
| LOW | `three_camera_ui.py` | 836 | Function `open_cap`: args missing annotations: idx, fps; missing return type. |
| LOW | `three_camera_ui.py` | 836 | Function `open_cap` is missing a docstring. |
| LOW | `three_camera_ui.py` | 945 | Function `safe_plot`: args missing annotations: last, frame; missing return type. |
| LOW | `three_camera_ui.py` | 945 | Function `safe_plot` is missing a docstring. |
| LOW | `three_camera_ui.py` | 1151 | Function `hud`: args missing annotations: img, label, lc; missing return type. |
| LOW | `three_camera_ui.py` | 1151 | Function `hud` is missing a docstring. |
| LOW | `three_camera_ui.py` | 1356 | Class `StatCard` is missing a docstring. |
| LOW | `three_camera_ui.py` | 1369 | Function `set`: args missing annotations: value; missing return type. |
| LOW | `three_camera_ui.py` | 1369 | Function `set` is missing a docstring. |
| LOW | `three_camera_ui.py` | 1374 | Class `FighterIDApp` is missing a docstring. |
| LOW | `three_camera_ui.py` | 1435 | Function `sep`: missing return type. |
| LOW | `three_camera_ui.py` | 1435 | Function `sep` is missing a docstring. |
| LOW | `three_camera_ui.py` | 1436 | Function `lbl`: args missing annotations: t; missing return type. |
| LOW | `three_camera_ui.py` | 1436 | Function `lbl` is missing a docstring. |
| LOW | `three_camera_ui.py` | 1632 | Function `upd`: args missing annotations: cards, data; missing return type. |
| LOW | `three_camera_ui.py` | 1632 | Function `upd` is missing a docstring. |
| LOW | `tools/annotate_dataset.py` | 111 | Class `Annotation` is missing a docstring. |
| LOW | `tools/annotate_dataset.py` | 122 | Function `is_complete` is missing a docstring. |
| LOW | `tools/annotate_dataset.py` | 125 | Function `duration_frames` is missing a docstring. |
| LOW | `tools/annotate_dataset.py` | 130 | Function `to_dict` is missing a docstring. |
| LOW | `tools/annotate_dataset.py` | 145 | Class `VideoAnnotator` is missing a docstring. |
| LOW | `tools/annotate_dataset.py` | 173 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/annotate_dataset.py` | 179 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/annotate_dataset.py` | 334 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/annotate_dataset.py` | 358 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/annotate_dataset.py` | 360 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/annotate_dataset.py` | 370 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/annotate_dataset.py` | 371 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/annotate_dataset.py` | 373 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/annotate_dataset.py` | 374 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/annotate_dataset.py` | 437 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/annotate_dataset.py` | 442 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/annotate_dataset.py` | 445 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/annotate_dataset.py` | 448 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/annotate_dataset.py` | 453 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/annotate_dataset.py` | 458 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/annotate_dataset.py` | 462 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/annotate_dataset.py` | 466 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/annotate_dataset.py` | 470 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/annotate_dataset.py` | 474 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/annotate_dataset.py` | 479 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/annotate_dataset.py` | 483 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/annotate_dataset.py` | 490 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/annotate_dataset.py` | 495 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/annotate_dataset.py` | 498 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/annotate_dataset.py` | 509 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/annotate_dataset.py` | 524 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/annotate_dataset.py` | 533 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/annotate_dataset.py` | 534 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/annotate_dataset.py` | 535 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/annotate_dataset.py` | 536 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/annotate_dataset.py` | 537 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/annotate_dataset.py` | 539 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/annotate_dataset.py` | 540 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/annotate_dataset.py` | 542 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/annotate_dataset.py` | 546 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/annotate_dataset.py` | 548 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/annotate_dataset.py` | 553 | Function `parse_args`: missing return type. |
| LOW | `tools/annotate_dataset.py` | 553 | Function `parse_args` is missing a docstring. |
| LOW | `tools/annotate_dataset.py` | 565 | Function `main`: missing return type. |
| LOW | `tools/annotate_dataset.py` | 565 | Function `main` is missing a docstring. |
| LOW | `tools/annotate_dataset.py` | 570 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/annotate_dataset.py` | 582 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 73 | Function `draw_overlay`: args missing annotations: corners. |
| LOW | `tools/calibrate_cameras.py` | 129 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 130 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 131 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 136 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 151 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 160 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 164 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 166 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 170 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 198 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 199 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 200 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 236 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 244 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 248 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 252 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 254 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 258 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 270 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 273 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 275 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 277 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 279 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 295 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 310 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 312 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 314 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 317 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 341 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 342 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 347 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 348 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 349 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 351 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 353 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 355 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 356 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 357 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 358 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 379 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 385 | Function `parse_args`: missing return type. |
| LOW | `tools/calibrate_cameras.py` | 385 | Function `parse_args` is missing a docstring. |
| LOW | `tools/calibrate_cameras.py` | 407 | Function `main`: missing return type. |
| LOW | `tools/calibrate_cameras.py` | 407 | Function `main` is missing a docstring. |
| LOW | `tools/calibrate_cameras.py` | 420 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 421 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 422 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 423 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 424 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 425 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 426 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 443 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 456 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 459 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 462 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 470 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 485 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 515 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/calibrate_cameras.py` | 552 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 81 | Function `compute_f1` is missing a docstring. |
| LOW | `tools/tune_thresholds.py` | 171 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 180 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 248 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 282 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 285 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 298 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 299 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 300 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 301 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 302 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 304 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 306 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 307 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 308 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 309 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 310 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 311 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 317 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 318 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 319 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 320 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 322 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 332 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 333 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 334 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 336 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 339 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 346 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 347 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 348 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 349 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 350 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 351 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 352 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 358 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 359 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 360 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 362 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 364 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 368 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 369 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 370 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 371 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 372 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 378 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 379 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 380 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 382 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 383 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 384 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 385 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 387 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 388 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 408 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 414 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 436 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 441 | Function `parse_args`: missing return type. |
| LOW | `tools/tune_thresholds.py` | 441 | Function `parse_args` is missing a docstring. |
| LOW | `tools/tune_thresholds.py` | 464 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 497 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 504 | Function `main`: missing return type. |
| LOW | `tools/tune_thresholds.py` | 504 | Function `main` is missing a docstring. |
| LOW | `tools/tune_thresholds.py` | 509 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 512 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 520 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `tools/tune_thresholds.py` | 525 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `vision_motor_v1.py` | 46 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `vision_motor_v1.py` | 50 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `vision_motor_v1.py` | 53 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `vision_motor_v1.py` | 55 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `vision_motor_v1.py` | 57 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `vision_motor_v1.py` | 137 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `vision_motor_v1.py` | 138 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `vision_motor_v1.py` | 165 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `vision_motor_v1.py` | 167 | Function `resolve_fighter`: missing return type. |
| LOW | `vision_motor_v1.py` | 204 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `vision_motor_v1.py` | 208 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `vision_motor_v1.py` | 210 | Function `start` is missing a docstring. |
| LOW | `vision_motor_v1.py` | 229 | Function `read`: missing return type. |
| LOW | `vision_motor_v1.py` | 234 | Function `is_open` is missing a docstring. |
| LOW | `vision_motor_v1.py` | 237 | Function `stop` is missing a docstring. |
| LOW | `vision_motor_v1.py` | 276 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `vision_motor_v1.py` | 279 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `vision_motor_v1.py` | 282 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `vision_motor_v1.py` | 288 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `vision_motor_v1.py` | 292 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `vision_motor_v1.py` | 301 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `vision_motor_v1.py` | 409 | Function `detect`: missing return type. |
| LOW | `vision_motor_v1.py` | 473 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `vision_motor_v1.py` | 475 | Function `write` is missing a docstring. |
| LOW | `vision_motor_v1.py` | 479 | Function `stop` is missing a docstring. |
| LOW | `vision_motor_v1.py` | 481 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `vision_motor_v1.py` | 503 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `vision_motor_v1.py` | 514 | Function `start` is missing a docstring. |
| LOW | `vision_motor_v1.py` | 515 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `vision_motor_v1.py` | 523 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `vision_motor_v1.py` | 532 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `vision_motor_v1.py` | 563 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `vision_motor_v1.py` | 571 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `vision_motor_v1.py` | 575 | Function `stop` is missing a docstring. |
| LOW | `vision_motor_v1.py` | 581 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `vision_motor_v1.py` | 582 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `vision_motor_v1.py` | 588 | Function `main` is missing a docstring. |
| LOW | `vision_motor_v1.py` | 609 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `vision_motor_v1.py` | 610 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `vision_motor_v1.py` | 611 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `vision_motor_v1.py` | 612 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `vision_motor_v1.py` | 613 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `vision_motor_v1.py` | 626 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `vision_motor_v1.py` | 628 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `vision_sync.py` | 37 | Function `crear_pelea`: args missing annotations: event_id, fighter_a_id, fighter_b_id; missing return type. |
| LOW | `vision_sync.py` | 82 | Function `iniciar_sesion`: args missing annotations: device_id, fight_id; missing return type. |
| LOW | `vision_sync.py` | 118 | Function `enviar_evento`: args missing annotations: device_id, fight_id, fighter_id, tipo, confidence; missing return type. |

</details>

---

## PR Changes

**Branch:** `claude/code-review-audit-rKJjQ`  
**Base:** `a2bf65d74138`  
**Changes:** 0 files, +0 / -0 lines

### File Risk Assessment

| Risk | File |
|------|------|

---

## Positive Observations

- Modular vision engine layout under `fighterid_vision_engine/` with clear submodule boundaries (camera, detection, pipeline, config).
- GPU inference with automatic fallback chain: DirectML → CUDA → CPU, ensuring broad hardware compatibility.
- Thread-safe camera capture (`CameraStream`) with per-frame locking and graceful backend fallback.
- CI/CD pipeline (`.github/workflows/lint.yml`) actively scans for hardcoded credentials and validates syntax on every push.
- Configuration centralised in `settings.py` with URL-validation helpers, sourced from `.env` via `python-dotenv`.
- 3-layer temporal strike detection (`temporal_strike.py`) provides a well-structured kinematic analysis pipeline.
- Hungarian algorithm tracker (`tracker.py`) maintains stable RED/BLUE fighter identity across occlusions.

---

## Manual Review Findings

The following issues were identified through manual inspection and are not captured by automated static analysis:

### HIGH

| File | Issue |
|------|-------|
| `.env.example` | Contains a real Supabase project URL (`https://eeshomcqztvjkvycdwi.supabase.co`) and a real anon key. `.env.example` is committed to git and publicly visible. Replace all values with clearly-fake placeholders (e.g. `https://your-project.supabase.co`, `your-anon-key-here`). |

### MEDIUM

| Area | Issue |
|------|-------|
| `fighterid_supabase_bridge.py` — threading | Three concurrent worker threads (event worker, session manager, heartbeat) share state with minimal documentation. Thread startup order and shutdown protocol are not documented. Risk of race conditions on `_session_id` and `_fight_id` if workers start before initialisation completes. |
| `requirements.txt` — reproducibility | No lock file (`pip-tools` `.txt` pin, `poetry.lock`, or `Pipfile.lock`). Unpinned transitive dependencies mean `pip install` can silently upgrade/downgrade packages, breaking inference or Supabase client behaviour across environments. |

### LOW (CI/CD Gaps)

| Gap | Recommendation |
|-----|----------------|
| No Python linter | Add `ruff` (or `flake8` + `black`) to `.github/workflows/lint.yml` to enforce style and catch obvious errors. |
| No type checker | Add `mypy --strict` (or at minimum `mypy` on `fighterid_vision_engine/`) to CI to catch `None`-dereference and mismatched return types. |
| No security scanner | Add `bandit -r fighterid_vision_engine/` and `pip-audit` to CI. `bandit` will catch subprocess injection, hardcoded passwords, and insecure random usage. `pip-audit` will flag CVEs in dependencies. |
| CI scope too narrow | `.github/workflows/lint.yml` only syntax-checks 4 explicit files. Extend to `python -m py_compile $(git ls-files '*.py')` or use `ruff check .` to cover the full repo. |

---

## Reference

- [Code Review Checklist](.claude/skills/code-reviewer/references/code_review_checklist.md)
- [Coding Standards](.claude/skills/code-reviewer/references/coding_standards.md)
- [Common Antipatterns](.claude/skills/code-reviewer/references/common_antipatterns.md)
