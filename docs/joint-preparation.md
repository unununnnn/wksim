# Prepare a joint run before executing physics

The default `tools/run-wksim.sh CONFIG` entry still creates and executes a fresh run. Joint scenes optionally support an operator-controlled launch order:

```bash
tools/run-wksim.sh CONFIG --output-root OUTPUT --prepare-run
# Read the returned run_dir and session.json instance_id; start View and wait
# for its transport readiness in the operator harness.
tools/run-wksim.sh CONFIG --output-root OUTPUT --use-prepared-run RUN_DIR
```

Both commands retain the normal private Linux isolation check and acquire the run ID, output path and display resource reservation. Preparation releases its reservation when it returns. Its JSON `status: prepared` means only that identity files and empty `epochs`, `actions` and `action-results` directories exist. It starts no flight controller, model, ROS or control nodes, advances no clock and makes no flight or resource readiness claim. Execution reacquires the reservation and immediately follows the ordinary joint epoch lifecycle; it never waits for View.

Use the same normalized configuration and output root for both commands. `RUN_DIR` must exactly identify `OUTPUT/run_id`. The manager creates a random instance ID; callers cannot choose it. `session.json` retains its version 1 schema. `preparation.json` version 1 binds state `prepared`, run ID, instance ID, canonical run directory, owner UID and SHA256 of normalized sorted compact JSON configuration. Before execution, validation rejects missing/malformed/foreign identities, changed configuration, unsafe ownership, symlink paths/files, nonempty action/epoch directories and unexpected files. An exclusively created, flushed and fsynced `execution.started.json` records state `consumed` before any epoch launch. A consumed directory cannot be replayed even if execution fails; prepare a new run ID instead.

These public options are exclusive, require `joint_scene` and cannot combine with `--preflight`. The hidden `--prepared` flag solely marks sourced runtime overlays and is unrelated. Preparation runs before overlay loading; execution carries `--use-prepared-run` through overlay reexecution. No rate budgets, physical steps, setup files or task completion semantics change.

File lifecycle checks: `python3 -B -m unittest validation.test_joint_preparation`. These tests launch no flight or display processes. The ownership case requires Linux root; symlink cases require symlink support.
