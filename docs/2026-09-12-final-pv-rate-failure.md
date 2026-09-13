# Final mixed-firmware P+V rate failure

The first formal `full_xyz_pv_yaw_v1` attempt used the admitted AP mixed, rWolCy control, and Rzj3Pf message manifests. Admission passed with zero children and the run started in its private network, IPC, mount, and process-group boundaries.

The run did not reach takeoff or either P+V leg. At tick 26636, the fixed 0.5x scheduler latched `resource_insufficient` at 100.038885 ms cumulative lateness, above the unchanged strict 100 ms limit. The measured timed-segment rate was 0.499096932366686 after 6649 completed four-tick groups. No catch-up or threshold relaxation was applied.

Cleanup completed without reported errors: both control nodes shut down cleanly, the unrelated-process inventory was unchanged, the explicit message candidate and repository sources were unchanged, and a post-run process scan found no matching runtime process. The run retained 284 files and 181,496,303 bytes under `validation/joint-public-flight-tpwl1k4p` on this host.

The async truth streams were retained, but the writer summaries were absent after the rate fault. The offline auditor therefore failed closed before downstream task and physical checks. The compact retained identity and rate record is `validation/83-final-pv-rate-failure-20260912/summary.json`; the auditor failure is `validation/83-final-pv-tpwl1k4p-audit.json`.

This attempt is failure evidence. It does not satisfy the full P+V flight, formal mixed profile, rate, or production gates. The second mixed task was not started.
