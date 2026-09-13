# AP P+V 候选运行与准入接缝

2026-09-09，只读源码调查及本报告写入。主代理实读本次 session JSONL，确认 `/root/ap_pv_runtime_seam` 为 `gpt-6-astra/high` 后释放执行；无嵌套委派。未构建、准入、启动 SITL/UE/MATLAB、修改固件/适配器/profile/pin/阈值，未操作进程或发布。本文为 #33 的第一切片方案，不能据此关闭 #33。

**最小路径是单独的实验准入器 + 显式 P+V 适配器开关 + 真实轨迹任务/原始审计。现有候选已具有完整 XYZ P+V+yaw 的固件接线；当前任何正式入口都不能仅靠替换路径运行它。真正 XY 速度/Z 位置仍是另一项 Guided 轴语义扩展。**

## 当前身份与原生语义

本轮在 Ubuntu-22.04 root 直接读取候选 manifest、二进制及实际 DDS/Copter/Guided/Location 源，重新计算前两项 SHA256，均匹配交接：

| 项目 | 固定值 |
| --- | --- |
| 候选根 | `/root/wksim-ap-pv-vn04950x` |
| `pv-build.json` SHA256 | `e05e5c9d0b2b576d2cf1751b01557219d6da36998b22ded396ca33d7f5c4db62` |
| `build/sitl/bin/arducopter` SHA256 | `7dfeb027e06712380f499611e2ba1bc809ed71f74ae477807ac5b2d51d62bb44` |
| `pv-source.json` SHA256（build manifest 绑定） | `c65a91801f7488a2a239895a9d7c8f3ca2167d417180b4ff64ab2977ddf3970b` |
| 不变基线 | `/root/wksim-ap-clock-stop-OXQqdR/wksim-build.json`，SHA256 `f347ba252fbfc33bc92baffba08660f33c3a0e4462e90177ba84bdc11408660a` |

本轮没有重跑完整 24,593 文件验证，历史完整验证见 [候选跟进](2026-09-08-pv-replay-followup-report.md)。正式试飞前必须重新调用完整验证器，不能用本轮两个 SHA 代替。

实际 `AP_DDS_ExternalControl.cpp` 接受 map 帧、完整位置和完整速度，P+V+yaw mask 为 **2496/0x9C0**；3520 忽略 yaw，2552/3576 保留纯 P。速度经 ENU `(x,y,z)` → NED `(y,x,-z)`，yaw 经 `wrap_PI(pi/2-yaw)`。Copter 新方法要求 armed + Guided，经 `Location::get_vector_from_origin_NED_m` 转 EKF-origin NED，再调用 `ModeGuided::set_pos_vel_NED_m`。

候选 `mode_guided.cpp:612,618,912` 实读确认：P/V 接口显式给零 A，保留 fence、target timestamp、`get_timeout_ms()` 和原生控制器；超时清零 V/A，并非泛化的“收到停止信号即当前位置悬停”。`Location.cpp:335` 仍经 origin NEU cm 再转 NED m；home-relative 高度不能直接当 origin-relative 高度。上述接口没有每轴 position-ignore 参数，不能把 NaN、任意 XY 锚点、GUIDED_OPTIONS 改值或外部 Z PID 当成混合轴实现。

## 已有入口的准确复用边界

以下判定来自实际源码；除上面的 manifest/二进制读回外，本轮未执行这些验证器或它们的失败分支。

