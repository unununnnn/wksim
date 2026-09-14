# CodeBuddy independent review — release audit tool + probe-run-02 matrix (2026-09-12)

Read-only independent recheck of the frozen release auditor and the probe-run-02
one-positive/four-negative report. No native run, no ROS nodes, no build, no full
raw scan; only targeted file reads. Only this file was written.

## Round 2 follow-up (2026-09-12, later)

New inputs checked: `validation/39-planner-flight/audit-matrix-20260912/`
(`main-verification.json`, `probe-executed.py`, `probe-report.json`,
`auditor-executed.py`, `probe.log`), plus the helper generator and consumer on the
WSL release checkout.

### Anchor verification — F1/F2 for the *historical* artifact: resolved

Every recorded binding recomputes exactly:

| Binding in `main-verification.json` | Recorded | Recomputed | Result |
|---|---|---|---|
| `probe_sha256` ↔ `probe-executed.py` | `92a83f4e…` | `92a83f4e…` | match |
| `probe_sha256` ↔ executed WSL `tools/probe_release_audit_integrity.py` | `92a83f4e…` | `92a83f4e…` | match |
| `source_report_sha256` ↔ `probe-report.json` (new dir and run-02 original) | `4b21beca…` | `4b21beca…` | match |
| `auditor_sha256` ↔ `auditor-executed.py` ↔ frozen `tools/audit_planner_release.py` | `e8d33c5d…` | `e8d33c5d…` | match |

The external derivation is faithful: positive accepted; the four required
negatives each rejected with the expected `ValueError`; `baseline_unchanged=true`
(319 files). I had already read the same five outcomes from the report itself in
round 1, so this is an independent confirmation, not a restatement.

Key distinction now explicit: the historical run-02 artifact is **externally
anchored** by the executed tool bytes + the frozen auditor + the derived flag, and
the main session did not claim the old report self-contains the field. With
`probe-executed.py` present, `complete_matrix_pass` is recomputable and auditable.
That closes F1/F2 for run-02.

**F2b stays open by design and is not re-litigated here:** the *new* repo probe
tool (47554 B, has coverage) still writes no producer self-hash, and
`complete_matrix_pass` still ignores the optional/`blocked_or_error` overall
state. Handed to DS-A; no repetition of the detail.

### F4 recheck — helper SET_PX4_MODE scope: boundary only, no action-bearing gap

Generator (helper → transport node):
- `planner_transport_node.py::_publish_setup_envelope` → `trajectory_bridge.py::build_ros_mode_request` (line 91) writes only `version=1`, `run_id`,
  `control_epoch`, `request_id`, `header.stamp`, `header.frame_id='map'`,
  `setup.cmd=SET_PX4_MODE`, `setup.px4_mode=mode`. `UAVSetup.arming` stays
  `False`, `control_state` stays `''`; there are no other fields.
- The helper's own record has no envelope: `planner-release-handoff.json` holds
  `mode`/`expected_native_mode`/high-waters only; the node log carries no
  published-envelope line.

Consumer (real action): `ros2/src/prometheus_control/prometheus_control/node.py::on_setup`, `SET_PX4_MODE` branch (lines 512–530) reads **only**
`msg.px4_mode` (validated against `{POSCTL, AUTO.LOITER, AUTO.LAND, AUTO.RTL, BRAKE}`;
`BRAKE` additionally requires native `external_mode == 'GUIDED'`) and then calls
`native.request('mode', msg.px4_mode)`. It never reads `arming`,
`control_state`, or `header`. The identity gate `RunSession.accept`
(`session.py:88–101`) validates `version==1`, `run_id`, `control_epoch`, and
monotonic `request_id`.

Therefore the auditor's current scope (identity + `cmd` + `px4_mode`, plus the
required `native_ack`/`setup_completed` events) covers every field that can affect
the BRAKE action. `version` is not compared directly, but `version≠1` is rejected
by `accept()`, which suppresses the required ack/completion, so it is transitively
covered. `header.stamp`/`frame_id`, `arming`, and `control_state` do not
participate in this operation; leaving them out of the comparison carries no
action risk. No specific unverified action-bearing field exists.

Boundary to state explicitly (and the only F4 claim that is defensible): the
helper envelope has **no full-field source-side ledger**, so the auditor does no
full-field source↔CDR 3-way reconciliation for `Setup66` — and the captured CDR
must not be presented as if it were that source ledger. This is a documentation
boundary, not a functional gap.

## Round 1 findings and status

- **F1/F2 (historical run-02 report lacked self-attestation):** resolved by the
  external anchor above. Residual note: `main-verification.json` itself has no
  self-hash, but the anchor chain is fully recomputable from the archived
  tool/report/auditor bytes.
- **F2b (new tool self-report + optional overall flag):** open, owned by DS-A.
- **F3 (optional-scenario inconsistency in `summarize_coverage`):** open, folded
  into DS-A's fix; not repeated.
- **F4 (Setup66 out of the 3-way):** rechecked; boundary-only, see above.
- **F5 (minor):** `derived_retained_sources` still over-counts via duplicates
  (70 listed vs 66 unique resolved files); reporting-only.

## Checked in round 1, no finding (unchanged)

- ROS-wire normalization is exact, with no numeric tolerance; the ledger /
  completion-report / full-CDR 3-way is sound and rejects extras, duplicates, and
  out-of-order ids.
- `event_id` contiguity is bounded to observed endpoints and explicitly does not
  claim tail/outside-range completeness; landing and release events are
  independently anchored by required presence.
- PX4 water level is a hard `1..127` contiguity bound tied to the captured final
  `last_request_id`.

## Constraint compliance

Read-only throughout except this report. No flight, no ROS nodes, no build, no
full raw scan; no new agents; no Issue changes. Uncommitted changes and user
originals untouched; DS-A's in-progress tool was read, not edited.
