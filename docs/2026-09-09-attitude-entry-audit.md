# #34 冻结入口合同的独立原始审计

2026-09-09。本次只扩展 `tools/audit_attitude_flight.py` 与 `validation/test_attitude_evidence.py`；没有修改任务、运行器、飞控、模型、控制候选、生产默认参数、预算或任何运行原件。主代理实读会话验证本代理为 `gpt-6-astra/high` 后放行，无嵌套委派。

入口合同 SHA256 为 `debd99a2b8c245608dd04bdaee61a9b9bc0e2c7240771c973eedec7c673c03c3`。原预算 SHA256 保持 `9a13e03abb5c9caf56d75ca4c5e4fd73d709037add7ec527405eee4d471d318f`。合同及运行源在真实第二场之前冻结；审计器扩展不改变合同，也不重解释首场失败。

## 独立检查

审计核对任务声明、运行源清单与 `run-source/Simulator/wksim_runtime/attitude-entry-v1.json` 的精确 SHA。新任务源码仍含入口合同而报告删掉声明时拒绝降级；确实没有入口合同的历史源码按原规则处理。

PX4 `VehicleControlMode` 由本轮实际安装且身份核对过的生成消息 codec 解码原始 CDR，不使用在线 `vehicle_control_mode_decoded` 代替它。三个入口分别在完整 2 s level 校准、位置恢复后的首次 5°姿态阶跃、完整 0.2 s 推力基线之前。

每个已声明完成的入口均重建公开中性请求、真实 native 中性姿态发布、相同 native timestamp 的仅 attitude 激活 OffboardControlMode、该入口新观察且最新的 VehicleControlMode，以及 MAVLink 原 datagram 中的实际中性 ATTITUDE_TARGET。核对全部冻结 true/false 控制位、原生时间戳、接收记录、四元数和推力。ATTITUDE_TARGET 的 `time_boot_ms * 1000` 必须严格大于 VehicleControlMode 的 native timestamp；检查 0.75/0.25 s 接收物理时钟新鲜度，并要求保留第一个合格目标，不能从较旧控制位或更晚匹配目标挑一个有利结果。

publisher discovery 单独检查唯一非零 endpoint GID，并核对入口期间身份不变。Humble raw take_message 没有每包 publisher GID，因此报告明确保留 `per_message_publisher_gid_available=false`，不将 discovery 身份冒充每包归因。

原始完整 1 ms 物理记录用于检查入口的 2 s 物理/10 s 墙钟截止时间、1.5–4.5 m 高度、4 m 位移和 15°倾角包线。原 level、姿态、推力基线窗口必须完整保留且位于入口完成之后；不会插值、平移固定跟踪窗口或寻找另一个通过窗口。实际入口中止仍标为 incomplete，任务不会由此获得 PASS。

AP 没有 PX4 中性控制位门槛。审计核对实际 `--defaults` 按顺序加载本场 `attitude.parm` 和最终 DDS 参数文件；文件内容必须等于记录的候选参数。`PSC_ANGLE_MAX=10` 是独立候选覆盖，原 defaults 不能被改成该值，`ATC_ANGLE_MAX` 保持 30。实际 GetParameters 生成 CDR 必须实读 10/30；如 BIN 含相应 PARM 记录，逐条与实读响应比较。服务响应仍标明是客户端返回响应的序列化，不冒充捕获的 DDS service packet。

## 验证与复现

20 项合成单测通过，包含原有 11 项物理/窗口/编码检查，以及入口完整链、15 种篡改、严格时间戳、挑选较旧控制位或更晚目标、接收年龄、合同删除或重封、候选参数与实际 defaults 不符等拒绝检查。AP 过渡关联检查另验证窗口前真实旧输入可解释、窗口起点或之后错误目标必须拒绝、缺少对应原始 CDR 或推力不符必须拒绝。合成测试只验证审计器，不能构成飞行证据。

离线环境按实际本轮身份加载 ROS Humble、PX4/common messages、AP attitude messages 与 attitude control overlay；ULog 使用原私有 `/root/wksim-attitude-audit-deps-g_2y8olg` 中的 pyulog 1.2.2。审计不启动 ROS 节点、FC 或模型，输出使用独立的新文件；工具同时拒绝把 `--output` 写入原运行目录。

```sh
python3 -B validation/test_attitude_evidence.py
python3 -B tools/audit_attitude_flight.py <terminated-run-directory> \
  --decoder-path /root/wksim-attitude-audit-deps-g_2y8olg \
  --output <new-file-outside-run-directory>
```

最终源码的首场回归：PX4 `/root/wksim-attitude-entry-audit-px4-01-final-regression.json` 与 AP `/root/wksim-attitude-entry-audit-ap-01-final-regression.json` 均为 **failed**，解析/身份错误均为空。PX4 原固定窗口仍只有 21 个样本，roll 最大误差 2.29114096°；AP 15°包线仍首次在 60.958 s 越界，3 个 1 ms 违例。旧证据与旧审计文件未改写。

## 第二场结果：两栈固定窗口与原生证据通过

本次通过仅适用于独立 quad-X attitude/thrust 候选场次；不是生产准入、硬件标定、两栈等推力或实时 40 Hz 证明。模型库仍为原准入 `cc0bc2d10790043251f38bb6a53f4d774379dd37a02b09cceba43ac1fafb02b3`。

原始目录分别为 `/root/wksim-attitude-flight-px4-20260909-02/attitude-px4-02` 和 `/root/wksim-attitude-flight-ap-20260909-02/attitude-ap-02`。两栈均在真实场次终结、进程回收之后审计，结果 PASS，错误为空。源码、原始记录、实际安装消息和控制实现、FC/Agent/模型身份、前后准入及启动命令均核对通过；safe_landing 为 true，cleanup_errors 为空。