| 文件/入口 | 对本候选的处理与可复用部分 |
| --- | --- |
| `tools/verify_ap_pv_candidate.py:28` | **可以核验构建身份**：显式 `pv-build.json` + 外部 `--sha256`，重新枚举源码、独立 Git 根、基线、补丁、准备器、固件和两份构建日志。成功仍明确 `production_admitted=false, flown=false`。应原样复用，不把返回值升级为实飞证明。 |
| `tools/test_ap_pv_native_boundary.py:15` | **可以测试该候选函数切片**，已有 `--candidate`/`--output`。只核验其读取的三文件对 pv-source 的 SHA，不要求独立外部 manifest SHA；Location/Guided 等为 stub。它是边界测试，不能承担身份准入、真实转换/fence/timeout 验收。 |
| `tools/ap_clock_candidate.py:32,72` | **拒绝**：仅 `/root/wksim-ap-clock-stop-*`、`wksim-build.json` 及该工具的完整 snapshot schema；其基线还是 `/root/wksim-ap-dds-yaw-state-4Wr27s`。不能重命名 PV 目录/manifest 来绕过。 |
| `tools/validate_sitl_physics.py:37–82` | **拒绝现有 PV 选择方式**：`--ap-dds-candidate` 只认 yaw 根；`--ap-build-manifest/--ap-build-sha256` 调上述 clock admit。即使新增准入，现有 mission/yaw gate 也只有位置任务。`sitl_dds.py` 的原生目标发布默认 mask 0xDF8，不发送 V；它不是 P+V 轨迹验证器。 |
| `tools/run-prometheus-validation.sh` | 第四参数是 **旧 AP 消息 overlay**，只认 yaw 根；第五/六参数才是 clock 固件 manifest/SHA。不要把 PV 根当 ROS overlay；PV 没改变 IDL，也没构建新 overlay。控制工作区参数只认 `wksim-ros2-*`，不能直接传 joint-control 候选。 |
| `tools/run_joint_flight.py:197–219,446` + `run-joint-flight.sh` | 可复用私有 net/ipc/mnt、双 FC、权威时钟、公开 Task、控制候选环境及进程/原始证据框架；**现状仍通过 clock admit 拒绝 PV**，且 task_main 调 `Task.execute()`，不是轨迹任务。已有参数是 `--ap-manifest/--ap-sha256`、`--control-manifest/--control-sha256`、可选 PX4 manifest/SHA。 |
| `tools/joint_control_candidate.py:56` | **可以核验未来新控制候选**，不核验 AP 固件。要求 repo/staged/installed Python 集合与 SHA 完全相等、构建输入/脚本/日志一致和独立 `/root/wksim-joint-control-*`。`environment()` 只调整子进程 overlay；还须证明运行时实际导入的是该包。 |
| `Simulator/wksim_runtime/preflight.py`、`joint_profile.py:20,47,141`、`independent_profile.py:13` | **正式入口拒绝 PV**：历史基线根/固件 SHA 固定；独立配置只能选择固定资源；joint 要求 descriptor 精确等于当前 pin、固件为 `wksim-build.json` schema，并绑定历史实飞。`promotion_flight` 不放开这些身份门。 |
| `tools/validate_independent_velocity.py:114`、`audit_independent_velocity.py:17` | 当前 #32 工具严格选择 `independent_quad_dds_v1`，任务/审计固定为速度操作数和阶段；**不能直接接受 PV 候选或作为轨迹验收**。物理 cursor、原始公开输入和身份审计方法可复用。 |
| `tools/validate_ap_json_clock.py:29`、`probe_joint_clock.py`、`probe_ap_shutdown.py` | 前者根白名单不含 PV，后两者使用 clock admit，**现状拒绝**。若需继承时钟/停止回归，应走新的明确 PV 身份入口，不改名、跳过或拿旧通过结果标记候选通过。 |

## 最小实施顺序（尚未实施）

1. **新增 `tools/ap_pv_candidate.py` 实验准入器**。输入使用独立命名的 `--ap-pv-manifest` 与 `--ap-pv-sha256`，互斥旧 clock selector；先运行 `verify_ap_pv_candidate.verify`，再核验 Ubuntu22.04/Humble、固定 DDS agents/消息 overlay/模型/PX4，以及单独封存的新控制候选。准入输出另写 `experimental-admission.json`，绑定全部 manifest SHA、实际 firmware SHA、控制包/模型/消息/Agent 身份、准确 P+V 能力与运行器源码 SHA；成功只能标记允许有界实验，保持 `production_admitted=false, flown=false`。不写/改 `pv-build.json`，不向 `joint-profiles.json`、`capability-index.json`、正式 examples 或旧实飞证据补新 pin。

   不能简单改 `joint_profile.check_resources` 的参数副本：它要求 descriptor 精确等于固定 profile。也不能因新 adapter 让 `_control` 的“当前仓库源 = 旧已安装源”检查失败就跳过整项。独立检查并记录原封存基线组件；以 `joint_control_candidate.check` 将当前 repo/staged/installed 源绑定到新候选。基线失败仍拒绝，候选控制校验是显式替换的身份分支，不能沿用旧 `ok=true` 结果。

