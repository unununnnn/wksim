# #43 最小参数原生协议模块（离线验证）

新增 `Simulator/wksim_runtime/parameter_protocol.py` 和 `validation/test_wksim_parameter_protocol.py`。本切片没有启动 SITL、UE、MATLAB、ROS 节点或硬件，没有创建网络口，没有更改遥测观察器、配置或固定清单；不构成 #43 实际参数写入、持久化或飞控重启验收。

## 接口和责任

`ParameterContext(operation_id, run_id, control_epoch, native_generation)` 固定操作身份，其中 control_epoch 为现有 session 的 32 位小写 UUID hex 字符串，native_generation 为非负整数；`GroundState(context, observed_at, disarmed, grounded, active_task)` 由运行器的 `state_provider` 每次提供。`observed_at` 是原生状态和物理地面证据中最旧必需样本的单调时钟时间。默认新鲜度上限 0.5 秒，可由运行器收紧或按实测设定。编码和回复处理都会再次检查状态；任何当前状态失败或时钟无效/回退会永久使该协议实例失效，即便状态后来恢复也不能继续写。

运行器必须从其拥有的当前载具读取这些状态，不能信任 UI 自报布尔值。模块不证明进程所有权或原生身份发现，也不阻止其他客户端并发写入。实际发送前须再次调用 `check_current()`，并在运行器锁/事件循环边界内保证状态核验到发送之间不会穿插任务接管。每次一项、一个在途操作，发送队列和超时由运行器负责。

- AP：`ap_get_request()`、`ap_set_request(value)` 返回真实 `rcl_interfaces` 请求；`ap_set_result(response)` 返回原生 `(successful, reason)`，没有把 `successful=True` 当作应用或持久化完成；`ap_get_value(response, expected=...)` 检查单项、DOUBLE、NOT_SET 和值。
- PX4：构造器注入已核验 dialect module、固定 peer、明确非广播 target_system/target_component；`px4_read_message()` 和 `px4_set_message(value)` 返回真实 MAVLink 消息对象。`px4_value(message, peer=..., context=..., expected=...)` 校验实际解码消息类、来源 sysid/component、peer、名称、REAL32、值及本地接收上下文。
- `validate_value(stack, name, value)` 仅允许 `arducopter/WP_SPD` 的 0.1 步或 `px4/MPC_XY_CRUISE` 的整数步，均为 [3, 5] m/s，拒绝 bool、非有限值、未知名称、错误范围。写请求不会静默四舍五入。AP 原生读数可保留准确 float32 存储值，例如 3.0999999046325684；若恢复该原值，应先显式映射到批准的 3.1 请求并保存两者，不能把不合步进值原样作为写请求。

AP ROS response 不携带参数名，本模块依赖运行器把同一 context 的单项请求与对应服务 future 绑定，并在超时后丢弃迟到 future。PX4 `PARAM_VALUE` 没有原生 request_id，也不是 `COMMAND_ACK`；其 context 是接收运输层的本地元数据，不能给旧缓冲包重新贴新 epoch。重复同值包无法在该协议中区分，测试明确保留这个限制。运行器须发送前排空、写后新发独立读请求、新 generation 关闭旧 transport；未知名/无回复只能报告 unknown/timeout，不能虚构原生拒绝。模块不实现重试或任何时序状态机。

## 源核对和验证

直接读取了固定 AP `AP_DDS_Client.cpp:1111–1302`（Set/Get Parameters）与 `AC_WPNav.cpp:49–56`，固定 PX4 `mavlink_parameters.cpp:98–208,475` 与 `multicopter_autonomous_params.c:34–46`。源目录/固定摘要见 [原生接缝调查](2026-09-08-parameter-native-seam.md)。本次没有结构图查询，也没有刷新索引。

在本机 Ubuntu-22.04 的 ROS Humble 环境运行：

```sh
source /opt/ros/humble/setup.bash
cd /mnt/c/Users/PC/Documents/odid编译/wksim
python3 -m unittest discover -s validation -p test_wksim_parameter_protocol.py -v
```

结果：4 tests，全部通过，最后运行 0.190 秒。真实 ROS CDR roundtrip 覆盖 GET/SET 请求、SET 回复与 DOUBLE 读回；拒绝空/多项结果、NOT_SET、错误类型和不匹配值。真实 MAVLink wire encode/decode 使用已有 `load_dialect('px4')` 的固定清单与 SHA256 验证，覆盖 READ index=-1、SET REAL32、错误 peer/sysid/component/name/type/value、旧 epoch/generation、COMMAND_ACK 冒充回复。状态测试覆盖不同 operation/run/epoch/generation、过期/未来时间、armed、非地面、活动任务及失效后恢复状态仍禁止写入。

主代理整合复核后补充：GET 忠实返回任何有限原生 DOUBLE/REAL32 存储值，包括 AP 默认可能出现的 10.0 或非写网格值；不会用写范围伪装 GET 失败。只有写请求及显式 expected 校验应用 [3,5] 和步进规则。运行器应在修改前决定是否具备恢复原值的能力，原值不在批准写范围时不得进入修改。回归增加 AP/PX4 范围外和非网格存储值读取、时钟 bool/字符串/None/NaN/Inf 拒绝及时间回退后永久失效，仍为 4 个测试方法。

这些是协议 fixture，未冒充飞控在线回复或实飞证据。仍需主代理把协议接入持有资源的运行器，完成真实服务发现、读旧值→写→独立回读→恢复，以及受监督原生飞控重启后的新身份/定位/持久化验收。
