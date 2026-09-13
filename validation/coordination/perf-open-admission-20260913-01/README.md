# Self-thread perf open admission

The main coordinator compiled and ran `open_self.c` on WSL2 Linux
6.6.87.2-microsoft-standard-WSL2. Both `exclude_kernel=0` and `1` opened and
closed successfully with errno 0 under this root execution environment.
This result does not establish access for an unprivileged process.

The event stayed disabled: no mmap, enable, switch sampling, or flight ran.
`switch_records_verified` is false. This establishes open/close availability
only; the full switch parser remains under repair and separate acceptance.

`prechecks.json` records two empty WSL process scans. The execution entry
checked both scans against the current boot and a 60-second freshness limit.
`receipt.json` retains compiler argv, source and private binary SHA256,
process exit status and same-boot empty process groups. Both child processes
terminated; no keeper was used. Private build files remain under the
receipt's `/tmp/wksim-perf-open-*` directory, outside Git.

`dispatches.json` records the three DeepSeek follow-up turns, existing Claude
and OMP turns, and the three CodeBuddy quota failures. These files are records;
they do not schedule background work. CodeBuddy reset was reported as
2026-09-13 20:54:20 JST and was still in the future at this check.
