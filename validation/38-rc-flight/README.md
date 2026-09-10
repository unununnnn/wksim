# RC follow-up: 12/12 final raw audits passed

2026-09-10. The final control candidate for this matrix is
`/root/wksim-joint-control-WjBuqN/build.json`, SHA256
`ae5236af5052e81a256566a5e05d1840752fffb4d6f5cc512e0c0a5bb9e88c1d`.
It contains the installed Humble CDR/GID adapter and explicit RC ownership logic.
Native adapters, firmware and model remain the separately checked pinned builds.

The general one-run command, from the wksim root in Ubuntu-22.04, is:

```sh
bash tools/run-rc-flight.sh --stack px4 --scenario movement \
  --run-id rc-px4-movement-03 --output-root /root/wksim-rc-flight-px4-movement-03 \
  --control-manifest /root/wksim-joint-control-WjBuqN/build.json \
  --control-sha256 ae5236af5052e81a256566a5e05d1840752fffb4d6f5cc512e0c0a5bb9e88c1d
```

Use a new run-id/output directory on every new execution. Scenarios are movement,
recenter, yaw, stream-stall, mode-out and new-takeover; stacks are px4 and
arducopter. The command enters private network/IPC/mount namespaces and does not
operate hardware. A successful runtime reports `observed`, never an audited PASS.

Offline audit after sourcing the recorded ROS message overlays:

```sh
python3 -B tools/audit_rc_flight.py /root/wksim-rc-flight-px4-movement-03/rc-px4-movement-03 \
  --output /root/rc-px4-movement-03-audit.json
```

The output must be fresh and outside the raw run directory. The audit decodes CDR,
checks actual per-packet GIDs, independently recomputes the deadzone/integral,
compares native DDS targets and modes, binds phase cursors to physical raw rows,
and verifies final landing/cleanup. Epoch and stream transitions stay explicit.
CDR padding may differ between readers, so comparison uses independently decoded
String content plus actual GID, not identical trailing alignment bytes.

The mode-out case now uses an independent native mode request (PX4 AUTO.LOITER,
AP BRAKE), observes automatic RC withdrawal, and keeps sending the retired stream
as a negative probe. Earlier explicit-public-setup mode-out runs remain separate
historical checks, not substitutes for this external native mode observation.

The first PX4 stream-stall attempt correctly withdrew RC but the generic Task
fresh-state monitor rejected the expected native Offboard failsafe. The next
candidate monitors only transport/navigation observations after withdrawal and
requires a new explicit native hold request before reacquisition. The failed
attempt and its raw evidence remain preserved.

No physical/G6/RateUnmet budget or old result has been changed. This matrix does
not complete Full, the other RC/manual modes, or hardware/HIL acceptance. Final
matrix results are in final-matrix.json; all 12 runs passed the same auditor.
The full report is docs/2026-09-10-rc-flight-report.md.

Current-source note (2026-09-10): a later AP takeoff-settling fix uses Control
8EMCw6 (`e61239c514c45d6c65222277066a7ca629e6e2638b9877a040bdfc99643e7e2e`).
Build a current candidate with `bash tools/build-joint-control.sh` and use its
returned manifest/SHA for a new RC run. WjBuqN commands above identify the sealed
historical matrix at commit 0ae940d; new source must not be silently substituted
for that old installed identity. The later fix preserves native reset rejection.

The AP takeoff-settling follow-up was also exercised with a fresh RC movement
run on 8EMCw6: `rc-ap-settle-regression`, independent raw audit PASS, +X 1.2176m.
Its original result, audit and raw archive are retained beside the original matrix.
