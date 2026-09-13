# Final-combination PV attempt: failed

Source commit `0769c3a`; run `joint-public-flight-nqyqcagl`, epoch `293c42f44d224b47b3077a99ce3f3936`. Command: the exact `bash tools/run-joint-flight.sh` invocation in `docs/2026-09-09-final-combo-pv-plan.md` at that commit, including the fresh ZlTVa4 Control candidate and both unchanged AP/message hashes. The recorded ArduCopter argv contains both native profile flags. No timing-probe or relaxed rate flag was used.

The run exited 1 after 178.577832652 wall seconds. At tick 53128 the unchanged 100ms cumulative lateness guard latched `RateUnmet('rate_unmet/resource_insufficient')`: actual lateness 104260439ns, measured rate 0.499509428482496, requested rate 0.5. Both aircraft had taken off but neither completed its task. This is not PV or Full acceptance; it provides no completed 60s airborne-window proof.

The runner reports source_unchanged=true, normal Control shutdown, no cleanup errors and no remaining child process-group members. A separate post-run `/proc` scan of all ten owned PGIDs found no members; see `independent-cleanup.json`. This is cleanup after a failed run, not completion of its normal LAND contract.

`summary.json` lists selected original files with byte lengths and SHA256. The compressed rate log was decompressed and compared byte-for-byte. All original truth, clock, wire, native and failure records remain in `validation/joint-public-flight-nqyqcagl/` and `/root/wksim-joint-flight-0tosni88`; this published subset excludes vendor sources and binaries.

The first audit command used the documented relative input path and failed its absolute-path identity guard. That result is preserved in `../pv-audit-20260912-nqyqcagl.json`. Repeating only the read-only audit with the resolved absolute path reached the actual failed-run guard: `Candidate run/cleanup did not pass`; see `../pv-audit-20260912-nqyqcagl-absolute.json`. Downstream physical checks remain unaccepted. No flight was repeated and neither failure was rewritten.
