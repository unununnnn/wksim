# #68 `25-px4-existing-audit` PX4-03 既有记录复审摘要

## 票据与边界

- GitHub：#68 `[Luna] 审计本轮 Hex PX4-03 既有记录（不重飞）`
- 稳定键：`25-px4-existing-audit`
- 前置 #65 已关闭；本票只审计既有 `/root/wksim-hex-flight-px4-03/hex-px4-03`，不启动新的 FC、模型、UE 或 ROS 飞行。
- 执行分支：`codex/independent-rgb-integration`
- 执行前 HEAD：`b54ba0f feat: prove AP authoritative-tick native GNSS candidate (#109)`

## 准确命令

两次命令只更换新输出文件：

```text
bash validation/lunar-65-astra-20260909-01/run-audit.sh tools/audit_hex_flight.py --run-dir /root/wksim-hex-flight-px4-03/hex-px4-03 --output validation/lunar-25-px4-existing/px4-03-audit-01.json
bash validation/lunar-65-astra-20260909-01/run-audit.sh tools/audit_hex_flight.py --run-dir /root/wksim-hex-flight-px4-03/hex-px4-03 --output validation/lunar-25-px4-existing/px4-03-audit-02.json
```

实际两次均返回退出码 `0`，输出均为 `status=passed`、`passed=true`、`errors=[]`。两次输出文件 SHA256 均为：

`3bc1731769d49ea92c744180984fa39c0df1f459cea67b387e864a12dcf5d33d`

逐字节一致，证明重复审计没有依赖随机窗口或修改原件。

## 实际核验范围

- `audit_hex_flight.py` 输出 schema：`wksim.hex.flight.audit.v1`。
- 读取并验证既有真实 PX4-03 的 Hex 模型/配置/源身份、77 项参数、六通道物理输入、CDR/MAVLink 原始记录、公共请求、驻留和落地窗口、进程身份与清理证据。
- 前置 #65 的最终审计已证明 38,644 条物理记录、30,924 个连续 1ms step、7,731 组、7,717 个 actuator packet，hold/waypoint/ground/landing 窗口无物理违规；本票以两份新审计输出复核同一结论。
- 原始输入哈希：`result.json` `ab9aeff2e222bb7105a8dfe9a6e25420eb1768ec062eaaf3deba40b8eba3b3ff`；`physics-1ms.jsonl` `2d93088f3d11945fc582d90f49310e867894f5f52216328ccd3f347afe85d5de`；`hex-native.jsonl` `eda5232731fc6adb15f06afe06ecf697c3ff49806952a089385ef03e2a500cb3`。

## 证据与清理

- 票据专用目录：`validation/lunar-25-px4-existing/`
- 活动目录：`validation/lunar-68-4dbbf9c11b584652858dfe0541ca9921/`
- 两次命令、stdout、审计 JSON、Issue 快照和哈希均已保存；原始 PX4-03 运行文件未改写。
- 审计工具在离线读取路径运行；WSL 审计后没有新增 FC/model/UE 进程，未执行全局清理或信号操作。

## 完成判定与未覆盖范围

本票完成条件满足：既有 PX4-03 原始记录的两次审计均 PASS 且字节一致，无新增飞行进程。可以评论并关闭 #68。

本票不证明 AP Hex 飞行、Hex cold reset、实时 UE 显示、实机标定、R1/G6 或父票 #25 完成；这些仍由 #66/#67/#69 及父票范围分别处理。#66 因缺少准确 live UE bridge 前置已保持 `needs-triage`。
