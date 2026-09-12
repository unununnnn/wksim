# Failed real scheduler run: visible WSL PID scope is not kernel scope

Baseline `5374afc`; Ubuntu-22.04; run `scheduler-cb5f52f63cd2`, epoch
`d0f9ba4b0e6f470099ca3a83c14ea079`. The Windows launcher used a fresh Linux
directory `/root/wksim-scheduler-probe-20260912-rootproof-01` and the retained
`exchange/` directory, with timeout 240 seconds and EOF cleanup grace 100 seconds.
Resource preflight passed. This diagnostic failed and is not rate/flight evidence.

The actual bootstrap trace disproved the former assumption that the visible
`wsl --system` PNS-0 row is the initial kernel PID namespace:

| Owner | System procfs ID, formerly labeled global | Actual sched_switch PID |
| --- | ---: | ---: |
| AP model worker | 2350 | 20191 |
| PX4 model worker | 2354 | 20195 |
| Supervisor | 1631 | 18931 |
| AP FC leader | 2352 | 20193 |

The system procfs root inode was 4026532210. Linux defines the initial PID
namespace inode as `PROC_PID_INIT_INO = 0xEFFFFFFC` (4026531836), independently
of a visible namespace hierarchy's missing-parent representation. See
[Linux v6.6 proc_ns.h](https://github.com/torvalds/linux/blob/v6.6/include/linux/proc_ns.h).
The corrected scope verifier explicitly marks nested system views and the
collector rejects them before treating their IDs as kernel IDs. This is a
correct rejection, not completion of the required mapping implementation.

Two additional failures were exposed:

- The first-step diagnostic gate stopped calling the product health callback.
  The lifecycle permission gap from 730.031917026 to 731.708533131 seconds
  exceeded the existing 0.5-second scene lease. Both tasks rejected expired
  permission before sending commands. The hook now calls the same product
  health callback while keeping tick zero; the lease and rate limits are unchanged.
- A daemon thread blocked in buffered stdin caused Python's
  `_enter_buffered_busy` shutdown abort (exit 134). The watcher now uses
  `select`/`os.read` on Linux and is stopped/joined in cleanup. Collector failure
  also bypassed metadata collection; cleanup now validates and preserves its
  original partial terminal metadata instead of losing removal evidence.

The original Windows result remains `need_cleanup=true`: its missing capture
summary could not prove retirement. The later independent audit in
`independent-retirement.json` verified the same boot, every saved owned process
identity gone, no manager group, and the exact private trace instance absent.
Collector metadata independently recorded `instance_removed=true`. Applying
the repaired metadata reader to the original files verifies cleanup while
retaining `complete=false`; see `replay-cleanup-verification.json`. No user
process was killed and no original report was rewritten.

`linux/` preserves the raw JSON/JSONL/log/trace/parameter evidence. The full
original file inventory and hashes, including files retained only in the Linux
run, are in `linux-file-manifest.json`. Native runtime data and copied source
trees are not duplicated here. `original-sources/` pins the four changed
diagnostic sources and matches their original recorded hashes.

Validation after the fixes: 97 tests and 32 subtests passed in Ubuntu,
including actual subprocess EOF and normal exit while the parent keeps stdin
open. Separately, 61 snapshot/collector tests and 20 subtests passed, with the
live snapshot test deliberately not selected for that pure scope check.

Before another real scheduler run, implement and verify a true kernel/local
PID binding for all five owners and required FC threads. The adjacent
`kernel-pid-canary-20260912` result demonstrates the two BPF PID helpers on one
owned process only. It does not supply the complete collector integration.
