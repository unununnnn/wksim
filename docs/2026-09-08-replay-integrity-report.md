# 离线回看输入完整性修复（2026-09-08）

范围仅为已有实验的离线 JSON 读取与导出；不代表 Full 功能完成，不构成重新仿真或飞行验收。

## 已复现与修复

`python -B -m unittest validation.test_wksim_replay -v` 在修复前新增三项均失败：`1e999` 被解析为 `inf`；重复 `run_id` 被最后一个值覆盖；逐行显式身份 B/C 被结果文件身份 A 覆盖。原有两项通过。

结果文件与 JSONL 现在使用同一解析函数。NaN、Infinity、-Infinity 及浮点溢出数词保留为 `{"nonfinite": "原数词"}`，附 `nonfinite_values` 诊断，严格 JSON 导出成功。复用现有 `_unique_object` 拒绝任意层重复键：结果报告 `invalid_result`，逐行报告 `malformed_record`，回看状态为 `partial`。输入文件与原始行文本、SHA-256 均不改写。

显式行或其直接 message 对象中的 `run_id`、`epoch` 优先于结果元数据；与结果冲突时保留原身份并报告 `identity_mismatch` / `partial`。行与 message 自身冲突的字段投影为 null，原始载荷保留。缺少逐行身份时仍使用结果元数据，保持历史兼容；不把 `control_epoch` 推断成 `epoch`，也不解析字符串内事件身份来建立新的归属语义。

额外验证了 `10**400` 整数真值时间及 header 秒字段：修复前均触发 OverflowError；finite 检查现在拒绝无法转为有限浮点数的整数，源时钟保持 unknown，原始大整数载荷完整保留。

主代理复核还实证有限的 sec/nanosec 在合成秒数时可溢出为 inf；同一回归加入此样本，合成结果再次校验有限性，异常仍保持 unknown，避免严格导出失败。

## 验证

修复后同一命令 6 项全部通过，包含非有限导出、重复键拒绝、身份归属及原有行序/时域和受理/完成区别检查。

真实只读样本：`validation/arducopter-dds-urq9hofr`，结果记录为 2026-09-05 的 pass。调用离线 main 时把 socket.socket 和 subprocess.Popen 替换为抛异常的守卫；导出成功，无网络或进程创建。读取前后该目录全部 10 个文件 SHA-256 一致，20,144 条导出 raw_json 的哈希逐条符合 raw_sha256。

- prometheus：5,378；dds：5,835；truth：3,944；telemetry：4,987。
- reader_status：parsed；历史缺失 run_id/epoch 仍为 null。
- 诊断：3,270 条 nonfinite_values、1 条 unknown_run_identity。
- 外部导出：`C:/Users/PC/AppData/Local/Temp/wksim-replay-integrity-20260908-ikzm7j8_/ap-replay.json`（临时目录，后续清理可能移除）。
- 导出 SHA-256：`0fe97bf363c36e45fb35dc5a5f1ffe03ed863f20b9cb95de065a1357c9a3e7ab`。
- 主代理按上述哈希归档到 `validation/pv-replay-followup-20260908/ap-replay.json`，再次逐行比对原始流；证明为同目录 `replay-archive-verification.json`，不依赖临时目录长期存在。
- 原 result.json SHA-256：`49708ddf16724b1fcbc6caaea74f668df0ebc813c356f6e9390b3c280f08fa06`。

未启动 SITL、UE、MATLAB；未修改控制、pins、原始实验记录，未更新 GitHub 或提交。当前切片仍受已有单文件 64 MiB 和内存读取边界限制。
