# ds-architecture-mixed-migration-20260913-01 — read-only reproduction (revision 3)

All commands are **read-only**: `git` / `stat` / `sha256sum` / `head` / `grep` / `python3 -c` on receipt **text**, plus the pure unittest invocation in §6 (no native, no build, no model execution).
Not permitted and not used: model imports, execution of the runner/native/FC, ROS/SITL/UE/MATLAB, builds, network, any write inside a Linux checkout.
`git diff --no-index` and `git show` read and print only. Nothing here is an acceptance run.

## 1. Windows identity (PowerShell, repo root)

```powershell
Set-Location -LiteralPath 'C:/Users/PC/Documents/odid编译/wksim'
git branch --show-current
git rev-parse HEAD                                   # revision 3 expects 386f713a7752515502fd2224e9186f2219674732
git status --short
git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD; $LASTEXITCODE   # must be 0
```

## 2. WSL checkout identities (read-only)

```bash
wsl.exe -d Ubuntu-22.04 --exec bash -lc '
for d in /root/wksim-architecture-acceptance-20260913 /root/wksim-release-acceptance-fe3; do
  echo "== $d"; git -C "$d" branch --show-current; git -C "$d" rev-parse HEAD
  git -C "$d" status --short | head -40
  git -C "$d" merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD
  echo "ancestor_exit=$?"
done'
```
Expected (revision 3): new candidate `386f713a7752515502fd2224e9186f2219674732` with `git status --porcelain` printing 0 lines and ancestor exit 0;
historical comparison `db1200d…` exit 1 with **5** tracked modifications.
Candidate update receipt: `validation/coordination/architecture-candidate-sync-20260913-02/receipt.json` (fast-forward `d45d1da → 386f713`, `private_wiring_migrated=false`).

## 3. Correct rate arithmetic (from the receipts, no model import)

```bash
wsl.exe -d Ubuntu-22.04 --exec bash -lc 'python3 - <<PY
import json
base="/root/wksim-release-acceptance-fe3/validation/joint-public-flight-oayggl_s"
anchor=latch=None; gs=ge=0
with open(base+"/rate.jsonl") as f:
    for line in f:
        try: r=json.loads(line)
        except Exception: continue
        if r.get("kind")=="rate_anchor" and anchor is None: anchor=r
        elif r.get("kind")=="rate_unmet" and latch is None: latch=r
        if r.get("kind")=="rate_group_start": gs+=1
        if r.get("kind")=="rate_group_end": ge+=1
aw=anchor["anchor"]["wall_ns"]; at=anchor["anchor"]["tick"]
lw=latch["issued_monotonic_ns"]; lt=latch["tick"]
span=lw-aw; sim=(lt-at)//4*4_000_000
print("segment_wall_s", span/1e9)
print("segment_sim_s", sim/1e9)
print("segment_average_ratio", sim/span)
res=json.load(open(base+"/result.json"))
print("scene_wall_s", res["wall_seconds"])
print("forbidden_mixed_ratio", (sim/1e9)/res["wall_seconds"])
print("groups", gs, ge)
PY'
```
Expected: `segment_wall_s 216.028736503`, `segment_sim_s 107.964`, `segment_average_ratio ≈ 0.499767`,
`forbidden_mixed_ratio ≈ 0.401769` (must never be reported as a rate), `groups 26991 26991`.

Receipt integrity:

```bash
wsl.exe -d Ubuntu-22.04 --exec bash -lc 'A=/root/wksim-release-acceptance-fe3/validation/joint-public-flight-oayggl_s
for f in result.json rate.jsonl manager-gc-candidate.json; do printf "%s  %s\n" "$(sha256sum $A/$f | cut -d" " -f1)" "$f"; done'
```

## 4. manager-GC provenance and distribution

```powershell
git show 7cb7e8401776848fcb11e0a8dd2237c1eee2337b --stat
git branch -a --contains 7cb7e8401776848fcb11e0a8dd2237c1eee2337b
git merge-base --is-ancestor 7cb7e8401776848fcb11e0a8dd2237c1eee2337b 386f713a7752515502fd2224e9186f2219674732; $LASTEXITCODE   # expected 1
git ls-files --error-unmatch tools/manager_gc_candidate.py            # expected: not tracked
git ls-files --error-unmatch validation/test_manager_gc_candidate.py  # expected: not tracked
Select-String -Path 'Simulator/wksim_runtime/joint_profile.py' -Pattern 'manager_gc|gc-freeze|compare_joint_gc'   # expected: no match => not a formal admission gate
```

```bash
wsl.exe -d Ubuntu-22.04 --exec bash -lc 'O=/root/wksim-release-acceptance-fe3
for f in tools/manager_gc_candidate.py validation/test_manager_gc_candidate.py validation/test_gc_candidate_entry.py \
         tools/compare_joint_gc_diagnostics.py validation/test_compare_joint_gc_diagnostics.py; do
  [ -f "$O/$f" ] && printf "%s  %s\n" "$(sha256sum $O/$f | cut -d" " -f1)" "$f" || echo "ABSENT $f"; done'
```

