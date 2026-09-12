# OMP C1 入口行为测试包（2026-09-12）

交付：`validation/test_gc_candidate_entry.py`（实验区，新文件，10/10 通过）。
方法：**真实导入** `tools/run_joint_flight.py` 并驱动其真实 `main(argv)`
argparse+门禁路径，仅 mock 掉 native 执行入口 `run`/`task_main`；不跑 shell、
不起 ROS、不加载模型、不构建。A 正在修 GC 模块；本包不改其文件、不等它。

## 行为验证结论（实际 parser/函数执行）

| 行为 | 依据 | 结果 |
|---|---|---|
| GC flag 无选项默认 | 缺省时 `args.manager_gc_freeze is False`，retest/原诊断 argv 照常解析 | ✅ 实测 |
| PV/MIXED 允许 | `--manager-gc-freeze` + 两 profile 全配对 → 进 run() | ✅ 实测 |
| 其他 profile 拒绝 | position + GC flag → `parser.error` SystemExit(2)，run() 未被调（:1186-1187 硬门） | ✅ 实测 |
| 默认 namespace 兼容 | 无 GC flag 的旧 argv 解析后 namespace 仅多该 False 字段 | ✅ 实测 |
| 原诊断 argv 可解析 | S1 模板 argv（PV+mixed+c2IXOr+Rzj3Pf）解析进 run() | ✅ 实测 |
| 两 timing env 是环境门非 argv | `timing_probe_enabled()` 实函数执行：unset/0→False、1→True、"2"→ValueError；`WKSIM_JOINT_CPU_TIMING` 字面 `'1'` 由 joint.py:54 文本钉 | ✅ 实测 |
| shell 转发合同 | `run-joint-flight.sh` 含 `exec python3 -B "$repo/tools/run_joint_flight.py" run "$@"` + unshare 隔离 + `ROS_DOMAIN_ID=77`（文本合同，**脚本未执行**） | ✅ 文本级 |

## 7bdfxkb 复测 argv（无占位符，证据钉死）

`validation/joint-public-flight-7bdfxkb_/result.json`：profile=PV、
`async_model_evidence_requested=true`、`rate_timing_probe` 诊断身份在档；
留存 `ap-build.json`/`control-build.json`/`message-build.json` 哈希前缀
`1e6250ef`/`6fe8c0b3`/`29969da0` 与三身份逐字吻合；model worker argv 含
`--async-evidence`（children-start.json）。据此生成复测 argv（测试
`RetestArgvTests`）：`--task-profile full_xyz_pv_yaw_v1` + AP mixed 对 +
c2IXOr 对 + Rzj3Pf 对 + `--async-model-evidence`；**无** --planner-release-proof、
无 AP-PV 对、无 PX4 override（PV 门自身拒 PX4 override，:1192）。两 timing env
以环境给出：`WKSIM_JOINT_CPU_TIMING=1 WKSIM_JOINT_RATE_TIMING_PROBE=1`。

## 措辞修正（供文档所有者）

此前"audit_joint_rate/audit_pv 拒绝所有 probe"不准确：
- `audit_joint_rate.py:32-36` 拒的是 rate 证据中的 probe **记录行**；
- `audit_pv_trajectory.py:298` 拒的是 alternate-workflow **标志位**；
- **正式能力证据的硬门在 `joint_profile.py:219-220`**（profile evidence 飞行
  含 `rate_timing_probe` 即 raise，两工作区该段逐字节一致）。

## Mock 限度（明确声明）

- 验证到 `main()` 的门禁为止；`run()` 内部（preflight、admission、
  ManagerGCFreeze.arm/restore、native 子进程）全部 mock，**未验证**。
- shell 脚本只读文本合同，未执行。
- A 的实现变动不在本包验证范围；发现缺陷记录于下文供 A 读取。

## 实测 SHA（2026-09-12 实读）

- `tools/manager_gc_candidate.py`：`cbf7b0186131c08d4055aea1fcafdb8e7cca36d9acfcb19cdac87938d8786e66`
- `tools/run_joint_flight.py`：`fd0b7ee6dfb99be7a2d6f580555c6f9bfcddf721e25f68e97761d7f5670df246`

A 若改源码，以新实测 SHA 复核本包（测试不钉这两个文件的哈希，避免误锁）。

## 缺陷记录（供 A）

本轮未发现 GC 入口缺陷。已知非缺陷事实：retest argv 中 GC flag 与
async-model-evidence 同场时两诊断叠加的行为（arm/restore 与 reset_on_fork
交互）未实跑，属 run() 内部，超出本包 mock 边界。
