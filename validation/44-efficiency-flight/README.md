# Six motor-efficiency flight audits passed

See `matrix.json` for exact runs, epochs, model/random state and audit results.
Each run subdirectory retains its original result plus a compressed raw archive
and per-file hashes. Failed AP baseline attempts 01/02 are retained separately.

The tracked implementation and run commands are described in
`docs/2026-09-10-motor-efficiency-flight-report.md`. Build a current Control
candidate before a new run; the final AP candidate is 8EMCw6. Original PX4 runs
used WjBuqN, with their exact installed source retained in the archives.

Raw archives contain public/native DDS CDR, original actuator packets, every 1ms
native physical interval and its 16 ODE4 samples, event/origin files, source
snapshots and terminal/cleanup evidence. They do not redistribute vendor model
source or binaries. All raw files were checked again after archive creation.
