# Code Review Report — Fighter-ID-Vision3D

_Generated: 2026-04-01 23:18 UTC_  
_Target: `/home/user/Fighter-ID-Vision3D`_

---

## Executive Summary

| Category | HIGH | MEDIUM | LOW | Total |
|----------|------|--------|-----|-------|
| Code Quality | 24 | 16 | 498 | 538 |
| PR Changes | 2 | 6 | 2 | 10 |
| **Combined** | **26** | **22** | **500** | **548** |

> **31** Python files scanned.

---

## High Priority Issues

These issues carry the highest risk and should be addressed before merging.

| Severity | File | Line | Issue |
|----------|------|------|-------|
| HIGH | `check_system.py` | 78 | Hardcoded Supabase URL appears hardcoded. Use environment variables instead. |
| HIGH | `fighterid_supabase_bridge.py` | 74 | Class `FighterIDAPI` defined in multiple files: fighterid_supabase_bridge.py:74, fighterid_vision_engine/pipeline/engine.py:100, vision_motor_v1.py:98. Consolidate to one location. |
| HIGH | `fighterid_vision_engine/camera/capture.py` | — | No test file found for `capture`. Expected `tests/test_capture.py`. Critical algorithm code needs unit tests. |
| HIGH | `fighterid_vision_engine/camera/capture.py` | 16 | Class `CameraStream` defined in multiple files: fighterid_vision_engine/camera/capture.py:16, vision_motor_v1.py:175. Consolidate to one location. |
| HIGH | `fighterid_vision_engine/config/settings.py` | — | No test file found for `settings`. Expected `tests/test_settings.py`. Critical algorithm code needs unit tests. |
| HIGH | `fighterid_vision_engine/detection/pose.py` | — | No test file found for `pose`. Expected `tests/test_pose.py`. Critical algorithm code needs unit tests. |
| HIGH | `fighterid_vision_engine/detection/pose.py` | 80 | Class `PoseDetector` defined in multiple files: fighterid_vision_engine/detection/pose.py:80, vision_motor_v1.py:246. Consolidate to one location. |
| HIGH | `fighterid_vision_engine/detection/tracker.py` | — | No test file found for `tracker`. Expected `tests/test_tracker.py`. Critical algorithm code needs unit tests. |
| HIGH | `fighterid_vision_engine/detection/tracker.py` | 153 | Class `SimpleTracker` defined in multiple files: fighterid_vision_engine/detection/tracker.py:153, vision_motor_v1.py:377. Consolidate to one location. |
| HIGH | `fighterid_vision_engine/pipeline/engine.py` | — | No test file found for `engine`. Expected `tests/test_engine.py`. Critical algorithm code needs unit tests. |
| HIGH | `fighterid_vision_engine/pipeline/engine.py` | 337 | Class `VisionMotorV1` defined in multiple files: fighterid_vision_engine/pipeline/engine.py:337, vision_motor_v1.py:487. Consolidate to one location. |
| HIGH | `fighterid_vision_engine/pipeline/fighters_state.py` | — | No test file found for `fighters_state`. Expected `tests/test_fighters_state.py`. Critical algorithm code needs unit tests. |
| HIGH | `fighterid_vision_engine/pipeline/heatmap.py` | — | No test file found for `heatmap`. Expected `tests/test_heatmap.py`. Critical algorithm code needs unit tests. |
| HIGH | `fighterid_vision_engine/pipeline/recorder.py` | — | No test file found for `recorder`. Expected `tests/test_recorder.py`. Critical algorithm code needs unit tests. |
| HIGH | `fighterid_vision_engine/pipeline/recorder.py` | 14 | Class `VideoRecorder` defined in multiple files: fighterid_vision_engine/pipeline/recorder.py:14, vision_motor_v1.py:460. Consolidate to one location. |
| HIGH | `fighterid_vision_engine/pipeline/replay.py` | — | No test file found for `replay`. Expected `tests/test_replay.py`. Critical algorithm code needs unit tests. |
| HIGH | `fighterid_vision_engine/pipeline/strike.py` | — | No test file found for `strike`. Expected `tests/test_strike.py`. Critical algorithm code needs unit tests. |
| HIGH | `fighterid_vision_engine/pipeline/strike.py` | 24 | Class `StrikeDetector` defined in multiple files: fighterid_vision_engine/pipeline/strike.py:24, vision_motor_v1.py:399. Consolidate to one location. |
| HIGH | `fighterid_vision_engine/pipeline/temporal_strike.py` | — | No test file found for `temporal_strike`. Expected `tests/test_temporal_strike.py`. Critical algorithm code needs unit tests. |
| HIGH | `supabase_client.py` | 7 | Hardcoded Supabase URL appears hardcoded. Use environment variables instead. |
| HIGH | `supabase_client.py` | 8 | Possible JWT token appears hardcoded. Use environment variables instead. |
| HIGH | `vision_motor_v1.py` | 62 | Hardcoded Supabase URL appears hardcoded. Use environment variables instead. |
| HIGH | `vision_motor_v1.py` | 64 | Possible JWT token appears hardcoded. Use environment variables instead. |
| HIGH | `vision_motor_v1.py` | 65 | Possible JWT token appears hardcoded. Use environment variables instead. |
| HIGH | `` | 618 | Hardcoded Supabase URL found in diff at line 618: +SUPABASE_URL = "https://abcxyz123.supabase.co" |
| HIGH | `` | 619 | Supabase publishable key found in diff at line 619: +API_KEY = "sb_publishable_abcdef..." |