2. **只改两处控制接缝并建立新安装候选**：`ros2/src/prometheus_control/prometheus_control/node.py:58` 声明只读、默认关闭的精确 profile 参数（建议 `arducopter_pv_profile=full_xyz_pv_yaw_v1`，空值为原行为）；`native_arducopter.py:198,225` 在该 profile 下放行 TRAJECTORY，并在现有 velocity 分支前识别完整 P/V+yaw。要求 P/V 三轴全有限、A 全未激活、yaw 有限且 yaw_rate 未激活；用现有 `home_offset` 转完整 P，`FRAME_GLOBAL_REL_ALT`、map、native boot stamp、mask 0x9C0、ENU velocity 原样填入同一 GlobalPosition。保留新鲜度、odom、订阅者、100 m 包络、原纯 P/纯 V/默认拒绝和原子失败。完整 P/V 之外仍拒绝混合轴。`shaping.py:98` 已输出 P/V/yaw 且故意不发送 A，无需更改。

   可复用 `tools/build-joint-control.sh` 新建工作区和 `joint_control_candidate.check`；新 profile 开关仅由通过候选准入的实验 launcher 注入。不改通用 `runtime.launch_spec` 的默认 argv，不安装覆盖当前正式工作区。

3. **给实验运行器增加精确 selector 与轨迹 task**。最靠近的框架是 `tools/run_joint_flight.py`/`run-joint-flight.sh`：增加上述 PV 身份参数及明确 `--task-profile full_xyz_pv_yaw_v1`；只有 PV admission 成功才选该任务并向 AP Control 注入开关。新增 `tools/pv_trajectory_task.py` 通过 session_v1 公开 `TRAJECTORY` 命令发送同一固定时间轨迹，沿用 Task 的公开 setup、状态、停止/接管/降落语义；两栈用相同轨迹时间，逐条保存 P/V/yaw 和 request/run/control/scene 身份。不能用 monkeypatch、改写 `preflight.ok`、直接诊断 DDS publisher 或重用位置任务 PASS 取代这条链。

4. **先冻结轨迹与验收，再运行**。新增专用计划和 `tools/audit_pv_trajectory.py`，在首次试飞前冻结轨迹公式/采样、误差/驻留/恢复窗、停止/模式切换顺序、时间/资源限额；本文不凭空指定阈值。先做默认 profile 拒绝、新 profile 严格 mask/有限值/转换及原命令输出差分；再预约有界真实双栈运行，保留原生 DDS 目标（AP mask/地理 P/ENU V/yaw/native stamp；PX4 P/V/yaw/失活 A）、公开命令、飞控原生日志与真值。AP 实际 handler 无目标 ACK，应以真实 Guided 目标日志及响应佐证执行，发送成功只算发布。

5. **单独补真实原生边界与退出证据**。用实际 origin/home 不同的转换、缺失 terrain/origin、fence 拒绝、停止目标流后的 native timeout，以及模式切换/停止/恢复的新锚点检查补齐 stub 未覆盖部分。记录有效参数而不偷偷调 GUIDED_OPTIONS/fence/timeout。运行前后完整身份复核；启动及运行中绑定 `/proc/<pid>/exe`、cmdline、start ticks、控制实际导入路径、原生消息 schema/动态库映射，并保存原始记录 SHA。失败与未覆盖项原样保留。真实飞行与审计通过后另写 flight evidence；生产提升仍是后续独立步骤，构建/试验准入/动作完成三个状态不能合并。

## 调查来源与索引边界

已读 AGENTS/CONTEXT、运行边界/项目隔离、#33 本地票据、五项批准记录及 2026-09-08 四份指定报告。`docs/adr/` 在 wksim 不存在；未套用父/兄弟工程 ADR。Codebase Memory MCP 可用，list_projects 两页确认项目 root；index_status 为 ready、50,865 nodes/165,157 edges，coverage generation `2026-09-08T12:13:51Z`。精确检查 joint_profile/preflight/AP adapter 为 no_recorded_issue 但 metadata_changed，tools 明确 excluded。故本轮按已知路径和配置/诊断文字定位后读取实际源码，没有依赖旧图推断新结构，也没有为唯一报告刷新全库。外部 WSL 固件按项目规定图外直接读取。上述 source 行号是本轮读取位置，主代理尚有并行 #32 改动，实施前需再次核对当前源。
