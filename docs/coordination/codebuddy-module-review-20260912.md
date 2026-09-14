# CodeBuddy 模块稳定交付复核（2026-09-12）

只读复核；唯一写入本文件。未运行 native/模型/构建，未扫全仓；仅小型纯数据复算与纯测试。
历史 F1/F2/F4 已闭合，不复述。快照如下（复核时刻 21:42–22:08 JST，文件未被实现者并发改动）。

## 模块 1 · DS-A 审计/复现（快照：probe 51342c48，test dff20f4b / 8f5a142b，auditor e8d33c5d）

**结论：无缺陷；交付真实可核。** 新包 `validation/39-planner-flight/module-delivery-20260912/` 逐项重算一致：

- `probe-report.json`（0feb3e2a…）自报 `probe_tool_sha256=51342c48…` = 仓库 `tools/probe_release_audit_integrity.py` 实测 = `probe.log` 打印值；`producer_distinct_from_auditor=true`。F2b 落实。
- `coverage.complete_matrix_pass=true`，且 `verdict_pass=true`、`missing=[]`、`negatives_not_rejected=[]`、`blocked_or_error=[]`；正例 accepted + 四个 required 负例各按预期 ValueError rejected；`baseline_file_count=319`、`unchanged=true`。F3 落实，子集/可选场景不能抬升该标志（`summarize_coverage` 1066–1114 行：`complete = required_matrix and verdict_pass`）。
- 原件未变：WSL 原件与仓库副本逐字节一致（delivery-manifest 984e1db8…、probe-report 0feb3e2a…、probe.log ac844249…）；`main-verification.json` 绑定 `report_sha256=0feb3e2a…` 与四份源码 SHA。
- F5 落实：`derived` 去重（299–300、937 行），manifest 记 55 listed / 55 unique。
- 独立纯测试复跑（Windows）：`test_release_audit_integrity.py` 49 passed / 2 skipped / 5 subtests，`test_planner_release_audit.py` 8 passed = manifest 的 Windows 总数 57 passed 完全吻合。
- 中性事实：required 矩阵为 1+4，`optional_executed=[]`（未跑 setup_mode_tamper）；不影响 required 断言。

**低危注记（非矩阵缺陷）**：WSL 实验区 `/root/wksim-release-acceptance-fe3/tools/probe_release_audit_integrity.py` 仍是旧版 `92a83f4e…`，而本次矩阵由 `51342c48…` 字节产生。`probe.log` 只记录 SHA、不记录被调用的 probe 绝对路径。矩阵身份由 SHA 保证，无实质问题；但若操作者从 WSL 检出路径复跑，会静默退回无 coverage 语义。建议复跑命令显式使用主仓库副本，或把被调用路径写入日志。

## 模块 2 · DS-B interval/复算/诊断（快照：analyzer c3ba9de8，plan 21:40:22，JSON 21:40:41）

**结论：公式与核算无缺陷；诊断边界有 3 处精确缺陷。**

核验通过：
- 同身份：`_latch_identity` 200–209 行与 `_reconcile` 244–247 行的五元组 `(epoch, segment_id, request_id, requested_rate, transition)` 精确相等，外来 latch 单独列出（`foreign_rate_unmet`），不混算。
- 缺 latch：278–288 行返回 `status="unavailable"` / `no_rate_unmet_for_identity`，且 `recorded_latch_lateness_ns`、`terminal_unreconciled_ns` 为 `null`，不留 0。
- 负残差：302–305 行直接 raise，不 clamp；另有 294–300、310–313 行的边界与形态一致性断言。
- 闭合算术逐场重算全部差 0 ns：zzmg3k47 118903+99881013+92179=100092095；tpwl1k4p 116719+99877507+44659=100038885；nqyqcagl 115025+97921130+6224284=104260439；8fmacpgy 114791+70719737+63993754=134828282。
- 诊断包引用正确的部分：`run_joint_flight.py:1092–1099/1095/1097`、`joint_profile.py:219–220`、`analyze_joint_rate_probe.py:54/56/62`（相位闭合、release_excess、overshoot 断言）均实读无误；`python -B -m unittest ...` 60 tests OK (skipped=2) 独立复现。

