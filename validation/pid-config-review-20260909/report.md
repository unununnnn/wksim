# #88 PID 配置选择与结果可见性前置复核

复核时间：2026-09-09（JST）。范围是 #88 指定的既有 `--config` 入口、实际 `external_pid` 结果和 #35 原始验收标准；不增加工作台 UI 门槛，不启动运行时，也不改动父代理负责的产品计划。

## 结论

在 #88 的限定范围内，既有配置路径满足 #35 对“选择并显示实际 PID”的可验证要求。命令行契约是 `--config <path>`，控制器选择来自冻结 JSON 的 `controller: "pid"` 字段，而不是额外的 `controller=pid` 参数。`load_config()` 先校验冻结配置 SHA，再调用 `select_controller()`；`select_controller()` 只接受 `pid`，其它选择立即拒绝。

PX4 运行结果也不是仅改标签：结果中的 `config.controller`、`config.external_pid.controller` 均为 `pid`，实现字段为 `Simulator.wksim_control.position_pid.PositionPID`。独立审计逐条重算 PID、检查 public `XYZ_ATT` 载荷和 request/command 身份，并检查测量窗内没有原生位置或轨迹目标覆盖。因此现有 CLI 配置/结果路径可以作为 #88 的 bounded review 通过项。

这不关闭 #35。PX4 证据已经通过 `recorded_evidence_pass`；AP #87 的第二次实际运行已完成全部阶段并安全落地，但 postflight identity 和独立严格审计仍待完成。双栈定点、轨迹和扰动这一原始 AC 必须等 AP 独立审计通过后才能判定。当前工作树还包含父代理未提交的 AP 反馈节拍/CDR 修订，PX4 封存审计不能直接作为修订后源码的全局验收证明。

## 配置、源代码和测试核对

- `Simulator/wksim_runtime/pid-flight-v1.json` 的 schema 为 `wksim.pid-flight.v1`，`controller` 为 `pid`，配置 SHA256 为 `25d50ddbbd44e658a72123e6d524a5c5021b355367a99e46a898ec9b9cecadc0`。
- `tools/run_pid_flight.py:223-242` 要求 `--config`，通过 `load_config()` 读取并把配置写入 admission 的 `external_pid`；`run()` 将同一配置写入运行 `config.json` 与 `pid-protocol.json`。
- `Simulator/wksim_runtime/pid_task.py:24-30` 做原始配置 SHA 校验并选择控制器；`:107-126` 将实现记录为 `PositionPID`；`:222-237` 只发布 `XYZ_ATT`，同时记录实际输出、质量、模型身份、校准值和 public request/command 身份；`:137-140,255-299` 禁止测量窗内的原生位置帮助函数；`:376-377` 把结果放在顶层 `external_pid`。
- `Simulator/wksim_control/position_pid.py:213-217` 的选择器只接受 `pid`。原始 Prometheus 来源、初始化/重置、质量和推力映射已在 `docs/2026-09-09-pid-controller-port.md` 固定并有纯算法 oracle。
- 当前纯测试命令为 `python -B -m unittest validation.test_pid_flight validation.test_pid_flight_audit validation.test_position_pid -v`：共运行 47 项，其中 46 项通过、1 项因未在 WSL sourced ROS 环境而跳过。覆盖选择拒绝、实际 `XYZ_ATT` 出口、时间戳/复位、测量期间位置帮助拒绝、独立 PID 重算、native 关联与恶意证据拒绝。

封存 PX4 运行的主要证据是 `validation/pid-native-association-20260909/audit.json`（文件 SHA256 `6d4d587ca9a47dd4a7562ed3706eb432d9dca2988349688c39222f9ae2ec78a2`），其状态为 `recorded_evidence_pass`；审计输入中的实际运行 `result.json` SHA256 为 `4744573ae423163f4dab5e44b5b062fe178a4d30884144ac52b280fb1379dd91`。记录的 PX4 运行 ID 为 `pid-px4-native-backpressure-20260909-01`，配置/协议 SHA 与上面一致。

该审计重算 point/circle/disturbance 分别 166/400/284 个 PID 更新，关联 850 个 public request 到 native attitude CDR，比较 512 个 native motor 输出；physics 原始流为 95,360 个 1 ms tick，扰动实际施加恰好 1,000 tick。在线结果的最大值分别为：point 位置误差 0.066571 m、速度 0.029606 m/s、yaw 0.007190 rad；circle 位置误差 0.128377 m、速度 0.322815 m/s、yaw 0.012640 rad；disturbance 位置误差 0.103621 m、速度 0.120063 m/s、yaw 0.010852 rad。circle 没有单独的速度预算；固定审计按原配置的误差/yaw窗口判定。

