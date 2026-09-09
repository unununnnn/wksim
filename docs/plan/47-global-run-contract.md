# #118 全球航点原生接入运行合同（待实现）

2026-09-09。前置 #116/#117 已关闭；审阅基线 fd4d45d。状态为 blocked_scope，不能据本文派发真实飞行或关闭 #118。

## 范围冲突与源码事实

#118 当前写入范围仅本文件与 validation/47-global-flight/。#116 的文件预约明确不扩大该范围。用户要求仅写允许文件，因此本次没有修改控制源码。

实际代码位于 ros2/src/prometheus_control/prometheus_control/：

- native_px4.py：supports 明确返回 px4_global_command_adapter_not_implemented；订阅缺 HomePosition/VehicleGlobalPosition；send 仅支持 local/attitude。SensorGps 不能作为融合全球位置，ref_alt 不能作为 home。
- native_arducopter.py：send(global) 发布 GlobalPosition，FRAME_GLOBAL_REL_ALT、map、0x9F8，保留 ENU yaw；现有经纬范围和高度检查未实施 #116 的 home/origin 双水平 100m fence。receive 检测 home tuple/reset 变化，不能识别同值 home 重设。
- command.py/shaping.py：全球目标是 latitude/longitude/home-relative altitude 三元组，没有 ResolvedTarget 身份与验证 checkpoint。
- node.py：on_command 先 supports 再 accept；drive 在现有导航/模式/reset 门控后 send。尚未调用 #117 resolve/validate_current。
- session.py：已有 run/epoch/request 去重；它不等价于全球 home/origin/native publisher 身份绑定。
- Simulator/wksim_runtime/config.py：严格白名单没有 global-home-v1 配置。

## 下一次实现的具体文件预约

主任务需先将以下文件写入 #118 写入范围并核对并行所有权，然后才进行实现：

1. ros2/src/prometheus_control/prometheus_control/native_px4.py：版本匹配 home/global 订阅、有效位与新鲜度、独立 home/origin generations、原生投影发送。
2. 同目录 native_arducopter.py：绑定 WksimState home 和会话，逐次校验；保留全球原生路径，拒绝要求检测同值重设的 profile。
3. 同目录 node.py：受理 resolve，发布 validate_current 并保存返回 checkpoint；pause/reset/epoch/GID/时钟异常立即丢弃旧目标，恢复后等待新观测与新命令。
4. 同目录 command.py、shaping.py：保留全球原输入与已解析身份，不将 global 静默转换为普通 local 意图。
5. 同目录 session.py：复用现有 request 去重和 epoch，为全球命令关联明确身份。
6. Simulator/wksim_runtime/config.py：显式 profile、可追溯 datum proof 与场景 origin；拒绝不支持的 datum/能力。
7. validation/test_global_native.py、tools/run-global-flight.sh、tools/audit_global_flight.py：真实消息边界回归、隔离运行、原始独立审计。

以上源路径来自 #116，尚未取得本票写入范围。安装/配置传播若需其他文件，必须先明确其实际路径与所有权；不能假定仅改 config 就会传播到安装节点。不在证据目录放置替代生产适配器。

## 保留的合同

复用 Simulator/wksim_control/global_reference.py 的 resolve/validate_current。公共 ENU/SI 与 yaw 保持原义；PX4 NED=(N,E,-U)，采用独立 EKF origin 的冻结投影；AP 保留经纬度原生目标与相对 home 高度。显式 amsl 或 home_relative；ellipsoid/AGL/terrain/未知 datum 拒绝。datum_proof_id 必须对应真实归档证据。

每次受理与发布检查 2s 单调时钟 freshness/TTL；重复源时间不续租、回退失效。绑定 run/instance/vehicle/epoch/native session/GID/scene origin/home generation/origin generation/reset counters。home 有效位、数值、PX4 update_count 变化撤销目标；AP 同值重设能力明确拒绝。暂停不冻结全球租期。

冻结 |latitude|<=85、经度 [-180,180]、home 与 PX4 origin 水平距离分别<=100m、|h_rel|<=100m，量化前后均校验。物理验收沿用 #116：起飞>=2.5m；保持5飞控秒高度误差<=0.6m、倾角<=0.35rad；目标误差<=0.5m且速度<=0.5m/s持续2飞控秒；落地绝对高度<=0.3m且 disarmed。

## 运行及原始审计交付门

run-global-flight.sh 和 audit_global_flight.py 尚不存在，当前没有可执行的全球飞行/原始审计命令。#119/#120 只能在真实入口、安装身份、冻结配置与独立审计交付后各执行一次新 run。

每栈需要原始命令、接受/拒绝原因、完整 home/origin 快照、datum 证明、每次转换/发布关联、原生订阅/发布记录、物理 tick/输入/真值、terminal 与进程清理结果；全部关联同一 run/epoch/模型/配置/固件/消息/安装源码 SHA。

审计必须从原始全球输入和场景 AMSL 真值基准独立计算误差；禁止仅用转换后的 local setpoint 证明全球目标。分别检查正目标、home/origin 不同、越界零发布、home 变化旧目标零发布、不自动接管。缺原始文件、缺 terminal、错误绑定、datum 不明均失败。测试运输记录不是实飞。

本轮准确回归命令和结果见 validation/47-global-flight/review-20260909-118/summary.md。当前未满足两栈接入、真实全球飞行及物理目标/datum 验收，#118 保持 OPEN / needs-triage。
