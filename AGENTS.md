# wksim: Prometheus migration

This checkout derives from amov-lab/Prometheus. The upstream commit is recorded in `docs/codebase-memory.md`. Preserve upstream attribution and use Prometheus control, messages, and experiments as the migration source.

## Discovery

- Read a known source file directly. Use text search for literals, diagnostics, configuration, ROS message definitions, and launch files.
- For unknown symbols, call paths, impact analysis, or architecture, check Codebase Memory project `wksim-prometheus` with `index_status`, then use `search_graph`, `trace_path`, `query_graph`, or `get_architecture`. See `docs/codebase-memory.md` for the local CLI fallback and coverage limitations.
- If MCP tools are unavailable or fail to start, immediately use the native CLI with the explicit cache/runtime environment in `docs/codebase-memory.md`, starting with `index_status`. Report a graph failure only after that fallback fails; use direct source/text discovery for uncovered files.
- Read actual source before editing or citing graph results. Run `detect_changes` or refresh the index after edits only before a structural query that depends on those edits. Index only this repository, not the parent mixed workspace.

## Migration decisions

For task scope and decisions, read the [Wayfinder map](https://github.com/unununnnn/wksim/issues/1) and the relevant linked ticket. Issues belong to `unununnnn/wksim`; use an explicit `--repo` argument with `gh`.

The user-selected target is UE5.5 display, WSL Ubuntu22.04 with ROS2/DDS, PX4 and ArduCopter SITL, RflySim-inspired module organization, and a minimal MATLAB interface. Consult `docs/sitl-runtime-proposal.md` when changing runtime boundaries; it distinguishes proposals from accepted requirements.

For the 2026-09-09 Luna handoff or a bounded low-cost execution slice, read [lunar模型完整推进指南.md](lunar模型完整推进指南.md), then select one ready child with `python tools/lunar_queue.py next`. Original parent acceptance/dependencies and the existing subagent model policy remain in force.

## Subagent model policy

Choose subagent settings by the actual dispatching (parent) agent's model. When the dispatcher is not `gpt-6-astra`, every dispatched subagent must use `gpt-5.6-luna`, reasoning effort `xhigh` (极高), and Fast enabled (`service_tier="priority"`; use the interface's equivalent Fast setting). When the dispatcher is `gpt-6-astra`, first classify the task: if it is neither difficult nor strongly exploratory (非困难且非强探索), dispatch `gpt-5.6-luna` with `xhigh` (极高) and Fast enabled (`service_tier="priority"`). Determinism is not a routing criterion. For difficult or strongly exploratory Astra-dispatched tasks (困难或强探索), subagents use `gpt-6-astra`, default effort `low`, with `high` selected explicitly only for complex or genuinely uncertain work; retain its existing speed setting. Apply this rule to new, nested, and resumed delegations, evaluating the immediate dispatcher each time. Explicitly select and verify the applicable model, effort, and speed; if the interface cannot select or verify them, perform the work in the main agent and report the limitation instead of substituting settings. If the dispatcher's model is unknown, verify it before delegating. This policy changes delegation settings only, not the main conversation's model, effort, or speed.

## Standalone project boundary

Use this directory as the project root and `origin` (`https://github.com/unununnnn/wksim.git`) as its only project remote. Read this repository's `CONTEXT.md`; parent and sibling project context is not an implementation dependency. For local build/runtime resources use the project-owned locations in `docs/project-isolation.md`. Preserve upstream attribution and historical evidence, while keeping new code and builds independent of sibling working copies.