## Medium Priority Issues

Address these in the current sprint or immediately after merging.

| Severity | File | Line | Issue |
|----------|------|------|-------|
| MEDIUM | `fight_manager.py` | — | File has a syntax error and could not be parsed. |
| MEDIUM | `fighterid_supabase_bridge.py` | 910 | File has 910 lines (>500). Consider splitting into smaller modules. |
| MEDIUM | `fighterid_vision_engine/main.py` | 22 | Bare `except:` catches all exceptions including KeyboardInterrupt/SystemExit. Use `except Exception:` or be specific. |
| MEDIUM | `fighterid_vision_engine/pipeline/engine.py` | 633 | File has 633 lines (>500). Consider splitting into smaller modules. |
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
| MEDIUM | `` | — | `.claude/skills/code-reviewer/references/code_review_checklist.md` was modified but no corresponding test file was changed. |
| MEDIUM | `` | — | `.claude/skills/code-reviewer/references/coding_standards.md` was modified but no corresponding test file was changed. |
| MEDIUM | `` | — | `.claude/skills/code-reviewer/references/common_antipatterns.md` was modified but no corresponding test file was changed. |
| MEDIUM | `` | — | `.claude/skills/code-reviewer/scripts/code_quality_checker.py` was modified but no corresponding test file was changed. |
| MEDIUM | `` | — | `.claude/skills/code-reviewer/scripts/pr_analyzer.py` was modified but no corresponding test file was changed. |
| MEDIUM | `` | — | `.claude/skills/code-reviewer/scripts/review_report_generator.py` was modified but no corresponding test file was changed. |

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
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 84 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 87 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 89 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 115 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 116 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 131 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 156 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 157 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 166 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 182 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 203 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 205 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 231 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 233 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 254 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 256 | Function `resolve_fighter`: missing return type. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 352 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 373 | Function `start` is missing a docstring. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 393 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 402 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 406 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 415 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 423 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 429 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 438 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 455 | TODO comment: # Replay: buffer todo frame antes de procesar |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 483 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 528 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 622 | Function `stop` is missing a docstring. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 632 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/engine.py` | 633 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/fighters_state.py` | 57 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/recorder.py` | 27 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/recorder.py` | 29 | Function `write` is missing a docstring. |
| LOW | `fighterid_vision_engine/pipeline/recorder.py` | 33 | Function `stop` is missing a docstring. |
| LOW | `fighterid_vision_engine/pipeline/recorder.py` | 35 | Use `logging` instead of `print()` in library/engine modules. |
| LOW | `fighterid_vision_engine/pipeline/replay.py` | 107 | Function `is_playing` is missing a docstring. |
| LOW | `fighterid_vision_engine/pipeline/strike.py` | 38 | Function `detect`: missing return type. |
| LOW | `fighterid_vision_engine/pipeline/strike.py` | 38 | Function `detect` is missing a docstring. |
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
| LOW | `` | 835 | New TODO added in diff: +    pattern = re.compile(r"#.*(TODO|FIXME|HACK|XXX)\b", re.IGNORECASE) |
| LOW | `` | 1248 | New TODO added in diff: +    todo_pat = re.compile(r"\+(.*?)(TODO|FIXME|HACK|XXX)\b", re.IGNORECASE) |

</details>

---

## PR Changes

**Branch:** `claude/setup-code-reviewer-template-J8QWV`  
**Base:** `424327a2c5a5`  
**Changes:** 6 files, +1221 / -447 lines

### File Risk Assessment

| Risk | File |
|------|------|
| LOW | `.claude/skills/code-reviewer/references/code_review_checklist.md` |
| LOW | `.claude/skills/code-reviewer/references/coding_standards.md` |
| LOW | `.claude/skills/code-reviewer/references/common_antipatterns.md` |
| LOW | `.claude/skills/code-reviewer/scripts/code_quality_checker.py` |
| LOW | `.claude/skills/code-reviewer/scripts/pr_analyzer.py` |
| LOW | `.claude/skills/code-reviewer/scripts/review_report_generator.py` |

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

## Reference

- [Code Review Checklist](.claude/skills/code-reviewer/references/code_review_checklist.md)
- [Coding Standards](.claude/skills/code-reviewer/references/coding_standards.md)
- [Common Antipatterns](.claude/skills/code-reviewer/references/common_antipatterns.md)