**缺陷 D1（错误引用）**：`docs/plan/33-rate-next-diagnostic-20260912.md:5` 称 `tools/audit_pv_trajectory.py:298` 对诊断 flag 记录要求为空。实测该文件全文 **0 处** `rate_timing_probe`/`timing_probe`；298 行检查的是 `pause_probe_requested`、`scene_lifecycle_requested`、`scene_lease_loss_requested`、`dds_loss_requested`、`diagnostic_land_step_period_s`。该引用必须删除或替换。

**缺陷 D2（机制被夸大）**：plan:4 与 `docs/coordination/ds-rate-budget-20260912.json`（`parser_coverage`）称 `tools/audit_joint_rate.py:32–36` 对 probe 记录 fail-closed。实测 32–42 行仅对**缺失/不符的身份块** fail-closed；带密封身份的 `rate_timing_probe` 行通过校验后，在 `schedule()` 46–114 行的 kind 分派中**无 else 分支、被静默忽略**；121/188 行对 result.json 也只校验身份块。真正阻断正式验收的是 `Simulator/wksim_runtime/joint_profile.py:219–220`（`if 'rate_timing_probe' in flight: raise`）。结论“诊断场不能当 #83 通过证据”仍成立（mixed/PV 路径），但引用与机制描述应改为指向 joint_profile.py。

**缺陷 D3（env 语义不实）**：plan:89 称两环境变量“只允许 1（其他值 raise）”。实测 `joint_rate_probe.py:23–30`：unset/"0" 为关闭、`"1"` 为开启、其余 raise；而 `Simulator/wksim_core/joint.py:54` 的 CPU-timing 门是 `os.environ.get('WKSIM_JOINT_CPU_TIMING') == '1'`，任何非 `"1"` 值**静默关闭、不会 raise**。两门语义不同，且 plan 把文件写作 `joint.py`（实为 `Simulator/wksim_core/joint.py`）。失败分诊时会误导。

## 模块 3 · DS-D #26 就绪包（快照：plan 6483e82d，test 317b7c06，JSON 21:41:18）

**结论：历史有效与当前 wrapper 可复现的分离正确、无虚构批准；2 处精确事实缺陷。**

分离与边界核验通过：
- `docs/coordination/ds-26-host-recheck-20260912.json` finding_1/finding_2 明确“不说既有 .so 证据失效；只说 pin 住的 wrapper 与当前 checkout 不同源”；`must_provide_evidence.current_source_matches=false`；缺口 A 标注真实阻塞且 owner=主会话，执行前要求书面确认冻结入口；plan §7 八条禁止外推含“重核通过⇒#26 可关闭”“⇒G6/R1”；§6.2 把新 `.so` 哈希标为未知且必须不同于 7da68532…，未编造具体值。
- 报告内的身份逐项重算一致：wrapper `150ddf3b…`/4070 bytes、弃用 pin `3f325678…`/1864、driver `0f6c7a8c…`（commit 50897b8，工作树干净）、checker `67fdeb30…`（`main()` 仅有 `--manifest/--output`，991–992 行）、lifecycle 校验器 `original_summary` 取自 manifest 同目录 summary.json（57 行）、断言在 81 行、plan §2.1/§4.4 与之一致；纯测试 `35 passed, 1 skipped` 独立复现。

**缺陷 D4（HEAD 引用过期）**：`docs/plan/26-current-wrapper-recheck-plan.md:3` 记 HEAD `7126d4d7…`。该文件 mtime 21:39:46，当时主仓库实际 HEAD 已是 `e52c7bb`（21:28:57）；复核时为 `319de4f2`（21:40:05）。已核对 `7126d4d..HEAD` 的 diff 不触及 `model.cpp`、`build_generated_e0.py`、`validate_generated_e0_lifecycle.py`、`audit_26_closure_readiness.py`，故计划前提不受影响；但头部 provenance 应改为执行时重新钉住（§4.1 已有再核对步骤，建议执行时以实际输出回填）。

**缺陷 D5（行数不实）**：同 plan §2 表格与 `docs/coordination/ds-26-host-recheck-20260912.json`（`plan_package.key_discovery.why_it_matters`）称 `validation/test_build_generated_e0.py` 为“782 行”。实测 HEAD 与工作树均为 **886 行**（文件干净）。不影响“驱动有充分测试”的结论。

## 约束遵守

只读（除本文件）；无 native/ROS/模型/构建/新物理场次；未提交 Git、未改 Issue、未动实现者文件；DS-A/DS-B/DS-D 报告中的 SHA 快照均先于复核固定并经重算。历史 F1/F2/F4 未复述。
