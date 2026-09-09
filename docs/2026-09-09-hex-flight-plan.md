# #25 Hex X 独立双栈任务候选

新入口 `tools/run-hex-flight.sh` 使用明确的实验 `model_profile=hex_x`。它复用已封存的原 Control 公共位置/偏航功能，通过新的六路物理接缝连接固定 Hex 源模板。没有调用生产 Quad preflight，也不把 Quad 的准入结果重标记为 Hex 通过。

截至实现阶段，仅完成纯 fixture 和只读准入。未启动模型、FC、ROS 节点或 UE；双栈飞行、冷重置和六旋翼显示结论均待实际运行及独立原始证据审计。

## 身份和启动

`hex_candidate.py` 在干净 shell 中加载固定旧 overlay，调用 `_fixed_resources(joint_quad_dds_v1)`。它校验旧 AP/PX4 源、构建、固件、原 Control 源/安装、消息、Agent、原始飞行证据与旧模型；新 Hex 模型另外检查保存配置、build manifest、全部 source/header/wrapper recipe、库 SHA 和六路 plan。旧资源仅为复用身份依据。

实际旧资源为 AP `/root/wksim-ap-clock-stop-OXQqdR`、PX4 `/root/wksim-px4-state-ONa1Kw`、Control `/root/wksim-joint-control-FVMjak`。Hex 库为 `/root/wksim-hex-candidate-private/build-ihnane6f/libwksim_hex_candidate.so`，SHA256 `b10ef333129b44ce41d2d8d944a1e3d1161db9201bb1aea9eca88e726a5a7c9c`；build manifest SHA256 `1f6534d11b5634723fa1c3c2e4d518ee11a281d5a28f24149c836eb56199834c`。

模型身份为 `sha256:d703da7f888e7110e402aa32ff911cabcb24e0b01afb8bbf4c9ec1ccb897276a`，六路 plan 为 `sha256:319c5cba50eb11b81f70ac3ade707879c2fdba252335aa039674e93b9168e1a0`。每次实验另有包含 stack、模型、plan、全部参数与固定构建 manifest 的 configuration identity；run_id 不参与该身份，以便比较同配置冷重置。

AP 默认文件顺序严格为 `copter.parm,hex.parm,dds.parm`，清除旧 Quad 文件；`LOG_DISARMED=1` 用于保留原生地面日志。PX4 从原 `launch_spec` 取得已验证的 DDS/MAVLink/instance 命令形状，删除全部原 `PX4_PARAM_*`，再应用六路 plan 和启动项；使用 custom POSIX 10016，不能称作 stock 6001。干净环境不继承未知参数。每次使用新的工作目录、参数存储、网络/IPC/mount namespace 和私有 `/tmp`。

## 首次运行前冻结合同

[hex-flight-v1.json](../Simulator/wksim_runtime/hex-flight-v1.json) SHA256：`33748c4374d5f297ae928d1682bc9ef00dde95030249fe5c7ff0dce21363ddcc`。执行前校验固定 SHA；主线在 RUN RELEASE 前保留该文件和 SHA。

公共门槛直接沿用现有 Task：ready 55 秒、PX4 prearm 55 秒、控制接管 40 秒、起飞 25 秒且高度至少 2.5 m；悬停 5 秒、高度 3±0.6 m、roll/pitch 绝对值不超过 0.35 rad；ENU 航点 `[2,3,3]` 在原默认 20 秒内达到，位置误差与速度范数各不超过 0.5，保持 2 秒；降落 30 秒，最后已上锁且高度绝对值小于 0.3 m。同义门槛同时核对物理真值；dwell 需公共 boot clock 和模型时钟都覆盖固定时长，仍使用原 Task 的 15 秒 dwell watchdog。在线物理真值最大相邻间隔 0.05 秒、文件新鲜度 2 秒。

PX4在地面先按合同显式应用两项零X坐标（CA_ROTOR0_PX/CA_ROTOR1_PX），等待固定值响应；随后每项参数只读一次、每项最多 10 秒，总参数读取 AP 45 秒/PX4 90 秒。AP 共 33 项（29 项六路 plan、DDS 三项、LOG_DISARMED）；PX4 共 77 项（74 项六路 plan、SIM_BAT_ENABLE、UXRCE_DDS_SYNCT、SYS_AUTOSTART）。AP 使用原生 `/ap/get_parameters`，PX4 使用 `PARAM_REQUEST_READ`。读取前、等待中和响应后都必须保持地面、fresh 公共/物理状态、相同控制 epoch 和 native generation；任何缺项、错值、类型错误或变化都会在 arm 前终止。PX4 参数类型来自实际固定构建 `parameters.xml`，INT32 从 PARAM_VALUE 原始前四载荷字节解码，FLOAT 对比实际 float32 存储值。

