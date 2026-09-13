# #52 `25-physics-core` Hex 逐毫秒物理证据检查摘要

## 票据与边界

- GitHub：#52 `[Luna] 实现 Hex 逐毫秒输入/时钟检查器（两文件）`
- 稳定键：`25-physics-core`
- 绑定时状态：`OPEN`，标签含 `ready-for-agent`。
- 执行分支：`codex/independent-rgb-integration`
- 执行前 HEAD：`4e1be48 evidence: complete AP PID preflight slice`
- 仅新增 `tools/hex_physics_evidence.py` 与 `validation/test_hex_physics_evidence.py`；未改运行器、模型、飞控或原始记录。

## 实现内容

`tools/hex_physics_evidence.py` 提供只读 `check(root, ...)` 和 CLI：

- 验证唯一 `start`、`initialized(initial_tick=0)`、连续 step 和唯一 terminal。
- 绑定并可核对 `run_id`、`model_identity`、模型库/配置/源身份。
- 验证 120 输出有限、`output120[2] == tick * 0.001`、16 输入、6..15 通道为零、六路 RPM 字段、连续 tick、group/substep 完整及组内输入不变。
- 通过现有 `hex_physics.decode_servos` 与 `hex_physics.actuator_commands` 从真实 `packet_hex` 重算 `input16`；检查最新 held packet，统计重复 actuator packet 与实际 step 推进。
- `--output` 只能写入原始 run 目录之外的新文件，不会修改原始 `physics-1ms.jsonl`。

## 正例：真实 PX4-03

原始输入目录：`/root/wksim-hex-flight-px4-03/hex-px4-03`

- `physics-1ms.jsonl` SHA256：`2d93088f3d11945fc582d90f49310e867894f5f52216328ccd3f347afe85d5de`
- model identity：`sha256:d703da7f888e7110e402aa32ff911cabcb24e0b01afb8bbf4c9ec1ccb897276a`
- model library SHA256：`b10ef333129b44ce41d2d8d944a1e3d1161db9201bb1aea9eca88e726a5a7c9c`
- Hex flight config SHA256：`33748c4374d5f297ae928d1682bc9ef00dde95030249fe5c7ff0dce21363ddcc`
- 实际记录：`38644` 行；`start=1`、`initialized=1`、`actuator=7717`、`step=30924`、`end=1`、`groups=7731`。
- `distinct_actuator_packets=7717`、`repeated_actuator_packets=0`、允许的初始 `held_packet=None` step 为 `56`。
- terminal 为 `interrupted_or_failed / Owned Hex physics process retired`，这是父运行器在正常停止时回收物理进程留下的预期终止记录；检查器将其作为 terminal 接受，不把它报告为完整飞行 PASS。

精确审计命令：

```text
cd '/mnt/c/Users/PC/Documents/odid编译/wksim' && python3 tools/hex_physics_evidence.py --root '/root/wksim-hex-flight-px4-03/hex-px4-03' --output '/mnt/c/Users/PC/Documents/odid编译/wksim/validation/lunar-52-28a845d4b3364827ac78c59c05b9dee3/hex-physics-audit-final.json' --run-id 'hex-px4-03' --model-identity 'sha256:d703da7f888e7110e402aa32ff911cabcb24e0b01afb8bbf4c9ec1ccb897276a'
```

结果：退出码 `0`，`status=passed`，`passed=true`，错误数 `0`。审计输出写在原始 run 之外：`validation/lunar-52-28a845d4b3364827ac78c59c05b9dee3/hex-physics-audit-final.json`，文件 SHA256 `afe2851a2eee8542a7825c6b0e837f0a79425ab65ae59d9f73090493cb22bfbe`。

## 测试与负例

命令：

```text
python -m unittest validation.test_hex_physics_evidence -v
```

结果：`4` 项通过、`0` 失败、`0` 错误。覆盖：

- PX4 正例、外部输出文件契约；
- ArduCopter 解码语义；
- 删除 tick、修改输入、修改 run 绑定、删除 terminal，均被拒绝；
- 输出路径位于原始 run 内时被拒绝。

新增源码 SHA256：

- `tools/hex_physics_evidence.py`：`a02fd1658ffa8af1b8d64e72dc8c70d9c5458092c87fc67668e21453a6a40d8d`
- `validation/test_hex_physics_evidence.py`：`d90fc601f769770ed7fdb08929e613b41c04d2e96fa54c1af1ed8366ec92886e`

## 证据与完成判定

活动目录：`validation/lunar-52-28a845d4b3364827ac78c59c05b9dee3`

其中保留 `selection.json`、命令、CLI stdout、CLI 结果、初版和最终 audit JSON。票据专用输出在 `validation/lunar-52-28a845d4b3364827ac78c59c05b9dee3/` 中；真实 PX4-03 原始文件保持只读不变。

本票完成条件满足：两个文件完成，真实 PX4-03 正例通过，删除 tick/改输入/换绑定/缺 terminal 等负例拒绝，输出契约和实际身份可复查。可以评论并关闭 #52。

本票只证明物理记录基础检查；不证明 Hex 整场飞行 PASS、飞行性能、UE 显示、AP/PX4 cold reset 或父票 #25 关闭。
