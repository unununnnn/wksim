# Prometheus Codebase Memory

2026-09-07 维护刷新：原生 CLI（显式 CBM_CACHE_DIR/CBM_RUNTIME_DIR）fast+persistence 成功，快照 **50,515 节点 / 163,780 边，ready**，日志 `C:/CBMData/logs/wksim-prometheus-1788790869.log`。覆盖本轮恢复修订/回滚/验证驱动改动后的结构查询基础；部分解析仍为既有第三方头文件，非新缺口。

2026-09-07 RGB 接入前结构查询：先 index_status/detect_changes，再 fast+persistence 成功刷新为46,541节点/158,981边（日志 C:/CBMData/logs/wksim-prometheus-1788745406.log）。图定位 View.start/_work 后读取实际 visual.py。此后新增 RGB/GameMode/准入代码只按已知路径读取，不宣称旧图覆盖新改动；下次依赖新结构的查询仍先检测/刷新。

正式联合入口跟进（2026-09-06/07 JST）：本轮在结构探索前成功刷新并持久化，快照为 **2026-09-06 13:34:37 UTC，46,110 nodes / 155,626 edges**，日志 `C:/CBMData/logs/wksim-prometheus-1788701677.log`。后续 MCP `index_status` 读回同一项目/root 和 ready 计数，见 `validation/product-joint-entry-20260906/index-status.json`；此前600527/712312及持久化失败是历史状态。新正式入口/配置/动作/监视模块在该快照之后添加，之后只按已知路径读取实际源码，并以逐epoch源码副本/哈希、真实运行和原始审计复核；没有用旧图推断新调用结构。下一次依赖这些改动的结构查询仍须检查/刷新，ready和计数不代表Full覆盖或所有路径已索引。

原生状态周期/独立PX4跟进（2026-09-06 JST）：Node恢复前提、Task显式原生保持和实验JSON原子交接已有当前源码真实回归；外部PX4源码通过固定提交、42,012文件/40仓库清单及两个补丁核验。图状态仍600527节点/712312边，Node/Task metadata_changed，新测试not_tracked，工具按tools排除，详见 `validation/native-state-observation-20260906/index-coverage.json`。本轮按已知路径直接读取源码，没有依赖新结构的图查询；下一结构查询仍须检查/刷新，不冒称此前持久化问题解决。[报告](2026-09-06_native-state-cadence-report.md)提供构建、真实输入、原始审计和加载映射，图计数不表示验收覆盖率。

真实DDS恢复收口（2026-09-06 JST）：本轮直接读取已知候选/运行器及审计源码，修复授权文件、公开发送日志与原始DDS确认的审计缺口。状态仍600527节点/712312边；精确路径覆盖显示 `Simulator/wksim_runtime/joint_lifecycle.py` not_tracked，两审计工具按tools排除。完整状态与边界在 `validation/joint-dds-recovery-final-20260906/index-coverage.json`，实现/真实运行/负例见[报告](2026-09-06_joint-dds-recovery-report.md)。本轮没有依赖新结构的图查询或不必要全库索引，不声称此前持久化失败已经修复；下一依赖新结构的查询仍须先检查/刷新。

## Checkout and index

获批生命周期跟进（2026-09-06 JST）：新增共享SceneLease和双Control许可/原生发布者GID冻结接缝，Task保持共享ROS时间并等待新原生源后继续。[实测报告](2026-09-06_approved-joint-lifecycle-report.md)记录真实两次4s暂停/四tick/继续/降落和许可失效负向验证。精确覆盖仍为scene及新测试not_tracked、Node/两个适配器/Task metadata_changed、tools排除；[状态](../validation/approved-scene-lifecycle-integration-20260906/index-coverage.json)。本段直接读已知源及封存构建，按源码/运行SHA审查，没有新结构查询或不必要重索引；下次依赖这些新结构的查询须先检查/刷新，旧持久化错误未冒称解决。

空中暂停跟进（2026-09-06 JST）：已知 `ClockPublisher.publish` 新增严格的已提交同步暂停时间重发，tools新增原始DDS观察/审计，真实结果见[报告](2026-09-06_joint-airborne-pause-report.md)。本轮实读仍600527节点/712312边；核心/test_scene_clock为metadata_changed，新测试not_tracked，tools排除。采用精确源读取、历史源快照差分和当前运行SHA核验，没有依赖新改动的结构查询，也未为报告全库刷新。此前完整索引/持久化失败仍未验证修复；下次新结构查询前须按路由检查/刷新。[本轮状态](../validation/joint-pause-integration-20260906/index-state.json)。

