# Final independent #67 / #25 acceptance review

**#67 PASS. #25 PASS for the frozen source-template Hex X scope, ready for the primary agent's final bookkeeping/closure.** This is not a Full/G6/R1 or real-time-rate verdict. No runtime, source, issue, commit or original evidence was changed; only this new review directory was written.

## AP cold reset independently verified

Repeated the complete current physical/native audit with `--require-cold-reset` against `/root/wksim-hex-flight-ap-reset-observed-20260909-05/hex-ap-reset-observed-20260909-05`. It passes with no errors and is **byte-identical** to the delivered `validation/25-ap-reset/20260909-05/strict-audit-report.json`: SHA256 **`0db3087a3f901a0c4be4abbc324bd7abc3df72ee8867ca13201930feabcef892`**. Own result/log are `ap-reset-independent-audit.json` and `ap-reset-audit-command.log`.

Directly compared original parent/child result files:

| Item | Parent AP04 | New AP05 |
|---|---|---|
| run_id | `hex-ap-live-observed-20260909-04` | `hex-ap-reset-observed-20260909-05` |
| result SHA256 | `d29308997ac1c71d7d89ad30ea5a0a8431164a19a12988f44efe188747531c86` | `abdb039be4695b37532c0d9695dd2189e29c497a443da8f667e4df13e97b0114` |
| control epoch | `005a79cdce1b4c11b69233675a54a5ea` | `80c96110a6b9425481eac194db18d6e7` |

The child parent-link SHA exactly matches the accepted parent above. Both configuration identities equal `sha256:94664f7e98b51ee2d55beadd3a7a9af0a06579f86dd8390f0e6912d267b0127e`; AP47v2 protocol remains `ce4f0aeb3c2de250aaf10c224f3fa43c326fcfcf8140c3746770879558f9df37`. All20 executed source hashes are identical between parent and child. The new native storage/run directory, supervisor and child lifetimes differ; the auditor checks boot_id/PID/starttime identity rather than assuming numeric PID uniqueness.

Child initializes at tick0 and records65,389 continuous1ms steps/actuators, six active motors and the expected owner-retirement terminal. All33 native parameters, public request chain, source-derived AP GUI/E7/local/global target receipts and landed/disarmed evidence pass. Full fixed physical windows have zero violations: hold5021 samples, waypoint2001, landing-to-terminal270, parameter-ground441. Safe landing and reaped flags are true, cleanup_errors is empty. The current `/proc` retirement audit checks all five child-run process identities and recursively verifies the accepted parent's evidence/retirement. No old task or process is reused, and this remains terminal-result cold reconstruction rather than live hot reset.

The recorded flight command exited0; it used the correct parent path and the new run/output root. No conditional acceptance of missing targets, disabled native checks, malformed logs or peer-reset terminal was introduced.

## Unaffected visual reuse is valid for #67

#67 explicitly permits prior AP live display evidence when no affected visual change occurred. Parent/child all20 runtime source hashes match, the full configuration/model identity matches, all six current visual/coordinator source hashes match the accepted AP04 manifest, and actual UE module SHA remains `15af1f6e400e77d6a8a207fd047b48b1d04c54260a5668312178051c119e6245`.

Reuse is therefore limited to the already independently reviewed AP04 display:3011 raw-correlated ACKs, complete phase coverage, and actual hover/waypoint frames0045/0048 inspected by primary and independent reviewers. This review does not mislabel those frames as newly rendered AP05 frames. Prior visual review is `validation/hex-ap-final-review-20260909/report.md` and the immutable-derived bundle is `validation/25-ap-live-observed-20260909-04-reviewed/`.

## #25 original acceptance criteria

| Original criterion | Result / evidence |
|---|---|
| Freeze model, parameters, mass/inertia, motor order/spins and applicable FC configuration | PASS for the fixed source-template Hex X. `docs/2026-09-09-hex-model-candidate.md`, retained config/build/static-response evidence, protocol files and actual admissions pin the1.515kg model, inertia `[0.0211,0.0219,0.0366]`, six motor geometry/spins and exact library. AP4.7 and PX4 custom POSIX10016 configurations are explicit, not falsely called stock6001. |
| Independent model and applicable two stacks complete takeoff/hold/waypoint/landing/reset | PASS. AP04 full flight plus AP05 cold reset; PX4-03 parent plus accepted `hex-px4-live-reset-20260909-02`. This review repeated AP05 and recursive AP04 audit. The completed independent #69 review verifies the PX4 pair's raw/source/process/config/tick0 invariants; its retained physical report and reviewed display are both passed. |
| UE geometry and rotors match Hex, no four-rotor placeholder | PASS. AP04 and PX4 reset02 have separate live raw/Actor/capture proofs; accepted reports contain3011 and1417 ACKs respectively and explicit reviewed PNG hashes. The prior two independent final-review reports document actual six-rotor image inspection and frozen geometry/spin/phase error checks. |
| State applicability limits, do not infer other combinations | PASS as explicitly scoped. Only frozen Hex X/source-template AP4.7 and PX4 configuration are claimed; no three-axis six-rotor, arbitrary model/FC pairing or aircraft-calibrated result is inferred. |
| Deliver commands, identities, expected/actual results, failures/limits and primary review | Evidence ready. Run manifests, raw logs, strict/reviewed reports, source hashes, native identities and actual commands are retained; original AP parameter/audit failures and first PX4 reset peer-termination failure remain unchanged. Root owns the final commit/issue closure. |

Reviewed aggregate evidence pointers: `docs/2026-09-09-hex-dual-stack-live.md`, `validation/hex-px4-final-review-20260909/review.md`, `validation/25-px4-reset-live-20260909-02/{flight-audit.json,reviewed-audit.json}`, AP04 final review, and this AP05 audit. The PX4 retained physical report, recursive parent and cold-reset tick0 checks pass; its reviewed display report passes with1417 ACKs. This review uses the completed independent #69 investigation rather than claiming a new PX4 flight.

## Dependencies and closure boundary

Live `gh --repo unununnnn/wksim` checks show original dependencies **#17 CLOSED** and **#24 CLOSED**. Supporting children #52/#65/#66/#68/#69 are CLOSED. #67's new evidence now passes and is ready for root closure; #25 remains OPEN pending root's aggregate bookkeeping. Stale unchecked Markdown boxes in its body are not evidence of missing completed work, but root should reconcile them when closing.

No remaining physical/display/reset obligation was found inside #25's stated frozen Hex X scope. This verdict does not close the Full parent, certify numerical equivalence/R1/G6, establish hardware or real-aircraft calibration, approve production model admission, or satisfy #20/#62 sustained1×. All earlier failures retain their original outcomes. The two flight stacks here are independent experiments, not a new joint-scene acceptance.
