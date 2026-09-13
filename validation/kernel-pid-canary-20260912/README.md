# Self-only native kernel PID helper proof

`kernel_pid_canary.c` compiled with the existing GCC and ran successfully in
Ubuntu-22.04 on Linux `6.6.87.2-microsoft-standard-WSL2`. No compiler/package
installation was needed. The kernel verifier accepted the UAPI instruction
program and its short-lived raw `sched_switch` attachment.

For this owned process the helpers returned:

- namespace inode 4026532221, namespace device 4;
- local TID/TGID 696;
- kernel TID/TGID 1115;
- monotonic observation 7330660813 ns.

The BPF program requires both the selected namespace and the exact canary TID
before recording an entry in its one-entry map. It uses
`bpf_get_ns_current_pid_tgid` for the namespace identity and
`bpf_get_current_pid_tgid` for the kernel identity, as defined in
[Linux's BPF UAPI](https://github.com/torvalds/linux/blob/v6.6/include/uapi/linux/bpf.h).
All attachment/program/map descriptors are closed before the result is emitted;
there are no pinned objects, signals, target-process modifications or SITL run.

`manifest.json` records source/compiler/binary hashes; `verifier.log` and
`result.json` are original output. The compiled binary stays in the private
Linux workspace. This is a capability proof for one process. Multi-owner
coverage, FC thread identity, pre/post lifetime binding, direct trace-field
cross-check and collector startup integration remain to be implemented.
