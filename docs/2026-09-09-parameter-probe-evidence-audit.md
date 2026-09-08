# 2026-09-09 参数 probe 历史证据审计

本次仅归档并独立重算 2026-09-08 已有运行，没有启动 SITL、写参数、重启飞控或修改产品源码。审计脚本为 `validation/audit_parameter_probe_20260909.py`；原始 JSON/JSONL、源路径、字节数及 SHA256 保存在 `validation/parameter-probe-audit-20260909/manifest.json`，断言结果见同目录 `audit.json`。复制仅接受普通文件，不跟随符号链接。

| 运行 | 原生参数结果 | 完整运行 | 完整物理日志最大高度 / 最小航点误差 / 最终高度（m） |
| --- | --- | --- | --- |
| read-arducopter-01 | 地面 freshness 拒绝，未读 | failed | 0 / 4.6904 / 0 |
| read-arducopter-02 | WP_SPD = 10 | failed | 2.9932 / 0.0169 / 2.9839 |
| read-arducopter-03 | WP_SPD = 10 | pass | 2.9930 / 0.0158 / -0.000026 |
| read-px4-01 | MPC_XY_CRUISE = 5 | pass | 3.1710 / 0.0236 / -0.000002 |
| write-arducopter-01 | 10 → 4 → 10，独立回读一致 | pass | 2.9901 / 0.0148 / -0.000035 |
| write-px4-01 | 5 → 4 → 5，独立回读一致 | pass | 3.1353 / 0.0541 / -0.000004 |

表中缩写均对应归档 `runs/parameter-{read,write}-{stack}-20260908-NN`。首轮 AP 来源为项目内旧归档，其余来源为原始 `/root/wksim-parameter-*` 目录。

可复跑断言已通过：全部请求/响应原始字节长度与 SHA256；请求先于响应且下一请求晚于上一响应；读值与原生响应一致；写轮严格按 GET、SET、独立 GET、恢复 SET、独立 GET 顺序完成，两次写尝试、零重试、`pending_restore=false`。PX4 响应 peer 127.0.0.1:18591、system 22/component 1、参数名与 REAL32 类型一致；AP 固定服务符合记录。每条 ground authority 的 run/epoch/generation/context 一致，disarmed、位置有效、物理高度绝对值 <0.3m、采样年龄 ≤2s，并与 truth 日志对应前缀核对。四轮完整通过记录的汇总前缀重算一致，完整日志也满足起飞、航点、落地门槛；最终公开状态 disarmed、safe_landing、landed_stop 均成立。写轮客户端关闭先于标准 Task 完成。物理日志含运行器汇总后的收尾记录，因此完整日志 records/final_time 可以大于 result.truth，不能要求两者逐字相同。

AP read-02 的 command_id 1 时间为 1788874456.099722851，command_id 2 为 1788874455.843517302，实际倒退 256205549ns；公开日志包含 `out_of_order_command_stamp`。本次保留失败及未落地的物理记录，没有做时间戳 clamp，也没有把读成功升级为整轮通过。

六轮都记录 children_reaped=true、cleanup_errors=[]、所有子进程 returncode 已知。本次只读 `/proc` 检查未发现同时匹配历史完整 argv 与记录 net namespace 的进程；未使用全局 PID/端口占用判断，更未杀进程。历史记录没有进程 start-time，namespace inode 也可能复用，因此该检查不等于可追溯的历史 start-time 身份证明，不能据新 maintenance 进程判断旧运行泄漏。

源码归属：六轮 runtime 记录哈希 `615f6ab01604bb9141a460b38cab0a6d81b3dda891c01c4460c9d97b3a34b888` 与 `runtime-before-storage.py` 原存档一致，已复制保留。`git show 1fdf273:Simulator/wksim_runtime/parameter_protocol.py` 实际字节 SHA256 为 `733f9d1a32d56e4d48ef320d200d1c3b21da1407de4bb3ff60df2d8fbc5225ea`，与 read-phase 记录一致，已另存；write-phase 协议记录为 `b8cf9e91db44c64d64d9e3145c1b35f7a5769fe1a90e665c1008cdc17b96cfcc`。当前 runtime/protocol 哈希单列为审计时快照，不冒充历史运行源码。

AP CDR 是真实对象序列化证据，不是网络抓包；此审计核对记录及原始字节哈希，未重新调用原生服务。PX4 PARAM_VALUE 无 request_id，证明本 context 内观察到存储值，不证明强请求因果关联。全部 restart_operations 为空：这些运行没有测试真实飞控重启、重启持久性或介质落盘；本报告不宣称关闭 #43。

复跑：在 WSL Ubuntu-22.04 root 运行 `python3 /mnt/c/Users/PC/Documents/odid编译/wksim/validation/audit_parameter_probe_20260909.py`。仅访问历史文件、git 对象与 `/proc`，归档文件若已存在且字节不同立即拒绝。
