# NE runtime acceptance — 2026-09-10

Both real Ubuntu-22.04 NE runs used the frozen configuration and completed with
safe landing. The PX4 strict report is `px4-attempt-01/strict-audit-report.json`
and the ArduCopter strict report is `arducopter-attempt-01/strict-audit-report.json`.
Their SHA256 values are `5cd6eff3b8bdf817035e6d31b2f9579346be61c32e5c31102f369c6f090e4e48`
and `c12fc18c3f95cc8bc62b371d0bf20833d662a3531a9feba7ca0ce1f9f76be688`.

The PX4 first audit report and command remain as rejected evidence because the
shared auditor call initially lacked its controller argument. The corrected
audit is a new exclusive report; no prior file or raw run was overwritten.

Offline validation: `python -B -m unittest validation.test_ne_runtime
validation.test_ude_runtime validation.test_pid_flight_audit -q` and the full
selected suite (88 tests before NE additions, 53 NE/PID tests) exited 0. Real
preflight and flight commands are retained in this directory's JSON/log files.
No NE run changes the PID/UDE frozen files or any physical budget.
