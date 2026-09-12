# Static-input EGO fixture: timed out

The actual EGO binary was launched with the frozen single-box XML, 11000-point scene, static odometry (-4,0,3) and explicitly synthetic control-state/clock inputs. No flight controller or public command consumer was connected. No B-spline arrived within the 30s fixture bound. The original planner log shows startup and COMMAND-mode entry, but does not establish planning completion or a failure cause.

`result.json` records the exact binary/source hashes, original timeout and cleanup: roscore and planner launcher exited zero; no process remained in the local private network view. `source/run_ego_planner_probe.py` preserves the executed fixture. This attempt did not establish trajectory or clearance acceptance.

An execution-coordination mistake is recorded in `coordination-note.json`: checking the Ubuntu process list and starting this Rfly fixture occurred in one unevaluated command. The check showed another task running rate-comparison preflight. Possible overlap means this fixture must not be used for performance or root-cause conclusions. The fixture reached its timeout and cleaned up before any manual interruption was performed. The other task was not terminated. Future native starts require separately completing and assessing both distribution process checks first.
