# Real kernel-BPF scheduler run: bootstrap reader backlog

Run `scheduler-72e2be6fc16f`, epoch `7c16f0a5c08e4770a07b7c7b06442adb`,
used baseline `2834161` in a fresh Ubuntu-22.04 directory. Resource preflight
passed, the inherited BPF descriptors were accepted, and all nine native target
kernel IDs were obtained. The scene reached tick 3008 without an authority fault.
The diagnostic still failed its unchanged three-second mapping deadline.

The saved trace prefix ends at 167.477076 seconds while terminal CPU stats are
around 168.515 seconds. There were 16,475 unread ring entries. DDS was born at
start tick 16762 and still had a BPF observation at 168.510311016 seconds, but
its events were not in the consumed prefix. `reader-lag.json` independently
records the raw timestamps, input hashes, per-CPU counts and all nine targets.
This is evidence of reader backlog, not evidence that DDS was inactive.

The mapper performed a full procfs inventory after each short trace_pipe read.
The fix drains batches under a 5ms/about-1MiB budget with a fixed large read
buffer and runs the expensive binding checks about every 50ms. The complete
nine-target trace cross-check, five-owner lifetime checks and three-second
deadline remain required. Failure cleanup now also drains the stopped private
ring to EAGAIN/EOF, with an explicit failure if its separate cleanup deadline is
exceeded. Late tail bytes cannot turn a timed-out mapping into success.

This original run remains failed: no formal ten-second capture was produced.
The Windows launcher verified `need_cleanup=false`, `cleanup_verified=true`;
the parent and collector probe handles were closed, the trace instance removed,
and all epoch groups retired. Original reports are unmodified. Large raw logs
are losslessly gzip-compressed in the published copy, with original and archive
hashes in `linux-file-manifest.json`. The original Linux directory remains
`/root/wksim-scheduler-probe-20260912-kernel-bpf-02`.