| 完整原始证据 / 固定指标 | PX4 第二场 | AP 第二场 |
| --- | ---: | ---: |
| 1 ms 物理记录 | 45,940 | 78,761 |
| 实际 CDR | 10,351 | 11,707 |
| 冻结 hover demand | 0.5310305357 | 0.3134692609 |
| 完整 2 s level 窗口 | 24.14–26.14 s | 57.6–59.6 s |
| level 最大垂直漂移 / 速度 | 0.032413 m / 0.021257 m/s | 0.017205 m / 0.011932 m/s |
| 固定 0.4 s 姿态跟踪窗 | 28.64–29.04 s | 61.62–62.02 s |
| roll / pitch / yaw 最大误差 | 0.494051° / 0.100627° / 0.504331° | 0.253008° / 0.145976° / 0.502198° |
| 固定 0.5 s 推力阶跃窗 | 34.94–35.44 s | 66.1–66.6 s |
| 原 0.1 s 与此前 0.2 s 均值速度增量 | 0.4333117908 m/s | 0.3582989573 m/s |
| 姿态恢复 1.5 s dwell | 32.64–34.14 s | 64.36–65.86 s |
| 姿态恢复最大位置差 / 速度 / 倾角 | 0.264465 m / 0.180946 m/s / 2.939649° | 0.171237 m / 0.148789 m/s / 2.893338° |
| 推力恢复 1.5 s dwell | 36.36–37.86 s | 68.52–70.02 s |
| 原全程包线 1 ms 违例 | 0 | 0 |

跟踪窗各含 401 个真实物理样本；推力比较分别含此前 201 个和最后 101 个样本。level 校准后恢复、姿态后恢复和推力后恢复全部满足原 8 s 超时及 1.5 s dwell。在线 trace 下采样得出的速度增量与上述完整 1 ms 结果有微小数值差，未以在线值替代原始重算值。

PX4 三个入口耗时：

| 入口 | 物理区间 | 墙钟耗时 | 中性输入 → 控制位 → 实际目标原生时间戳（µs） |
| --- | --- | ---: | --- |
| level 前 | 23.8–24.12 s | 0.315855 s | 23804000 → 24064000 → 24084000 |
| 5°阶跃前 | 27.64–28.12 s | 0.471966 s | 27644000 → 28096000 → 28108000 |
| 推力基线前 | 34.14–34.7 s | 0.549056 s | 34164000 → 34648000 → 34684000 |

原始控制位和端点身份均满足冻结合同。PX4 固定跟踪窗内有 8 条 ULog 目标采样，AP 有 13 条 GUIA 目标，均匹配公开目标。PX4 414 条电机原生采样与下一组物理输入最大误差为 5.87e-8；AP 767 条为 0。AP 30,718 条 SIM2 按既定源代码时序关系对应真实状态，最大误差 1.19e-7。日志采样和接收 cursor 的边界沿用首轮报告，不声称每毫秒独立网络包归因或精确首次受理 tick。

AP GetParameters 与原生 BIN PARM 均实读 `PSC_ANGLE_MAX=10`、`ATC_ANGLE_MAX=30`，实际候选文件和启动 defaults 一致。BIN PARM 的 Default 字段是在该场候选 defaults 加载之后记录，不能拿它声称生产原始默认也为 10；原 defaults 文件保持零/未覆盖，候选覆盖独立保留。

### AP offered 时间关联错误及修正

保留初审文件 `/root/wksim-attitude-entry-audit-ap-02-final.json` 的失败结果。其唯一错误是旧审计器把 public offered 后的所有 GUIA 都当作该新命令的即时 native 目标。实际原始链为：旧 hover CDR header 66.076 s → public offered cursor 66.08 s → 旧 hover GUIA 66.087 s → 冻结窗口起点 66.1 s → 新推力 CDR header 66.102 s。旧目标为 0.3134692609，新目标为 0.3434692621。

修正只涉及证据关联：保留整个 offered 后 timeline，并把 66.087 s 旧 GUIA 与最新先前真实 CDR 对照，记录为 `pre_window_transitions`。原固定 66.1–66.6 s 物理窗口没有移动，所有窗口内 GUIA 必须匹配新目标；不通过搜索第一个正确目标重新选择窗口。合成测试明确拒绝起点或之后的错误目标及无法由原始 CDR 解释的窗口前目标。最终源码回归两栈首场仍保持原失败。

### 实际节奏与重复性

配置 output_rate 为 40 Hz，但本次实际 native CDR 平均发布节奏为：PX4 level 33.333 Hz、roll 33.0 Hz、推力阶跃 31.25 Hz；AP level 34.119 Hz、roll 33.024 Hz、推力阶跃 33.543 Hz。对应 DDS source 实测也约为 31–34 Hz。没有因为配置值为 40 就宣称实际达到 40，也没有加入新的容差把实测 33 Hz 改称 40 Hz。PASS 表示本报告列出的固定动作、入口和证据检查通过；调度/输出频率一致性仍应单独处理。

最终固定审计器对两栈各执行两次，每栈完整 JSON **逐字节一致**，全部可比检查和指标相同：

- PX4：`/root/wksim-attitude-entry-audit-px4-02-verified-a.json` 与 `-verified-b.json`，SHA256 `39669be3af0467b8cc597c0b329e7a6053892f5975052c7e96dc5e6c4b042b77`。
- AP：`/root/wksim-attitude-entry-audit-ap-02-verified-a.json` 与 `-verified-b.json`，SHA256 `71480fbfb5472767574c834a950f649c01dc9bfa9afe61da29ac21e85de90f2e`。
