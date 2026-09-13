# #114 · 46-reexecution implementation and verification

2026-09-09. Prerequisite #113 is CLOSED/COMPLETED. This delivers the bounded
independent physical recalculation tool and refusal tests for #114.

## Delivered files and contract mapping

- `tools/reexecute_model.py`: import/run/audit, strict sealed-source validation,
  fresh native child process, one 1ms call per input, independent full-output audit.
- `validation/test_model_reexecution.py`: 33 admission tests and one Linux native
  integration test with real source capture, fresh-process recomputation and corruption cases.
- This new evidence directory: commands, logs, native raw input/output, receipts and hashes.

The approved #114 filename is `reexecute_model.py`; #113's draft
`reexecute_physics.py` spelling is superseded for this implementation. No file
outside the ticket allowlist or this shared-permitted evidence directory is included.
Existing AGENTS.md and the Luna handoff guide changes remain outside this commit.

The static independent `quad-mass-cold-post-step-v1` profile enforces 16 normalized
actuators, 15 explicitly zero terrain inputs, cold initialize at tick zero, all
17 source random streams and their consumption identity, complete mass configuration,
source/build/archive/wrapper/library/dependency identities, per-tick input references,
explicit no-events declaration and complete exited-source terminal/frontiers.
Missing/duplicate/undersampled intervals, warm restart, unsupported pause/reset/events,
nonfinite/bool numbers, foreign epoch, unknown fields, malformed paths/symlinks,
truncation and missing/changed source members reject before native initialization.
No interpolation or inferred held input is used. Input files are copied byte-for-byte.

Run receipts bind the input manifest hash, actual library, full build/platform identity,
source tool hash, loaded mappings, actual engine times, child exit and stream hashes.
The auditor compares all 120 native post-step slots at every tick, atol=rtol=0,
reports first mismatch and per-slot maxima/counts, and rejects incomplete run evidence.
The current bounds are 100,000 ticks, 64 members and 256 MiB per source package;
unsupported profiles are explicitly refused. Stored argv is never executed.

## Exact verification and results

From the wksim repository root:

```powershell
python -m unittest validation.test_model_reexecution.AdmissionTests -v
wsl -d Ubuntu-22.04 -u root -- env WKSIM_REEXECUTION_NATIVE=/root/wksim-reexecution-114-20260909-03 /usr/bin/python3 -m unittest validation.test_model_reexecution -v
```

Windows: **33 passed, 0 skipped**. WSL: **34 passed, 0 skipped**. Both exit 0.
`review.ps1` executed those commands and archived outputs. Native target directories
are exclusive-create; use a new unused directory when repeating the native test.
The script's archival destination is also exclusive-create; preserve this result.

Actual CLI sequence exercised by the integration test (Linux repository root):

```bash
python3 tools/reexecute_model.py import --source /root/wksim-reexecution-114-20260909-03/source --output /root/wksim-reexecution-114-20260909-03/input
python3 tools/reexecute_model.py run --input /root/wksim-reexecution-114-20260909-03/input --library /root/wksim-reexecution-114-20260909-03/build/libwksim_configured.so --output /root/wksim-reexecution-114-20260909-03/run
python3 tools/reexecute_model.py audit --input /root/wksim-reexecution-114-20260909-03/input --run /root/wksim-reexecution-114-20260909-03/run --output /root/wksim-reexecution-114-20260909-03/audit.json
```

The source plan was frozen before capture; a separate source process ran the model
and exited 0 before sealing. The recomputation used another process and 25 real
1ms native integration calls. All **3,000 comparisons passed exactly**. Source
bytes were checked unchanged after all tests. This is a short implementation
fixture with the real native library, not #115's independent source acceptance.

Changing one expected value yields exit 1 / `numerical_failed`, exactly one
mismatch at **tick 10, slot 10**. It proves the executor does not echo expected
outputs. Corrupting the supplied actual library yields exit 2 / `build artifact
hash` before creation of the native child request. Six independent audit negatives
(gap, 1ms time, epoch, manifest request, nonzero child exit, missing terminal) all
return exit 2, including actual-stream mutations with recomputed terminal hashes.

The first Windows development run had one assertion-pattern mismatch for malformed
JSON (the parser correctly refused it); the assertion was corrected. The first
archival script attempt stopped because Windows PowerShell treated unittest's
successful stderr progress as an error; exit-code handling was corrected. Final
raw results are `windows.log`, `wsl.log`, and `native/`. Earlier native development
fixtures remain under `/root/wksim-reexecution-114-20260909-01` and `-02`.

## Identity and retained boundaries

`review.json` records exact argv, exit codes, source hashes and every archived
native evidence file hash. `native/source/manifest.json` binds source and build;
`native/source/build.json` retains compilation argv/compiler and original hashes.
`native/run/request.json`, `loaded.json`, `actual.jsonl`, `terminal.json`,
`process.json` and the standalone `native/audit.json` provide execution evidence.

- Contract SHA256: `54c93d120a9745bb9466b2b4279bafa0701b7b3c706f3728574a5797c719fac1`.
- Config identity: `sha256:9a0592896161ac99ed9defa9f5616a8463dc5d4d459cace3bf3115d18548501b`.
- Input manifest SHA256: `1ae747154a72ac46435c33cede8642b81224c12c20f0b13f02825750108d314f`.
- Archive SHA256: `d528b5d247e13d943f1eaa7a37fd3cb4d15c7e9bb7a6b0e5988a1423e59d05ed`.

Hashes attest byte identity; they do not authenticate an arbitrary capture author's
claims. Approved capture provenance remains a review responsibility. The existing
replay reader remains an offline-record reader; old #24 baseline is refused as
`insufficient_recording`, and no old terminal or missing inputs were reconstructed.
The fixed static profile refuses lifecycle changes instead of silently losing them.
Cross-platform/build identities do not receive same-build numerical acceptance.

All test-owned native processes exited. No FC, ROS, UE or flight was started.
Builds and vendor materials remain local; no model source, library or ZIP is
committed. The implementation reuses ConfiguredModel and the standard library.
R1, RateUnmet, Full, parent #46 and #115 acceptance are unchanged.

Actual session settings verified from the latest `turn_context` of
`01a085a2-4d06-7f03-afec-a223f7527504`: **gpt-6-astra / low**. No subagents.

AC1: bounded native tool, full comparison and source-sufficiency negatives delivered.
AC2: source/config/build identity, exact commands, raw results and boundaries delivered.
Only #114 is eligible for closure.