连续联合公共任务跟进（2026-09-06 JST）：新增 `Simulator/wksim_core/joint.py`、修改Task/MissionTask身份及ControlNode显式ROS操作时基和正常退出；实际双FC公共任务/当前源码审计见[报告](2026-09-06_joint-public-flight-report.md)。本轮状态仍可读600527节点/712312边；精确覆盖显示JointPhysics为not_tracked，Task/Control为metadata_changed，tools排除。此前刷新/持久化失败未宣称解决。本轮围绕精确已知源码和新建文件工作，不作依赖这些新增结构的图断言；状态归档不重复全库索引。当前证据与覆盖导航 `validation/joint-flight-integration-20260906/`，下一结构查询仍按前述刷新/覆盖规则处理。

联合核心接缝跟进（2026-09-06 JST）：新增 `Simulator/wksim_core/worker.py` 与 `Simulator/wksim_runtime/scene_clock.py` 后，在依赖新增结构的查询前尝试 MCP fast+persistence，返回 Pipeline failed；立即按固定 CBM_CACHE_DIR/CBM_RUNTIME_DIR 原生 CLI 重试，仍返回error/退出1。数据库可读视图随后为600527节点/712312边，覆盖generation=2026-09-06T03:45:49Z，但仓库 `.codebase-memory/artifact.json` 仍20:55:31Z旧快照。只称部分更新，不能把ready当作完整刷新/持久化成功；未删除旧库或改全局权限。两新核心及测试文件为no_recorded_issue/metadata_changed，工具按tools排除。当前工作直接读实际源码并核对真实运行SHA；完整状态见 `validation/scene-clock-integration-20260906/index-state.json` 和[报告](2026-09-06_scene-clock-lifecycle-report.md)。下一依赖这些新结构的图查询仍须先确认可用性/持久化状态；下文是历史记录。

原生时钟/停机跟进（2026-09-06 JST）：[报告](2026-09-06_native-clock-and-stop-report.md)归档了两次真实双DDS只读观测与AP停止精准诊断。775条真实AP微秒样本全部匹配源代码浮点/整数累计网格，亏差48–1820µs；并非与模型精确同钟。停流TERM不退出的13次单AP尝试另有真实栈/标志/恢复对照。只改tools中的实验观测/审计与文档，产品核心/飞控/安装包未变；本轮index_status仍20:55:19UTC、92,892节点/202,270边、ready。新工具按tools祖先排除，外部AP/PX4源/类型依然直接读源和哈希，不宣称已入图或为归档重复索引。下一依赖改变后产品结构的查询仍先检查/刷新。#8候选尚未获批，G2未完成。

