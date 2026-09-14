# CodeBuddy mixed-work-overrun v2（修订版）历史语境绑定与登记（ingest note）

2026-09-14；工作区 `C:/Users/PC/Documents/odid编译/wksim`；本文件写作时权威 HEAD `31e5b65f5448c5558450d16d0f46da0ef0f0a03c`；架构祖先 `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` 经 `git merge-base --is-ancestor` 验证为当前 HEAD 祖先（exit 0）。

## 0. 本文件的地位

本文件只做两件事：把修订版（remediated）`docs/coordination/mixed-work-overrun-20260913-v2.md` **按字节绑定**为历史语境并登记其已复核结论与可复核性限度。它自身不构成任何验收、批准、收口或复核记录；被绑定文件同样不构成这些。本文件为纯只读复核产物：未修改被绑定文件或任何既有文件；未运行 native/构建/MATLAB/ROS/DDS/SITL/飞控/UE/模型/飞行；未提交 Git；未联网；未触碰受保护文件（`docs/Prometheus.gitmodules.reference`、`validation/coordination/short-cycle-dispatches.json`）。

## 1. 绑定对象（字节级）

| 项 | 值 |
| --- | --- |
| 被绑定文件 | `docs/coordination/mixed-work-overrun-20260913-v2.md`（修订版工作树字节） |
| SHA256 / 大小 | `b432e2c3bca0ffbcd7b77dd91304d6a5d064e9d6dabd20a8fba1ec99e8836352` / 5410 bytes |
| 写作时 HEAD 树版本（修订前） | `24ad15729ac393026488f9356f265297a8b4b071c92ab6a501b0fe45bca4893a` / 2863 bytes |

修订内容（新增"可复核性与当前限度"节 + 第 4 点证据链的启动件语义修正）目前是**工作树状态，尚未提交**（写作时 HEAD 树仍为修订前版本）。本绑定针对工作树字节；修订入库与否由当前权威裁决，本登记不代办。**v1（`mixed-work-overrun-20260913.md`）保留为历史证据，不再逐条修订；修订版 v2 为当前限度的权威表述。**

## 2. 已复核结论保全（2026-09-14 现场逐项核对）

1. **启动件 env 语义（修正后的表述成立）**：`validation/33-formal-promotion/current-mixed-oxv29042/launch.sh` 第 4 行为**显式 unset 控制**，整行核得 `unset CMAKE_PREFIX_PATH AMENT_PREFIX_PATH COLCON_PREFIX_PATH LD_LIBRARY_PATH PYTHONPATH ROS_PACKAGE_PATH ROS_DISTRO PKG_CONFIG_PATH WKSIM_JOINT_CPU_TIMING WKSIM_JOINT_RATE_TIMING_PROBE`——该行确实包含 `WKSIM_JOINT_CPU_TIMING` 与 `WKSIM_JOINT_RATE_TIMING_PROBE` 字样，但语义是清除而非设置（无 `=` 赋值）；同目录 `launch.json` 与 `children-start.json`（本 checkout 已跟踪副本）对该串匹配数为 0；`pre-run-identity.json` 第 28 行记 `"WKSIM_JOINT_CPU_TIMING": null`。flag 在该场为 off/unset 的结论保持成立：显式 unset 控制 + 身份记录 null + 启动件无设置路径。
2. **raw wire 与 go/admission 为外部限度**：raw `joint-wire.jsonl`（SHA `20d0634e…`，495,410 行）仅存于 Linux 接受根、未随场入库，本 checkout 无法重算其 SHA、行数或重跑 kind 普查；计数固化于已跟踪的 `validation/coordination/mixed-work-overrun-20260913/mixed-work-overrun-v2.json`（`diagnostic_cpu_timing` 段三种 kind 计数均为 0，`rows_in_overrun_windows` 为空，7 组 ±邻域 tick 窗口每组 17 tick 共 119 tick 均无记录）。oxv29042 场目录在本 checkout 中不含 `go.json` 与 `experimental-admission.json`（HEAD 树与工作树均确认缺席），其内容只能在接受根（外部）核对，**无法本地复验**。本绑定与配套测试**无 PASS 依赖任何仅外部（untracked-only）原件**。
3. **v1 历史性 / 脚本 SHA 演进 / runner 漂移**：v1 所引脚本 SHA `e5a0db2b…d81595fe` **不在 Git 中**（从未提交）：`validation/coordination/mixed-work-overrun-20260913/analyze_mixed_work_overrun.py` 全历史只有一个已提交版本（提交 `596cb5e6`），其内容 SHA 为 `1162d9fbcaa581fe795dadd2a33427c6f03b69c81aa67111b8b98eda4e691972`，与 v2 JSON 的 `script_sha256` 一致；v1 的复跑命令按旧 SHA 描述已过时，复跑以 v2 的脚本与 SHA 为准。现场 runner 漂移：本 checkout 的 `tools/run_joint_flight.py`（现算 `c8577093a62e4993c8048a69f4501984b3ee9045b8a73d26fb83aedc73acbb3b` / 79221 bytes）相对冻结快照（`65c7a86765a99d2173a62ffafaf56c43243674dd1e3cbbc1150147b4c56d8161`，已跟踪于 oxv29042 场目录）已有演进（GNU diff 计 377 个变更行，新增 perf-capture 装载等）；wire `record()` 位于快照第 829–831 行与 v1 一致，但现场运行的 runner 与快照不再逐字节相同。joint.py 快照 SHA `f5433c2ec7e81794ffcfab26dce0feff18d4e1affdfb44f895a72e4ce0241d50` 与 HEAD 树 `Simulator/wksim_core/joint.py` 逐字节一致，第 54 行门控点 `self.cpu_timing = os.environ.get('WKSIM_JOINT_CPU_TIMING') == '1'` 可本地复核。
4. **数值观察仅为历史诊断证据**：v1/v2 的全部数值观察（含 `main-rate-analysis.json` 的区间算术与 33-rate 数字）保留为**历史诊断证据**，不是当前执行、不是验收、不是晋升。v2 JSON 自身载明 `full_run_acceptance=false`、`performance_pass=false`、`native_executed=false`，原样保全。**不关闭 G6、不关闭 Full、不收口 #84、不触发 #83 重跑、不做验收晋升**；本结果不算全场通过。
5. **诊断门控语境保全**：既有已跟踪门控词汇原样保全——1ms tick（1 ms tick）、native barrier（native barrier 调度）、4-tick grouping（4-tick group / `tick_alignment_control.true_P+1..P+4=true`，错误对齐被拒绝）、no catch-up（不追帧）、100ms（lateness 上限 ≤100 ms）、full-window（complete windows 全窗）、physics（真实 MATLAB→Console→WSL PX4 FC/physics 链路）、identity gates（身份门：epoch/manifest/source_unchanged 等身份核验）。已跟踪锚：`validation/coordination/ds-g0-g5-frontier-20260913-01/audit.json` 含原句 "1 ms tick, 4-tick group, no catch-up, <=100 ms lateness, complete windows, source_unchanged"；oxv29042 场自身记录 `period_ns=8000000`、`ticks_per_group=4`、`groups_total=32930`。
6. **可复核性边界**：本地复核以已入库件为限（analyzer、v2 JSON、oxv29042 启动件、rate.jsonl.gz、joint.py 等）；raw wire 与 go/admission 两件留在外部。

