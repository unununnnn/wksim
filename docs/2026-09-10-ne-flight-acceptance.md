# NE dual-stack flight acceptance

The NE runtime is frozen in
`Simulator/wksim_runtime/ne-flight-v1.json` (SHA256
`3b09761ad60976aa971f43e81edc0de9bb4ede7065a10b5d512c57c22a478e18`) and uses
the existing external XYZ_ATT task path. The source algorithm
`PositionNE` and its original-source comparison were unchanged. Runtime
selection, reset/initial-position binding, physics protocol and independent
audit were added in commit `261bcf5`; the corrected audit interface and PX4
evidence were pushed in `3092698`.

PX4 run `ne-px4-acceptance-20260910-01` completed normally and landed. The
corrected strict report is
`validation/ne-runtime-acceptance-20260910/px4-boundary2-strict-audit-report.json`
(SHA256 `5cd6eff3b8bdf817035e6d31b2f9579346be61c32e5c31102f369c6f090e4e48`). It
verified 93,400 physical ticks, 1,000 disturbance ticks, 850 native target
associations and NE recomputation counts 167/399/284 (point/circle/disturbance).
Maximum position errors were 0.104605/0.142220/0.119038 m.

The first PX4 audit report is preserved as rejected evidence because the shared
auditor call lacked its controller argument; it did not alter the run or the
later report.

ArduCopter run `ne-arducopter-acceptance-20260910-01` completed normally and
landed. Its strict report is
`validation/ne-runtime-acceptance-20260910/arducopter-strict-audit-report.json`
(SHA256 `c12fc18c3f95cc8bc62b371d0bf20833d662a3531a9feba7ca0ce1f9f76be688`). It
verified 126,336 physical ticks, 1,000 disturbance ticks, 659 native target
associations, 510 motor comparisons and NE recomputation counts 132/307/220.
Maximum position errors were 0.163224/0.158618/0.160244 m.

Both runs passed source/protocol consistency, same-run hover calibration, reset
identity, fixed physical windows, native mode checks and owned-process cleanup.
The exact command/preflight/audit records and compact run snapshots are under
`validation/ne-runtime-acceptance-20260910/`; dense native logs stay in the
sealed WSL run directories named in those reports. Full/UI, joint real-time
rate, hardware, motor-efficiency and other unrelated project scope remain
separate acceptance boundaries.
