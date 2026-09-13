# #45 GNSS 事件离线包与 ArduPilot 原生接缝核查

2026-09-09 JST。实读 [#45](https://github.com/unununnnn/wksim/issues/45)、#1、项目 AGENTS/CONTEXT、[可执行前沿 GNSS 行](2026-09-09-ready-frontier.md)后，仅新增 `Simulator/wksim_core/gnss_event.py`、`validation/test_gnss_event.py` 和本文。未修改 PX4/AP 适配器、核心循环、运行时、任务控制、模型或固件；未启动 FC、ROS、模型、UE；未安装依赖、修改工单或提交。

## 本次实现与合同

`GnssEventPlan` 是单个停止新 GNSS 报文的计划，以 run_id / epoch / vehicle_id 绑定唯一对象，权威 1 ms tick 的 `[start_tick, end_tick)` 为有效区间。没有通用故障框架、墙钟调度、缓存重放或后台线程。计划可在下一候选前安装，不能覆盖、重复安装或追溯已处理 tick。

`GnssSample` 保留来源身份、递增 sequence、原始采集 source_tick 和当前 PX4 `gps_arguments` 的完整 13 个整数参数：time_usec、fix_type、lat、lon、alt、eph、epv、vel、vn、ve、vd、cog、satellites_visible。字段按当前 HIL_GPS 参数位置保存，不丢弃坐标、质量、速度或源时间。构造时拒绝非法身份、bool/浮点冒充整数、错误字段长度、可变列表、非法整数范围和非法航向。输入是 Python 类型合同，未增加 JSON/文件解析入口。

**时间合同只适用于 epoch 相对仿真微秒，不适用于 Unix/GPS 周时间。** source_tick 必须由采集边界填写，不能填收到报文时的 tick；原始 `gps[0]` 必须保留。控制器同时检查 tick 年龄和原始微秒年龄，不会因到达时间变新而更新源时间。原始微秒不得晚于采集 tick，来源时间、sequence 和采集 tick 均须严格递增；重复发送路径也因此不能再次授权 GPS。静止载具的坐标可保持不变，不能靠坐标相等判断陈旧；若调用者同时伪造原始采集时间和原始 GPS 时间，本模块不具备证明真实采集的能力，实际接入必须在采集边界保留原包。

`GnssEventController.decide(sample, tick=...)` 返回不可变的 `GnssDecision`。其 `record()` 可直接 JSON 序列化，包含控制器与源身份、权威决策 tick、完整计划、年龄预算、原包、源 3D fix 质量、是否处于中断区间、受理结果、原因和拟输出参数。所有拟输出参数与原参数逐项相等，不重打时间戳。格式不合法的输入在构造/入口抛出异常，由未来集成调用者记录原始输入及异常；格式合法但 foreign、future、stale、duplicate 或 backward 的候选返回明确拒绝记录，不改变游标。

| 事件/状态 | 离线决策 | 边界 |
| --- | --- | --- |
| 计划内停止新 GNSS (`signal_loss`) | 接受新原始候选、记录质量/时间、`outbound_gps=None` | 只表示计划抑制；未模拟射频传播、接收机 RF 状态或真实发包结果 |
| 新鲜来源未达到 3D fix (`invalid_fix`) | 计划外原样输出无效定位报文 | 与停止报文不同；本轮不制造无效 fix，只保留并区分输入质量 |
| 原始采集 tick 或原始 GPS 时间超过预算 (`stale_source`) | 拒绝、无拟输出 | 旧原包不因新决策 tick 变有效；预算包含等号 |
| 重复或倒退来源 (`duplicate_or_old_source`) | 拒绝、无拟输出 | 被中断抑制过的原包也不能在恢复 tick 重放 |
| 计划结束后的新鲜候选 (`pass`/`invalid_fix`) | 恢复逐包原样输出 | 不表示 EKF 恢复、任务接管或飞控动作完成 |

`source_fix_3d` 仅记录 HIL_GPS fix_type >= 3，原始 fix_type/eph/epv/satellites 仍全部保留；它不是定位就绪或任务接管信号。拒绝记录即使保留源 3D fix 也没有拟输出。中断时源质量与计划状态可同时观察。

`reset(new_epoch)` 要求从未使用的 epoch，清除旧计划和所有样本游标。旧 epoch 留在拒绝名单，旧计划不能复用；新 epoch 必须显式重新安排计划。控制器实例固定 run/vehicle，另一个 run 使用新实例。该 API 不证明外部 run/epoch 身份来自真实运行，未来入口仍须绑定权威会话。

## 离线验证

在仓库根执行，Python 3.13.11、标准库 unittest：

```powershell
python -m unittest validation.test_gnss_event -v
```

结果：**10 tests，OK，0.003 s**。覆盖 199/200/399/400/401 精确边界、固定输入逐字段重复相等、原始时间/质量/坐标保留、无效 fix 与抑制区别、年龄预算及旧源时间包装、重复/倒序/foreign/future 拒绝且不污染游标、中断包恢复时重放拒绝、新 epoch 清除和显式新计划、计划重复/过期拒绝、格式和数值范围非法输入。全部为手工构造固定样本，没有真实传感器或飞控结果。tick 预算在测试中固定 100；实际试验预算仍须提前声明并冻结。

## 实读 PX4 接缝

`Simulator/wksim_core/px4_mavlink.py:29` 的 `gps_arguments` 从模型 `state[90:120]` 提取完整 HIL_GPS 参数；`:75` 在 `model.ticks % 100 == 0` 时调用 `protocol.hil_gps_send`。GPS 输入可在这个真实发包边界交给本控制器，IMU 仍照常发送。现有重复 actuator 分支会再次调用 `send_sensors`，集成时需要正确处理 GPS 重复拒绝，同时保留现有 IMU 重发语义。本次没有改动/接入该路径。

本模块决定的是 **拟输出**，不是“实际发包”。接入时必须另记调用 `hil_gps_send` 的成功/异常及真实原包、run/epoch/tick，不能把 `outbound_gps` 非空当作网络发送成功；还须核验实际模型 GPS 源时钟符合上述合同。

## ArduPilot 原生传感器路径证据

仅通过 WSL 读取现有 `/root/wksim-ap-clock-stop-OXQqdR/src`，没有创建 checkout 或启动固件。`git rev-parse HEAD` 为 `1511f27194f1dcc3728270883047bdf022b3fd53`。`git status` 与 `git diff` 显示 `SIM_JSON.cpp/.h` 含已有绝对微秒时钟量化及等待时退出检查补丁；不是 pristine upstream。其余下列 GPS/状态源码实读未修改。

| 实读文件及行 | 行为 |
| --- | --- |
| `Simulator/wksim_core/ap_json.py:39` | 仅发送 timestamp、IMU、position、quaternion、velocity，没有独立 GPS 字段 |
| `libraries/SITL/SIM_JSON.h:128` 附近 keytable；`SIM_JSON.cpp:398–418,477` | JSON position/velocity 被作为模型状态读取，位置转换后 `update_position()`；不是 GPS 专用输入 |
| `libraries/AP_HAL_SITL/SITL_State.cpp:226–230`；`libraries/SITL/SIM_Aircraft.cpp:373–398` | 更新模型后 `fill_fdm(_sitl->state)`，位置/速度成为 FDM 真值 |
| `libraries/AP_HAL_SITL/SITL_State_common.cpp:464–467` | 遍历已存在 GPS 实例，调用 `gps[i]->update()` |
| `libraries/SITL/SIM_GPS.cpp:436–567` | 从 `_sitl->state` 读取真值；按配置 HZ 调度；添加误差/天线偏置；生成 `have_lock`、准确度与 timestamp；`interpolate_data` 引入延迟；最后 `backend->publish(&d)` |
| `libraries/SITL/SIM_GPS_UBLOX.cpp:206–240,263–266` | 将原生数据转换成 UBX 定位/质量消息，`have_lock=false` 导致 fix_type=0 / satellites=3，仍生成报文 |
| `libraries/SITL/SIM_GPS.cpp:210–239` | `write_to_autopilot` 是实际串行 GNSS 输出边界；instance=1（第二路）在 disabled 时停止写出，第一路不是同一行为；BYTELOS 控制逐字节损失 |

这证实 **删除 JSON position 会改变/破坏模型真值输入，不能实现独立 GNSS 故障**。同样，第一路 `SIM_GPS1_ENABLE=0` 生成无 fix 数据，与“停止新 GPS”不同，不能混为一个事件。源码显示 `BYTELOS=100` 可在串行写出路径丢弃字节，但异步参数修改本身不能证明边界精确落在权威 tick；本次没有执行该参数方案。

诚实的后续 AP 接入点是 `GPS::update()` 中传感器生成/发布前的带原始 `GPS_Data` 决策，以及 `GPS::write_to_autopilot` 的实际写出结果。要让计划精确对齐 wksim run/epoch/tick，需要给原生 AP 侧提供并校验权威身份和 tick，同时记录传感器延迟后的来源时间及输出结果；当前 JSON 合同没有这个入口。本次不承诺无需固件候选修改即可完成。

另一个不可混淆的时间细节：`SIM_GPS.cpp:339–350` 的 `gps_time()` 使用仿真时间生成 GPS 周/TOW，并按 200 ms 网格处理；UBX 发布侧用该 TOW，不能把 UBX 新报文时间自动当成延迟前 GPS 真值采集时间。接入应分别保存 `GPS_Data.timestamp_ms`、原始质量、权威 tick 及实际 UBX 时间，而不是套用本离线 HIL_GPS 微秒合同。

实读文件 SHA-256（现有源码，不复制厂商源）：

```text
8dfcd44f9bb12da648825bff10ce2dabe33c780ec9a5b8d84a60e25e7f9e1f68  libraries/SITL/SIM_JSON.cpp
096df38337a1a19bc5e50fa7efc327c2bd5df6ae88325b5a56dfb21e6361edc1  libraries/SITL/SIM_JSON.h
e692b93506fe1c33757f15167a0a66387f853252781376dc7a71ace5dd814d26  libraries/SITL/SIM_GPS.cpp
a12ddb2163f422040c26cee273c605c242a8591ca55207493a01288ad29dd6e7  libraries/SITL/SIM_GPS_UBLOX.cpp
02a147c1f03dfdf9a347e700dfee0531ede02d9d71296033ed5cdda7ad53c060  libraries/SITL/SIM_Aircraft.cpp
9ddebef1b8ed99f4e1b349ddeddb784246dd0fb2466e03615c1e8b5ce2b90d43  libraries/AP_HAL_SITL/SITL_State.cpp
57db98fffe988936cd4e8393abc5146bb80fcf6f80b634bb076aed9e33464a2a  libraries/AP_HAL_SITL/SITL_State_common.cpp
```

发现路径：仓库已知文件直接读取；外部 AP 源不在 wksim 索引覆盖内，按原生文件直接定位并实读。没有依赖改后仓库结构的图查询，也未刷新全库索引。

## 尚未完成的 #45 验收

尚无实际 HIL_GPS/AP 原生链注入、逐包真实传感器/状态/真值关联、真实 GNSS 中断飞行、任务撤销、飞控动作、恢复后显式接管证据。该包只完成独立事件逻辑及 AP 源码接缝核查，**不能关闭 #45，也不证明物理数值精度通过**。实际集成和受控运行由主代理串行安排。
