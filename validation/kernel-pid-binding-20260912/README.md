# Kernel PID binding with inherited descriptors and real scheduler events

Run 04 passed with five owned synthetic actors and all nine named target tasks.
The production native BPF library, Python descriptor handoff, binding functions
and collector bootstrap reader were used. These actors provide diagnostic
thread names only; they do not implement FC/model behavior or establish flight.

The parent creates a namespace-filtered BPF map/program/link before its actors,
then passes map/link descriptors to the collector child and closes all parent
copies. The child checks creator/boot/namespace/library provenance and kernel
FD identities. Actual BPF kernel IDs match the retained sched_switch fields;
raw procfs stat/status/namespace evidence binds their local identities and
lifetimes before and after sampling. All nine targets and five owner groups
were independently rechecked in `independent-check.json`.

Run 04 recorded zero map-update failures and zero trace-buffer loss. BPF was
detached before any formal-window transition. Bootstrap residual events were
stopped and retained with the bootstrap bytes, and the private trace instance
was removed. All actors exited 0; all source hashes remained unchanged during
the run. The five source snapshots match `run-04/inputs.json` exactly. A later
collector change includes all nine comm names in the initial bootstrap filter;
that outer orchestration change is outside this canary's validation scope.

Run 01 failed before creating actors because the initial Python wrapper used
65,536 map entries and a 512-byte verifier buffer, inconsistent with the native
ABI bounds. The wrapper was corrected to 4,096 entries and 65,536 verifier
bytes. Run 02 then passed. Run 03 added parent/boot/source guards; run 04 added
raw procfs evidence and the sealed bootstrap tail. All results are retained;
`file-manifest.json` inventories the original Linux files and excluded native
shared libraries. No binary is published.

The profiler integration starts BPF before native children, waits for mappings
while draining bootstrap trace, detaches BPF before the formal window, and
verifies task lifetimes afterward. The trace is deliberately stopped while
switching filters; `bootstrap_to_filtered_gap_ns` records that excluded
transition, so it cannot be mistaken for a continuous formal window.
Physics/input/clock/rate thresholds are unchanged. The Windows wrapper defaults
to `kernel_bpf` and requires complete mapping and descriptor cleanup evidence.

This mechanism check is a prerequisite for the next fresh real scheduler run,
not scheduler/SITL/rate/clearance/Full acceptance. Actual runs used
`/root/wksim-kernel-pid-binding-canary-20260912-01` through `-04` in Ubuntu-22.04.
