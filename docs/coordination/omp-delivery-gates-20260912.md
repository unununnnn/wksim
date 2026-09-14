# OMP 交付包可执行性门（2026-09-12）

核对对象：DS-A 审计完整包（`tools/audit_pv_trajectory.py`）、DS-B #83 诊断包
（`tools/run-joint-flight.sh` + `tools/run_joint_flight.py` + 候选清单）、
DS-D #26 重核（`tools/audit_26_closure_readiness.py`）。全部对照真实 parser/函数
接口；自动拒绝测试：`validation/test_delivery_entry_contract.py`（9 项，
Windows/WSL 双平台通过）。未运行 native/模型/ROS/构建；未改模块负责人源文件。

## DS-B #83 诊断包：可执行（限实验区）

- 全部模板 flag 存在于两工作区真实 parser（契约测试 `test_run_joint_flight_flags`；
  manifest/SHA 对经 `'--'+name` 循环构造，文本核验 `:1067/:1069` 主、`:1129/:1131` 实验区）。
- **配对完整性有真实强制**：`ap_mixed_candidate.admit()` 含
  `'Message candidate path/SHA pair is incomplete'`（:108-109）与
  `'requires the exact final manifests'`（:114-116）硬拒；`joint_control_candidate.check()`
  /`joint_message_candidate.check()` 对 SHA 做 `[0-9a-f]{64}` fullmatch + 字节比对
  （:145-149 / :106-110）。
- **执行工作区 pin 与已核身份一致**（实验区 `ap_mixed_candidate.py:22-24`：
  FINAL_AP=`1e6250ef…`、FINAL_CONTROL=`6fe8c0b3…`=c2IXOr、FINAL_MESSAGE=`29969da0…`=Rzj3Pf；
  契约测试逐字校验）。**主工作区 FINAL_CONTROL_SHA 为 `3d04d53a…`（不是 c2IXOr）——
  该诊断包只能在实验区 `/root/wksim-release-acceptance-fe3` 执行**，主工作区会以
  "exact final manifests" 拒绝。这是有意分流，不是缺陷。
- 壳入口 `run-joint-flight.sh` 仍 source 历史 MUlZd0/FVMjak overlay；候选环境
  PREPEND 覆盖（`joint_control_candidate.py:157-162`、`joint_message_candidate.py:118-127`），
  且 `activate_candidate_imports` 对解析原点 fail-closed（run_joint_flight.py:76-96）。
  可执行，但壳内历史 overlay 是**需要主会话知情的包装层事实**（本切片不改 runner）。

## DS-A 审计完整包：可执行，一处真实缺口

- CLI：`directory` 位置参数 + `--output` + `--task-profile`（audit_pv_trajectory.py:863-866），
  契约测试核验。
- **缺口（不掩饰）**：`--output` 用 `write_text` 直接覆盖（:877）——重跑可覆写历史审计
  产物。同样形态见于 `audit_26_closure_readiness.py:997` 与实验区
  `audit_planner_release.py:355`。**主会话验收前应要求输出到全新路径**；归模块负责人改，
  本切片不动。契约测试不为该行为写重钉测试（只报告）。

## DS-D #26 重核：可执行

- CLI：`--manifest`（默认 `docs/plan/26-closure-readiness-manifest.json`，文件存在，
  契约测试核验）+ `--output`（audit_26_closure_readiness.py:990-992）。
- 同样的 `--output` 覆盖缺口适用（:997）。

## 诊断专用再确认（契约测试 `DiagnosticOnlyGateTests`）

- `WKSIM_JOINT_CPU_TIMING` 字面 `'1'` 读取（joint.py:54）+ 验收候选硬拒
  （check-delivery.py:34）均在。
- `WKSIM_JOINT_RATE_TIMING_PROBE` 字面、diagnostic_only 分类、PV/MIXED 门、
  audit fail-closed 均在。
- `--async-model-evidence` 的 PV/MIXED 硬门与 result 字段均在。

## 主会话可验收的最小列表

1. DS-B 诊断包在实验区按 c2IXOr/Rzj3Pf/fhuf05l9 身份可执行（pin 逐字一致，
   契约测试绿）；壳 overlay 历史层事实知情即可。
2. DS-A/DS-D 审计入口参数齐备可执行；**验收前提**：`--output` 指向全新路径
   （覆盖缺口未修，归模块负责人）。
3. 三个诊断开关保持诊断专用（契约测试绿）。
4. 运行前复核三清单 SHA（今日实读快照见 omp-83-freeze-check-20260912.md）。

## 未证/边界

- 运行期 admission（preflight/admit 全链）未实跑；契约测试是静态层。
- 主工作区与实验区 runner 漂移（69 行，planner-release-proof 机制）未逐项审。
- 契约测试为纯文件/AST 层；不证明运行行为。