复核时的 sealed PX4 source hashes 包括：`tools/run_pid_flight.py` `695e59e92700045e4d7ce297f9b11127939bf833855195edac27dc961d4c430f`、`tools/run-pid-flight.sh` `c772423deea8dde33914f05edef5777cf116c06cbae4c008f9accaea09ae8302`、`tools/pid_physics.py` `2e540fed821c07df63e83252d8288d03599da613e2386cadd0e5dd04abcb0775`、`Simulator/wksim_control/position_pid.py` `96160fcfbabed9660c06599679cadaa4530a3ef7a60cc442432af549da2d7884`、以及上面的 PID 配置 SHA。封存运行中的 `pid_task.py` SHA 为 `54eefcb81043992d1feb9c484510c51a1c1a8eea48ff5c3b1d16bf98bb4db695`。

当前共享工作树的 `pid_task.py` 已变为 `ffbddccff7a1135bb6342c6883d8a7c22b2922fc16b0d2652e4d80a8fc073d62`，`validation/test_pid_flight.py` 已变为 `8a894c70ef6c2a880010b5c7664abcd40324297c1507fe20562102fd4f97d48f`，对应父代理的 AP shaped-attitude/backpressure 修订；这两项尚未提交。因而上段 PX4 hash 只绑定已封存运行，不能代替 AP 通过后的当前源码重封存与审计。

## AP #87 通过后必须补的精确复核

AP 运行结束后，应以该 AP run 的实际路径生成新的独立审计，并逐项保留下列证据。不能把 PX4 结果复制成 AP 结果，也不能只看在线 `online_ok`。

1. 身份：`result.json`、`admission.json`、`postflight-admission.json`、`config.json`、`pid-protocol.json`、`pid-resolved-config.json`、`pid-progress.json`、`pid-trace.jsonl`、`prometheus.jsonl`、`attitude-native.jsonl`、`physics-actuator-packets.jsonl`、`physics-1ms.jsonl`、`truth.jsonl`、`disturbance-event.json` 的输入 SHA；`config.external_pid == pid-protocol`、`controller == pid`、协议 SHA 为 `25d50dd...cadc0`；run-source 中执行的 `run_pid_flight.py`、`pid_physics.py`、`pid_task.py`、`pid-flight-v1.json`、`position_pid.py` 与运行前实际 hash 一致，并检查 source/candidate unchanged。
2. 资源：AP 固件、Micro-ROS agent、固定 model library 和 Control 安装包的路径、字节 SHA、启动 argv、maps 与 admission/postflight identity 一致；实际 Control argv 仍含 `native_attitude_profile:=attitude_thrust_v1` 和 `enable_external_attitude:=true`。
3. 校准：AP 本轮 native `ATTITUDE_TARGET` 连续覆盖 3 s，端点各在 0.1 s 内、相邻样本间隔不超过 0.25 s；median 与 `pid-resolved-config.json`/结果相同并在 0.15–0.8；同轮 2 s level validation 满足高度变化不超过 0.3 m、竖直速度不超过 0.2 m/s，入口位置/速度/倾角/yaw 门槛也由原始 truth 重算。
4. PID 轨迹：逐行重算积分、力、姿态投影和 AP 正 collective；每行 `controller=pid`、配置/协议/model/mass/calibration/epoch 身份一致，state 时间戳来自原始 public CDR；public command 必须是 `XYZ_ATT`，request/command ID、ACK 和 AP native target 一一对应，测量窗内不得有位置/速度/高度 helper 或 `XYZ_POS`。
5. AP native/物理接缝：消费原始 AP `.BIN` 与 `/ap/wksim/attitude_target_v1` CDR；测量窗内不得有 `GUIP` 或 GPS pose override，`GUIA` 的 rate/altitude 字段必须为零；`SIM2` 必须按源派生时钟映射到 1 ms truth；`RCOU` motor 输出必须与实际 applied input 对齐；每个 PID request 都要有 distinct native attitude CDR、执行日志和无遗漏的目标关联。
6. 固定预算：从完整 `physics-1ms.jsonl` 重算 point（位置/速度/yaw ≤ 0.3/0.3/0.15）、circle（位置/yaw ≤ 0.35/0.15）和 disturbance（声明窗口位置 ≤ 0.5，事件结束后 8 s 内恢复，末 1.5 s 连续位置/速度/yaw ≤ 0.3/0.3/0.15）；扰动必须绑定同一 run/protocol，四路输入恰好 1,000 tick 乘 0.97，事件首载入距 start 至少 1,000 tick，边界和 tick 连续性通过。
7. 终止与限制：safe landing、children reaped、cleanup_errors 为空、最终 public/physical state grounded；审计状态为 `recorded_evidence_pass`。保留审计声明的限制：没有 exact first native acceptance tick 或 publisher GID，native 日志为采样证据，mass 是 source/hash bound 而非 runtime getter；这些限制不能被写成 Full 或生产准入。

完成以上 AP postflight 与独立审计证据后，主代理再以当前源码 hash 重跑 #88 的结果复核。届时可同时确认 #35 的双栈物理 AC；在此之前，本报告结论保持“配置/结果路径通过，#35/#88 整体待 AP 审计接受”。
