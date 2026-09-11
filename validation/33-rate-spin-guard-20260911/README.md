# Joint-rate final-spin guard diagnostic

These two diagnostic-only host measurements compare isolated 8 ms release
edges.  They are not flight or production-performance evidence.  Both ran in
Ubuntu-22.04 under `SCHED_FIFO` priority 50 and nice -10 with 1,500 samples per
guard.

`measurement-pre-review.json` was produced by source SHA
`6045107981e96bb8c201f7e52fceee567574eb6b05c2d2afecd1a4e65b14442a`.
Its raw samples are retained, but its embedded p95/p99 summaries used a
floor-index definition that understated small-sample tails.  The table below
recomputes those percentiles from the raw values using nearest-rank.

`measurement.json` was produced after changing the summary to explicit
nearest-rank percentiles, source SHA
`a97f711a68d7e7d5898049f8c1c67a0340ad2f983568f434ae1ef31fcf9bdba7`.

| run | guard | mean overshoot | p99 | max | >100 us | mean spin |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| pre-review | 1.0 ms | 1,946 ns | 97,156 ns | 387,738 ns | 15 | 913,784 ns |
| pre-review | 0.5 ms | 1,891 ns | 64,980 ns | 611,214 ns | 10 | 433,145 ns |
| pre-review | 0.2 ms | 1,420 ns | 12,826 ns | 729,025 ns | 7 | 145,140 ns |
| nearest-rank | 1.0 ms | 1,911 ns | 53,658 ns | 530,236 ns | 9 | 928,380 ns |
| nearest-rank | 0.5 ms | 1,955 ns | 53,835 ns | 265,032 ns | 14 | 429,626 ns |
| nearest-rank | 0.2 ms | 3,391 ns | 140,141 ns | 319,152 ns | 20 | 123,320 ns |

The 0.5 ms candidate did not reproduce its advantage over 1.0 ms in the
second run.  The 0.2 ms ordering also reversed.  No production guard change or
new flight run is justified by this measurement; investigation returns to the
observed group-work and host-scheduling tails.

File SHA-256:

- `measurement-pre-review.json`:
  `fcc6082926439c7e8947cd48f8e7bb001d5b22771dd1bd6951895ef1c1ea45d9`
- `measurement.json`:
  `b495bcb2e62e282cfd04a0a02350bfff11cb438460a95665a98fded3a109899f`