## 5. Migration diff (read-only; writes nothing)

```bash
# full diff of the donor runner vs the new-architecture runner (reference only; do NOT copy wholesale)
wsl.exe -d Ubuntu-22.04 --exec bash -lc 'cd /root/wksim-release-acceptance-fe3 && \
  git --no-pager diff --no-index --stat -- \
    /root/wksim-architecture-acceptance-20260913/tools/run_joint_flight.py tools/run_joint_flight.py'

# hunk map
wsl.exe -d Ubuntu-22.04 --exec bash -lc 'cd /root/wksim-release-acceptance-fe3 && \
  git --no-pager diff --no-index -U0 -- \
    /root/wksim-architecture-acceptance-20260913/tools/run_joint_flight.py tools/run_joint_flight.py | grep -E "^@@"'

# manager-GC hook lines in the donor, and the removable marked regions
wsl.exe -d Ubuntu-22.04 --exec bash -lc 'grep -n "manager_gc\|manager-gc" /root/wksim-release-acceptance-fe3/tools/run_joint_flight.py'
wsl.exe -d Ubuntu-22.04 --exec bash -lc 'grep -n "owned-snapshot-wiring" /root/wksim-release-acceptance-fe3/tools/run_joint_flight.py'

# the small, self-contained feature commit that adds manager-GC (53 lines of runner change)
git show 7cb7e8401776848fcb11e0a8dd2237c1eee2337b -- tools/run_joint_flight.py
git show 7cb7e8401776848fcb11e0a8dd2237c1eee2337b -- validation/test_joint_rate_probe.py
```

## 6. Pre-existing test inconsistency (independent of migration)

```powershell
# exact source of the disputed line (v3 correction: it is getattr-guarded)
(Get-Content 'tools/run_joint_flight.py')[328]
Select-String -Path 'tools/run_joint_flight.py' -Pattern "async_model_evidence = getattr|model_promotion_flight = getattr"

# the actual test outcome (read-only; no native, both paths mocked inside the test)
python -m unittest validation.test_joint_rate_probe.JointRuntimeTimingProbeEntryTests.test_real_runner_source_manifest_and_source_unchanged_follow_probe_state -v
```
Correct result: `tools/run_joint_flight.py:329` is `async_model_evidence = getattr(args, 'async_model_evidence', False)`,
and the run reports `Ran 1 test` / `OK`. **The v2 claim that this case fails and needs a `SimpleNamespace` repair was false and is withdrawn.**
The donor's +21 test lines exist only because the donor runner reads more plain attributes (for example `planner_release_proof`, `manager_gc_freeze`);
they are needed only if such wiring is migrated.

## 7. Candidate update pointer and build / admission (NOT performed; post-migration sequence only)

Current candidate pointer (v3): the Linux candidate was fast-forwarded `d45d1da → 386f713` from a main-branch bundle, clean tree, ancestor exit 0,
with `private_wiring_migrated=false`; read the receipt at `validation/coordination/architecture-candidate-sync-20260913-02/receipt.json`.
The `d45d1da` snapshot in this report's v1/v2 revisions is historical.

```text
1. two-WSL precheck: found=[] and identical boot_id, each checked within the last 60 s
2. entry-time boot/freshness validation (delivery policy rule 14)
3. clean env; for an unprobed trial unset WKSIM_JOINT_CPU_TIMING and WKSIM_JOINT_RATE_TIMING_PROBE
4. new-candidate launcher: cd /root/wksim-architecture-acceptance-20260913
   bash tools/run-joint-flight.sh \
     --task-profile xy_velocity_z_position_yaw_v1 --async-model-evidence [--manager-gc-freeze ONLY IF retained] \
     --ap-mixed-manifest /root/wksim-ap-mixed-fhuf05l9/mixed-build.json \
     --ap-mixed-sha256 1e6250eff8873d6b2e52017b613c223ac29f8260fdf92aac2cf0c7cdcc6ce94c \
     --control-manifest /root/wksim-joint-control-c2IXOr/build.json \
     --control-sha256 6fe8c0b30775a9ba83407302f602d0785876d307e5f1cb746afa3bf316cf5e7e \
     --message-manifest /root/wksim-ros2-Rzj3Pf/message-build.json \
     --message-sha256 29969da0702451e3fc6f1de40bc301a67284c4e7d5fae8f88c64773d27a96219
   (if --manager-gc-freeze is NOT migrated, omitting the flag is required: the runner has no such argument)
5. gate only on the original thresholds: 1 ms tick / 4-tick group / no catch-up / 100 ms late limit /
   complete 10 s / 60 s sliding windows / source_unchanged; on RateUnmet retain the original and do not rerun that config
```