## 3. 锚复核结果（2026-09-14 于 HEAD `31e5b65f` 现场重算）

| 锚 | 状态 |
| --- | --- |
| `validation/coordination/mixed-work-overrun-20260913/analyze_mixed_work_overrun.py` | tracked；HEAD 树 = 工作树 = `1162d9fb…e691972` / 28503 bytes；全历史唯一提交版本 `596cb5e6` |
| `validation/coordination/mixed-work-overrun-20260913/mixed-work-overrun-v2.json` | tracked；`e10619cc08f4f49cfc8db25b56ab12d48e74672979ee28646b74b119b568c408` / 12062 bytes；`script_sha256` 与上锚一致 |
| `validation/coordination/mixed-work-overrun-20260913/mixed-work-overrun.json`（v1） | tracked；`d0a214e34ffbece76cbb2e1291a7e295beec68da6e3bb948942f145042218272`，原样保留 |
| `validation/coordination/mixed-work-overrun-20260913/main-rate-crosscheck.json` | tracked；`461f6bd328a0f7fe339f360dabb71a41850a5bc7081ce60cc2b20396e009febe` |
| `docs/coordination/mixed-work-overrun-20260913.md`（v1） | tracked；`a0bd3df069419257314f91a519291aa9d8425ee0bc81cc4ef2d233b0086cd3ec` / 4082 bytes；第 15 行含 `e5a0db2b…d81595fe` 缩记 |
| oxv29042 `launch.sh:4` | tracked；显式 unset 行核得（§2.1），含两个 env 名、无赋值 |
| oxv29042 `launch.json` / `children-start.json` | tracked；`WKSIM_JOINT_CPU_TIMING` 匹配数均为 0 |
| oxv29042 `pre-run-identity.json:28` | tracked；`"WKSIM_JOINT_CPU_TIMING": null` |
| oxv29042 `rate.jsonl.gz` | tracked；`8058ecff7f4730d5fd81a50e8817a8a4190230cc2de3b8170496e46e279c99da` / 2138673 bytes，可本地复核 |
| oxv29042 `source__tools__run_joint_flight.py.txt`（冻结快照） | tracked；`65c7a867…c56d8161`；`record()` 在 829–831 行 |
| `tools/run_joint_flight.py`（现场） | `c8577093…acbb3b` / 79221 bytes；对快照 GNU diff 377 变更行（约数） |
| `Simulator/wksim_core/joint.py` | HEAD 树 = `f5433c2e…241d50`；`:54` 门控点成立 |
| `validation/coordination/ds-g0-g5-frontier-20260913-01/audit.json` | tracked；`7206d768cddb16192f837603ac252c5cd2525fe29aa63777bdd59b226f79d94f` / 64330 bytes；含 §2.5 原句 |
| oxv29042 目录缺席项 | `go.json`、`experimental-admission.json`、raw `joint-wire.jsonl`：HEAD 树与工作树均不存在 |

## 4. 不声称清单（显式）

- 未把历史语境升格为当前执行、验收、批准或收口；不做验收晋升；
- 未重跑任何诊断场或正式场；未触发 #83 重跑；未声称 G6/Full/#84 任何进展；
- 未从 raw wire 重derive 任何数值（原件不在本 checkout）；未复算 495,410 行或 kind 普查；
- 未声称 flag-on 不可能性超出该场（oxv29042）范围；
- 未修改被绑定文件或任何既有文件；未触碰受保护文件；未联网；未提交 Git。

## 5. 开放风险（显式，不代办）

1. **修订未入库**：被绑定的修订版 v2 是工作树状态（HEAD 树仍为修订前 `24ad1572…`）；其后任何漂移与本登记无关。
2. **外部件**：raw wire、go.json、experimental-admission.json 留在外部接受根；本地证据链以 v2 JSON 固化结果为限。
3. **漂移计数为约数**：377 为 GNU diff `^[<>]` 行计数；仅表示漂移规模，不作为逐行锚。
4. **受保护文件现状**：`docs/Prometheus.gitmodules.reference` 与 `validation/coordination/short-cycle-dispatches.json` 在本登记时刻为工作树脏文件；本登记未触碰。