联合时间地面调查（2026-09-06 JST）：[#8有界验证报告](2026-09-06_joint-clock-ground-report.md)与[AP固定源码研究](2026-09-06_joint-clock-source-research.md)已归档。两个独立模型进程由唯一整数tick调度器推进，真实双FC两次地面重复及逐条审计通过；不等于G2或生产调度批准。本轮index_status实读ready，仍20:55:19UTC、92,892节点/202,270边；精确覆盖确认 `tools/probe_joint_clock.py`、`audit_joint_clock_probe.py`、`run-joint-clock-probe.sh`、`test_probe_joint_clock.py` 按tools祖先排除/not_tracked。复用model.cpp/model.py/ap_json.py/px4_mavlink.py无记录解析缺口但metadata_changed，直接读源并核对运行SHA。外部WSL飞控源不在图内；本轮不改这些产品文件，也没有依赖新结构的查询，因此不为工具/报告重复全库索引。

最新工作台动作快照（2026-09-06 JST）：接入 `Workspace.mission_action`、保守 `LiveRunReader._action_offer`、确认代次文件校验和原生HTML暂停/恢复后，在依赖新实现的结构审查前读index_status并用明确缓存/运行路径的原生fast+persistence刷新，36.708秒成功。快照 **2026-09-05 20:55:19UTC，92,892节点 / 202,270边**，metadata20:55:22，artifact20:55:31；日志 `C:/CBMData/logs/wksim-prometheus-1788641731.log`。

MCP实读ready，5个精确动作/反馈入口完整返回、has_more=false，随后复读源码。五个实际实现文件没有记录解析缺口，但freshness仍为metadata_changed；工具按tools祖先排除，直接读取。998partial/371excluded/0skipped不表示功能完成率。当前源码另与服务启动快照和4次真实双栈正式结果独立哈希核验。完整查询、运行和残留记忆位于 `validation/operator-mission-actions-20260906/` 及 [本轮报告](2026-09-06_console-mission-actions-report.md)。下列快照为历史；后续仅报告变更不重复索引，下一依赖源码变化的结构查询仍先检查刷新。

最新任务生命周期快照（2026-09-06 JST）：实现 `MissionTask` 显式暂停/恢复、`ActionMailbox`、会话请求高水位和受监督物理寿命后，在依赖新实现的结构查询前以指定 CBM_CACHE_DIR/CBM_RUNTIME_DIR 原生 fast+persistence 刷新，38.633秒成功。快照 **2026-09-05 20:17:24 UTC，87,512节点 / 196,679边**，metadata recorded_at20:17:27；日志 `C:/CBMData/logs/wksim-prometheus-1788639456.log`，本地归档 `validation/mission-lifecycle-integration-20260906/memory-index.log`。

MCP index_status 实读 ready；精确查询返回6项且 has_more=false，包括 `MissionTask.pause_and_resume`、`allowed_actions`、`Task.receive_session`、`ActionMailbox.poll`。查询及四个实际实现文件的覆盖记录见同目录 `memory-query.json`；实际源码另行读取。四文件没有记录解析缺口，但 freshness 仍是 metadata_changed，不宣称完全解析；tools 验证器按祖先排除，仍走直接读取。991个partial、368个excluded、0skipped是索引元数据，不是功能完成率。后续只写报告不重复索引，下一依赖新源码的结构查询仍须检查变化。

- Source: https://github.com/amov-lab/Prometheus
- Upstream commit: `5dcd8cfa764d558f3e15dcb88aa7d49e32c54cce`
- Checkout: `C:/Users/PC/Documents/odid编译/wksim`
- Local branch: `codex/prometheus-sitl`
- `origin`: `https://github.com/unununnnn/wksim.git`; `upstream`: Prometheus.
- Codebase Memory project: `wksim-prometheus`, initially indexed with version 0.10.8, `fast` mode and persistence enabled.
- Initial source graph: 39,877 nodes / 138,297 edges; `index_status` returned `ready`.
- After adding validation material, the refreshed snapshot contains 39,904 nodes / 138,330 edges; current counts and timestamp are in the artifact metadata.
- After implementing the independent model and both FC physics adapters, the 2026-09-05 05:04:11 UTC snapshot contains 40,411 nodes / 139,215 edges. `Model.step`, `wk_model_step`, and `Lockstep.update` are searchable under `Simulator/wksim_core`. The scope check only recorded its excluded `__pycache__` subtree; this is not a completeness guarantee. `tools/validate_sitl_physics.py` remains a direct-read file because `tools` is excluded by design.
- Shareable artifact: `.codebase-memory/graph.db.zst`; metadata: `.codebase-memory/artifact.json`.

2026-09-05 UE implementation follow-up: after new `Simulator/ue55` sources, MCP indexing first produced 42,940 nodes / 142,440 edges. A later MCP refresh returned `status=error` (pipeline failure); the prescribed native CLI fallback refreshed successfully at 06:27:29 UTC to **44,399 nodes / 144,211 edges**. Log: `C:/CBMData/logs/wksim-prometheus-1788589652.log`. Subsequent MCP search located `AWksimVisualGameMode.ApplyPacket` at line138, `packet_from_truth` at39 and `actor_errors` at62. `Tick → ApplyPacket` is LSP0.95; a heuristic0.50 self-call is not present in the source and must not be treated as real recursion. Source was read directly.

The `Simulator/ue55` scope has a partial UCLASS header at lines11/14/42/45 and an excluded `__pycache__`; `tools/validate_ue55.py` remains excluded by the `tools` ancestor. Freshness reports `metadata_changed` even after this refresh: source/staged build and run-source hashes were independently checked in `validation/ue55-checks-913993ff/integrity.json`, rather than claiming complete or automatically fresh graph coverage. The [UE report](2026-09-05_ue55-report.md) indexes the actual live-flight, screenshot and failure evidence. Validation artifacts contribute to aggregate counts; these counts are not equivalent to migrated source coverage.

2026-09-05 DDS implementation follow-up: the native CLI again returned `ready`, 40,411 nodes / 139,215 edges. New DDS diagnostics and bootstrap/build launchers are under the intentionally excluded `tools/` directory; read those files directly. Their implementation, pinned dependency/build paths, clock fix and live dual-flight evidence are indexed by [the DDS report](2026-09-05_native-dds-report.md), not silently claimed as graph coverage. No indexed model source changed in that phase, so an unnecessary re-index was not run.

### Live MCP usage check after connection repair

The MCP tools became available in this task on 2026-09-05. Actual calls to `list_projects`, `index_status`, `detect_changes`, `search_graph`, `trace_path`, and `check_index_coverage` succeeded against `wksim-prometheus`; this was not merely a CLI or configuration-health claim.

- `index_status`: ready, 40,411 nodes / 139,215 edges, root `C:/Users/PC/Documents/odid编译/wksim`.
- `search_graph` located `Model.step` in `Simulator/wksim_core/model.py:75` and `Lockstep.update` in `Simulator/wksim_core/ap_json.py:54`; the paginated Model search was exhausted.
- Outbound depth-1 trace from `Lockstep.update` returned `decode_servos` and `sensor_message` (LSP, confidence0.95), plus `Model.step` (heuristic, confidence0.24). Direct source confirms the call at `ap_json.py:61`; the low-confidence graph edge alone is not proof.
- `check_index_coverage` recorded no parser gap for those two files, but returned `freshness=metadata_changed`. Current source was read and both SHA256 values matched the previous physical-flight evidence: model.py `af767e9299e4282da8da168998605c02039ea64d9cc27bb33e9dce24d1a6b77a`, ap_json.py `9ea25a99604fd1d585c7cb7c34e41646d382dab3383cb91689598cfdc098f3ff`. This qualifies the metadata warning; it does not make coverage complete. `detect_changes` only summarized eight untracked directories/files with zero seed symbols, which is not evidence of no changes.
- `tools/sitl_dds.py` and `tools/validate_sitl_physics.py` were explicitly reported excluded by the `tools` ancestor. External FC sources under WSL `/opt` or `/root` are outside this project and must be read there, not inferred from a different ArduPilot graph/version.

No source was changed by this usage check and no index was rebuilt for demonstration. Recheck freshness and refresh as needed before the next structural query that relies on changed or uncovered sources.

This is a shallow, source-focused sparse checkout. Git records the upstream tree, while selected source/config/document extensions are materialized. Large meshes, textures, datasets, binaries and gitlink contents are not fetched for this index. `git sparse-checkout list` shows the exact selection. Expand a required asset directory explicitly before using it; initialize only submodules needed for the current task. Absence from the working tree is not proof of absence upstream.

2026-09-05 Prometheus ROS2 follow-up: `detect_changes(scope=files)` reported ten untracked top-level paths including `ros2/`, but zero seed symbols; this did not mean no source changed. Exact coverage checks for the then-new `ros2/src/prometheus_msgs/msg/UAVCommand.msg`, `CMakeLists.txt`, and `validation/test_prometheus_interfaces.py` returned `freshness=not_tracked`; the migration/build-test Python tools remained excluded by `tools`. This phase used direct schema/config/source reads and a pinned Git inventory, with actual Humble compilation and runtime evidence in [the ROS2 interface report](2026-09-05_prometheus-ros2-report.md). No structural query depended on those new files, so no gratuitous full re-index was run. At that point the snapshot was still 06:27:29 UTC, 44,399 nodes / 144,211 edges, not claimed to cover the port; the later command-library refresh is recorded below.

2026-09-05 command-library follow-up: after adding `ros2/src/prometheus_control`, a dependent structural query required a fresh index. MCP indexing succeeded at **07:22:53 UTC**, **44,795 nodes / 145,330 edges**; log `C:/CBMData/logs/wksim-prometheus-1788592976.log`. A complete four-result query located `CommandProcessor.update_state` (86–103), `accept` (130–167), `step` (179–214), and `resolve_move` (216–243). Source was read directly. A query for the upstream C++ methods first used the wrong `Function` label and returned no rows; using `Method` found all39 methods, so the empty result was not treated as absent source.

The exact `ros2/src/prometheus_control` scope has no recorded parser gap, but freshness still reports `metadata_changed`. The repository, staged build and installed `command.py` independently match SHA256 `38c2899e53d9946faa47691cb98586e70e6db349fad9772bf65a9d1b09d284dc`. `validation/prometheus-command-e_8fywjj/result.json` records the actual installed module path, source/test/oracle hashes and102 original-C++ differential cases. Full32-test/build evidence is indexed by [the command report](2026-09-05_prometheus-command-report.md). New tools remain intentionally excluded; later documentation and tool-only provenance edits do not imply the graph became automatically fresh or complete. Refresh again before a structural query that depends on subsequent indexed-source changes.

## Query from PowerShell

2026-09-05 原生控制节点跟进：新加`frames.py`、`native_px4.py`、`native_arducopter.py`、`node.py`后，在依赖新结构的图查询前刷新。最终快照 **09:53:16 UTC，49,282 nodes / 151,821 edges**，日志 `C:/CBMData/logs/wksim-prometheus-1788601998.log`。完整四结果查询定位`ControlNode.on_setup`103–164、`on_command`166–188、`tick`241–259、`drive`261–301；随后实际源文件已读取。`drive`的一层出向查询返回11项、未分页；CommandProcessor与Shaper调用为LSP0.90，动态适配调用部分为heuristic0.12–0.28，图只解析出AP一侧，不能据此断言没有PX4分支，实际源码与双栈运行另作证明。

四个新模块和`validation/test_prometheus_native.py`没有记录解析缺口，但freshness仍为`metadata_changed`。`detect_changes`报告11个未跟踪顶层路径、0 seed，不代表没有修改。仓库、构建副本和安装包七个Python文件已逐项哈希核对；两个真实任务使用相同安装代码，详见[原生节点报告](2026-09-05_prometheus-native-report.md)和`validation/prometheus-native-checks-33tTFL70/manifest.json`。`tools/`仍按设计排除，状态补丁因后缀被排除；外部WSL飞控源不在本项目图内。测试日志等资产影响aggregate counts，不把图大小视为迁移覆盖率。后续若结构查询依赖新的源码变更，须再次检查刷新。

2026-09-05 output-shaping follow-up: the source graph was refreshed before querying the new indexed module. Snapshot **07:54:03 UTC**, **45,281 nodes / 146,213 edges**, log `C:/CBMData/logs/wksim-prometheus-1788594845.log`. The four-result query located `SetpointShaper.__init__` (60–68), `reset` (70–74), `shape` (76–121), and `_velocity` (123–154). The control package and new oracle have no recorded parser gap; freshness still reports `metadata_changed`, not a completeness guarantee. Source/staged/installed `shaping.py` SHA256 independently agrees: `56782d96f9fc6f7df3ddadf80cd8c09f474af81c5c183d20d3d26c2f9e66bc69`. `tools/validate_prometheus_shaping.py` remains deliberately excluded. The [output-shaping report](2026-09-05_prometheus-shaping-report.md) records40 regressions and332 oracle cases, including intentional differences rather than claiming universal equivalence.

Before implementation, graph traces found `send_pos_cmd_to_px4_original_controller` as the single direct caller of each velocity shaping function (LSP0.95). The actual dispatcher, both output functions, estimator offset callbacks, header defaults and `math_utils.h` were read. An over-constrained regex-style `file_pattern` returned no rows; an exact-path Cypher query found12 send methods. That empty navigation result was not treated as absent code. Upstream source is unchanged; read sources and the evidence report before using the graph to infer behavior.

2026-09-05 ArduCopter position/yaw follow-up: the actual fixed FC source under WSL was read directly because it is outside this graph. A four-file optional patch, isolated builder and bounded validation now have [source/build/flight evidence](2026-09-05_arducopter-dds-yaw-report.md); the Prometheus command/shaping implementation itself did not change. MCP `index_status` still returned ready, 45,281 nodes / 146,213 edges at the 07:54:03 UTC snapshot. Exact coverage calls confirmed the four diagnostic/build tools excluded by `tools`; the new `validation/ap_dds_yaw_boundary.cpp` and patch were `not_tracked`, and `validation/test_sitl_dds.py` was `metadata_changed`. These are direct-read sources, not newly claimed graph coverage. No structural query depended on the new harness, so no unnecessary full re-index was run. Refresh before a dependent structural query; 41 unit tests and111 native boundary assertions are functional evidence, not graph counts.

If MCP tools are unavailable, use the native CLI against the same project. Set the existing cache/runtime locations explicitly so a restricted child environment does not select a different cache:

```powershell
$env:CBM_CACHE_DIR = 'C:/CBMData'
$env:CBM_RUNTIME_DIR = 'C:/CBMRuntime'
$cbm = 'C:/Users/PC/.local/bin/codebase-memory-mcp.exe'
& $cbm cli index_status --project wksim-prometheus
& $cbm cli get_architecture --project wksim-prometheus --path Modules/uav_control --aspects overview
& $cbm cli search_graph --project wksim-prometheus --query 'UAV_controller mainloop' --limit 6
& $cbm cli trace_path --project wksim-prometheus --function-name wksim-prometheus.Modules.uav_control.src.uav_controller.UAV_controller.mainloop --direction outbound --depth 1 --limit 20 --include-evidence true
& $cbm cli check_index_coverage --project wksim-prometheus --scopes Modules/uav_control
```

### MCP startup repair (2026-09-05)

Codex desktop logs reported `handshaking with MCP server failed: connection closed: initialize response`. Launching the executable with a restricted environment reproduced exit code 1: `exact executable identity could not be verified (cache-private)` because the default user-directory DACL granted mutation rights to another SID. The interactive shell already carried `CBM_CACHE_DIR=C:\CBMData` and `CBM_RUNTIME_DIR=C:\CBMRuntime`, explaining why CLI queries succeeded.

The user-level Codex `config.toml` now explicitly sets those two variables under `[mcp_servers.codebase-memory-mcp.env]`. With the same restricted environment plus these variables, MCP `initialize` and `tools/list` passed (version 0.10.8, 15 tools). Existing index status, symbol search and call tracing also passed. No ACL change or re-index was needed. If an existing desktop session still omits the tools, restart this MCP server through Settings > MCP servers and verify its connected status; CLI remains usable meanwhile.

For CLI array flags, the single-value forms above were tested. Passing a JSON-array string directly as a flag value was interpreted as one literal value. For structured arrays, use a JSON arguments file via `--args-file`; see each tool's `--help`.

After source changes, inspect `detect_changes --help` and use it before the next dependent graph query. Re-index only when missing/stale coverage requires it:

```powershell
& $cbm cli --progress index_repository --repo-path 'C:/Users/PC/Documents/odid编译/wksim' --name wksim-prometheus --mode fast --persistence true
```

## Verified coverage and limits

空中显式接管跟进（2026-09-06 JST）：修复 `node.py` / `command.py`，增加 AP-only BRAKE 显式映射及测试；实际边界、失败 LOITER 样本、最终安装 `/root/wksim-ros2-MUlZd0` 和双栈真值见[接管报告](2026-09-06_airborne-takeover-report.md)。在依赖新实现的结构查询前，`detect_changes(scope=files)`仍只返回13个未跟踪目录/文件、seed_symbols=0；随后原生入口使用明确 CBM_CACHE_DIR/CBM_RUNTIME_DIR，fast+persistence 刷新36.346秒成功。

最新快照 **2026-09-05 19:44:17 UTC，86,159节点 / 194,794边**；metadata recorded_at19:44:20，artifact19:44:29。日志`C:/CBMData/logs/wksim-prometheus-1788637469.log`和`validation/airborne-takeover-integration-20260906/memory-index.log`。MCP index_status实读ready；精确名查询完整5项、has_more=false：CommandProcessor.enter_control113–147，ControlNode.on_setup137–218及activate245–255，以及两native adapter的mode_name；实际源代码另行读取与实飞SHA256核对。

上述三个更改源码与新增测试没有记录解析缺口，但freshness仍为metadata_changed，不将其说成完整解析；tools验证器按祖先排除，固定版本WSL ArduCopter源码/二进制日志不属于该图。988个partial/367个excluded/0skipped只是索引信号，不是Full完成率。后续仅归档报告不重复全库索引；下一依赖源码变更的结构查询仍先检查/刷新。以下保留早期快照。

只读遥测跟进（2026-09-06 JST）：此前P450阶段的Pipeline failed，本轮以相同原生入口重试即成功，18:24:31 UTC、79,872节点/187,627边；日志`validation/cbm-repair-20260906/red-baseline.log`名字虽含red，其实际内容为成功，不改写为红色复现。没有修改全局配置/权限/索引目录，也没有证据把恢复归因于某项修复；旧失败原因仍未定位。

新增遥测实现结束、依赖它的新结构查询前，先查index_status/detect_changes（未跟踪目录仍seed_symbols=0，不能证明没有修改），再以指定CBM_CACHE_DIR/CBM_RUNTIME_DIR原生刷新，耗时38.426秒成功。最终快照**2026-09-05 19:06:54 UTC，83,249节点 / 191,465边**，metadata recorded_at19:06:57 UTC，artifact19:07:05 UTC，日志`C:/CBMData/logs/wksim-prometheus-1788635225.log`。本地日志和查询归档于`validation/telemetry-integration-20260906/memory-index.log`、`memory-query.json`。

精确入口查询完整返回4项（has_more=false），含Observer.forward87–127、poll129–137、load_dialect25–41及既有CancelMailbox.poll；随后直接读取实际源码。forward的一层出向图返回5项，其中decode_datagram为LSP0.95；另把bytes的encode/decode误连到Airsim C++和console函数（heuristic0.38/0.21）。实际forward源码没有这些跨模块调用，不采用启发式边证明数据或控制路径，也不以图中缺边证明绝无网络发送。

runtime/telemetry/telemetry_dialect/config/preflight/isolation和测试文件均无记录解析缺口，但freshness仍为metadata_changed，不宣称完整解析。最终真实双栈结果中的所有runtime源码SHA256已独立与现有文件核对。tools/docs按设计排除；外部WSL固件/XML/生成器/生成模块不在本项目图内，按固定版本直接读取和哈希记录。977个partial、365个excluded不是功能覆盖率。新功能和失败证据见[遥测报告](2026-09-06_native-telemetry-report.md)。后续只归档工具/文档不重复索引；下次依赖源码变化的结构查询仍需先检查刷新。以下保留历史失败与早期快照。

P450 显示跟进（2026-09-06 JST）：`WksimVisualGameMode.cpp`、头文件/构建配置和 console `visual.py` 已有新改动，资产来源、原生导入和双栈运行记忆见 [P450 显示报告](2026-09-06_p450-view-report.md)。在计划中的新结构审查前调用 `index_status`、`detect_changes(scope=files)`；后者仍只返回未跟踪目录、seed_symbols=0，不能解释为源码没有变化。MCP `index_repository` 返回 Pipeline failed，随后使用上述明确 CBM_CACHE_DIR/CBM_RUNTIME_DIR 的本地 CLI，先查状态再以 fast/persistence 刷新，也返回相同错误（24.255秒），日志 `validation/operator-p450-20260906/memory-index-native.log`。项目路径和源文件实际存在；磁盘有74.5 GB空闲，未得到更具体的失败原因。未删除旧数据库、未修改全局权限或其他项目。

最后可读图仍为 **2026-09-05 16:36:00 UTC，72,451 nodes / 179,977 edges**，artifact 时间16:36:11 UTC。最新精确覆盖检查显示 GameMode.cpp 和 console visual.py 为 metadata_changed；`tools/prepare_p450_asset.py` 与 `tools/visual_readability.py` 按 tools 祖先排除/not_tracked。因此本轮未用旧图继续依赖新实现的结构查询，实际源码直接读取并以构建/运行 SHA256 核对。ready 只是旧数据库可读，不是刷新成功；下一依赖新结构的查询前仍需修复刷新。下面保留此前成功快照的历史说明。

第四批工作台（2026-09-06 JST）：新增console源码在旧图中为not_tracked；实现结束后为新的结构审查刷新并持久化。最终快照 **2026-09-05 16:36:00 UTC，72,451 nodes / 179,977 edges**，metadata recorded_at 16:36:02 UTC；日志 `C:/CBMData/logs/wksim-prometheus-1788626171.log`。收窄到 `Simulator/wksim_console/*.py` 的精确入口查询完整返回7项、has_more=false：`read_result`56–71、`Handler._dispatch`100–175、`View.start`179–188、`Workspace.start`224–258、`_start_runtime`260–265、`_start_after_view`267–291、`cancel`318–325。源文件已直接读取复核，子进程argv到WSL正式入口的动态边界不靠图补造调用边。

workspace/server/records/visual/app.js 五个精确路径没有记录解析缺口，但freshness仍报告metadata_changed，不声称完整解析。965个partial文件、263个按设计排除文件不是功能覆盖率；tools/docs、外部WSL源和真实日志仍走直接读取。实现/测试与图像/浏览器未通过边界见[第四批报告](2026-09-06_operator-workspace-report.md)。后续仅文档状态归档不再重复索引；新的依赖源码结构查询仍须先检查变化。

第三批任务/取消（2026-09-06 JST）：新增源码在旧图中为not_tracked，因此在依赖新结构的查询前刷新并持久化。快照为 **2026-09-05 15:04:04 UTC，61,826 nodes / 167,560 edges**，metadata recorded_at 15:04:07 UTC；日志 `C:/CBMData/logs/wksim-prometheus-1788620655.log`。精确查询完整返回 `MissionTask.execute`137–179、`dwell_waypoint`204–228、`request_cancel`163–197、`audit_mission_truth`17–90，has_more=false，源文件已直接读取复核。

`mission_task.py`、`mission_plan.py`、`mission_cancel.py`、`mission_evidence.py`、`runtime.py`没有记录解析缺口；freshness仍为metadata_changed，不声称完全解析。956个partial文件及230个按设计排除文件不代表功能遗漏统计；tools/docs及外部WSL源仍不据图作否定结论。实际源码/运行证明见[第三批报告](2026-09-06_product-third-wave-report.md)及其独立SHA256审计。归档只更新文档/状态时不重复全库索引；下一轮依赖改变后结构的查询仍按同一路由刷新。

2026-09-05首批产品入口跟进：源码变化后，在新的结构查询前刷新并持久化。最终索引代次为**12:21:01 UTC，52,918 nodes / 156,535 edges**，artifact写入时间12:21:10 UTC；日志`C:/CBMData/logs/wksim-prometheus-1788610870.log`。两个收窄后的完整查询分别返回UE的`display_packet`19–40、`relay`32–66，以及runtime的`preflight`37–179、`load_evidence`60–149、`run`126–280、`Task.arm_ready`66–72、`Task.execute`147–176，均has_more=false。直接源文件已经读取；此前宽泛run搜索的366项结果没有被当作完整枚举。

上述六个Python文件及GameMode.cpp的精确覆盖查询没有记录解析缺口，freshness仍报告metadata_changed。运行和构建输入通过独立SHA256审计，见[首批产品报告](2026-09-05_product-first-wave-report.md)及`validation/product-first-wave-20260905/audit.json`。tools/docs及缓存/示例等仍按设计排除，外部WSL飞控源也不在该项目图中；931个部分解析文件主要来自既有第三方，不能把节点/边数量作为Full迁移覆盖率。本次后续只修改文档、证据清单和能力索引的四行验收进度，不改变准入/基线规则；无新的依赖源码结构查询，不为状态归档重复全库索引。

2026-09-05第二批隔离/会话跟进：在依赖新结构的查询前刷新并持久化。快照 **13:34:47 UTC，56,975 nodes / 161,724 edges**，metadata recorded_at为13:34:50 UTC；日志 `C:/CBMData/logs/wksim-prometheus-1788615298.log`。精确查询分别完整返回 `Task.restart_on_ground`209–227，以及`RunSession.accept`86–98、`native_identity`100–114，均has_more=false；随后直接读取这些源段。

`task.py`、`runtime.py`、`isolation.py`、`session.py`、`node.py`的精确覆盖没有记录解析缺口，freshness仍为metadata_changed。`tools/validate_control_restart.py`明确因tools目录被排除；外部WSL飞控源码不在本图中。943个partial文件的列表只是解析信号，不是负面功能结论或完成率。独立源码/运行哈希审计、130项测试和真实双栈/UE证据见[第二批报告](2026-09-05_product-second-wave-report.md)。后续只归档文档和不改变准入的工单状态，不为该归档重复全库索引；下一次依赖新增源码的结构查询仍须检查刷新。

`Modules/uav_control` yielded 653 nodes / 2,129 relationships. Symbol search located `UAV_controller::mainloop` at `Modules/uav_control/src/uav_controller.cpp:212`, and a call trace located mode switching, failsafe checks and setpoint publishing. The source was read to confirm those boundaries.

The initial full source snapshot reported 912 partially parsed files, largely in third-party/templates, 16 excluded directories and five individually excluded files. `Modules/uav_control` coverage reported no recorded issue; this is not a proof of complete parsing. The graph contains low-confidence heuristic edges as well as stronger LSP edges. Inspect evidence before inferring dependencies.

Default exclusions include `tools`, `docs` and several `scripts` directories, including Gazebo's Jinja generator and basic demo scripts. ROS `.msg`, launch/config files and excluded scripts must be read or text-searched directly. `fast` mode omits semantic/similarity edges. No ROS2 build, SITL run, asset migration or flight test is implied by index readiness.