每次独立运行总 watchdog 300 秒，不能据此延长上述动作门槛。失败结果保留原始轨迹并有序退休本次拥有的进程；不自动改参、降低门槛或重复飞行。

## 原始证据与边界

`hex_task.py` 使用原公共 `session_v1` SetupRequest/CommandRequest，包括模式、解锁、3 m 起飞、悬停、航点和降落。额外 observer 使公共 request topic 有两个订阅者，准入严格要求它们正好是原 Control 和本 recorder、两个不同非零 endpoint GID。保存实际 middleware CDR、发现图、服务 request/response 的客户端序列化、全部收到的 MAVLink datagram 与解码包载荷。发现图不能冒称每包 publisher 归属。

`hex_physics.py` 保存每 1 ms 的完整 input16/output120、原始执行器字节和六路 RPM `[16:22]`，默认 50 Hz truth 用于在线任务核对。保留原生 AP BIN/PX4 ULog、日志、启动 argv/cwd、PID/boot_id/starttime、maps、运行源副本和 hash、前后只读准入。缺原生日志、模型初始 tick 不为零、清理失败或身份变化均不能得到 observed。

返回 `status=observed` 只表示运行器观察到既定流程并保存证据，完整原始数据仍待独立审计，不能当成 #25、R1/G6、真实机架标定或生产配置通过。UE 六路显示由主线单独接入和验收；本入口不发送错误的 Quad 显示包。

## 复用命令与冷重置

Ubuntu-22.04 中从项目根目录执行，只读准入：

```bash
python3 -B tools/run_hex_flight.py --stack arducopter --run-id hex-ap-check --preflight
python3 -B tools/run_hex_flight.py --stack px4 --run-id hex-px4-check --preflight
```

主线单独放行后，首次飞行命令（示例目录必须尚不存在）：

```bash
bash tools/run-hex-flight.sh --stack arducopter --run-id hex-ap-01 --output-root /root/wksim-hex-flight-ap-01
bash tools/run-hex-flight.sh --stack px4 --run-id hex-px4-01 --output-root /root/wksim-hex-flight-px4-01
```

再次单独放行的冷重置示例：

```bash
bash tools/run-hex-flight.sh --stack arducopter --run-id hex-ap-02 --output-root /root/wksim-hex-flight-ap-02 \
  --cold-reset-from /root/wksim-hex-flight-ap-01/hex-ap-01/result.json
```

`--cold-reset-from` 只接受已安全降落、终止和回收的旧 Hex observed 结果，保留旧 result SHA 与子进程身份。若旧 boot_id/starttime 对应进程仍在，拒绝继续，绝不发送 kill。新调用要求同配置身份、不同 run_id、不同 Control epoch、新 native 参数目录与模型 tick 0。它表示从终态冷重建，不能称作同一 live 会话内热恢复；旧结果内容不被修改，并在结束时再次核对父 SHA。

纯测试：`python -B validation/test_hex_flight.py -v`，当前 11 项通过。实读 PX4 与 AP candidate preflight 均为只读校验，报告分别暂存 `/root/hex-preflight-only.json` 与 `/root/hex-ap-preflight-only.json`，未启动运行子进程。

主代理首次飞行前整合：单独Hex参数文件另保留原模型适配所需的MOT_BAT_VOLT_MIN/MAX=0、SIM_RATE_HZ=1000、ARMING_CHECK=1及原生观测流；未沿用copter.parm中的9.6–12.8V补偿。新的plan与协议SHA如上，旧提案未运行并保存在validation/hex-flight-preparation-20260909。原动作/物理阈值未变。原始物理记录每20ms flush并在不可变start绑定run_id/model_identity，供后续真实显示消费；不把旧文件重打成LIVE。最终JSON沿用既有显式nonfinite_number诊断标记保存可选未知字段，原始CDR未变；必需物理/控制值仍严格有限。

本轮已完成PX4-03正常落地，结果仍observed待独立审计；前两次地面拒绝及具体修正见2026-09-09-hex-round-handoff.md。AP及cold-reset/live-UE尚未执行。后续按Luna子票而非本节历史示例随意重跑。
