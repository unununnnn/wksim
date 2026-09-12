# Verified real ground scheduler capture

Baseline `6d38b54`, run `scheduler-086648004be0`, epoch
`1c404fd36f8543e19b9d083c8e437cdc`, Ubuntu-22.04. The Windows launcher returned
`diagnostic_captured_and_retired` and verified cleanup after 81.73 seconds total.

The formal capture lasted 10.000188298 seconds. Its 44,273,034 bytes contain
321,461 independently checked events: 162,926 scheduler switches, 78,753
wakeups and 39,891 write entry/exit pairs. Every captured event is inside the
declared formal time interval and satisfies the exact target PID filter. All
raw overrun, commit-overrun and dropped-event counters are zero. No fsync or
fdatasync event was observed in this ground window; absence is not a failed
identity proof or a claim about flight logging.

All nine target task identities and five owner lifetimes were checked against
the BPF helper words and raw procfs stat/status/namespace snapshots. BPF was
detached before the formal window; the parent and collector closed their probe
descriptors. The private trace instance was removed and all epoch groups
retired. Native simulation reached tick 12184, synchronized, with no authority
fault and unchanged source hashes. The short timed segment measured 0.9937333x
at requested 1x; worst cumulative lateness was 77,256,332ns, below the existing
100,000,000ns failure threshold.

The bootstrap prefix is retained separately in the 49,900,326-byte full trace.
There is an explicitly recorded 72,915,263ns gap while sealing bootstrap and
changing filters. It is outside the formal interval and is not presented as
continuous capture. The mapper now drains short reads in batches instead of
performing a full procfs scan after each read; all nine bootstrap trace/kernel
PID matches and the original three-second mapping deadline remained required.

`independent-check.json` records raw-event, PID, time-window, hash, counter and
retirement checks. `linux-file-manifest.json` describes original files and the
losslessly compressed published copies; `archive-check.json` independently
checks all 75 retained files from Windows. Native binaries, runtime binary data
and duplicate source trees remain in the original Linux directory:
`/root/wksim-scheduler-probe-20260912-kernel-bpf-03`. Original reports are unchanged.
The exact launcher source is retained because its CLI was subsequently changed
to print a compact summary instead of duplicating the full report on stdout.

This completes one owned ground diagnostic and its trace/identity/cleanup
verification. It is explicitly `acceptance_eligible=false`: not a flight,
long-duration rate test, mixed/PV acceptance, G6 budget result or Full completion.
