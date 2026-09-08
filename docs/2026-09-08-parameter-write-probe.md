# #43 候选参数写 / 独立回读 / 恢复 probe

2026-09-08。仅离线实现与验证，未启动 SITL、UE、MATLAB，未真实写参数或重启。主代理已核验本代理实际 JSONL 的模型 gpt-6-astra、effort low。复用 `ReadProbe` 的真实 ground_state / check_current 权限与 `runtime.run` 正式运行器；参数客户端关闭后直接调用 `Task.execute()` 标准起降，不再次运行只读 probe。

## 写合同与存储精度

首次真实写入前，将此前未实写的候选合同修订为 AP `WP_SPD` [3,10] m/s、0.1 步，以便原样恢复已读到的默认 10.0；PX4 `MPC_XY_CRUISE` [3,5] m/s、整数步不变。这是离线候选修订，不宣称硬件批准、安全范围验收或默认产品准入扩大。先前两份接缝/协议报告中的 AP [3,5] 是历史草案。

`expected` 检查严格等于请求经 IEEE float32 量化再拓宽的值，不使用绝对/相对浮点容差。无 expected 的 GET 仍忠实返回有限原值。恢复请求通过枚举允许网格，要求原读数本身可精确表示为 float32，且其 float32 bits 与某一允许请求一致；原值不能无损恢复则在任何 SET 前拒绝。保留 original_value 与 restore_request_value 两者，不对任意原状态四舍五入。

## 实际流程与失败边界

等待当前 run / epoch / native_generation 的新鲜 disarmed、物理地面、无活动 Task 状态；读取原值、预验证恢复请求、SET 4.0、新发独立 GET 确认、SET 原值、新发独立 GET 确认。每次实际发送前重新核验真实 ground_state；同步串行运行，每次仅一个在途操作、10 秒响应超时、无重试。未知 SET/GET 结果、状态失效或任何异常都停止序列，不在 finally 自动补写，也不继续起飞；正式运行器负责资源收尾。`pending_restore` 保存待处理状态，既可能尚未恢复，也可能恢复已发送而结果未知，不能将它误解为确定当前值。

AP 持有两个真实 `/ap/get_parameters` / `/ap/set_parameters` 客户端，分别核验实际服务图的固定类型和名字，每项请求绑定真实 future，超时取消，最后销毁两个客户端。SET successful/reason 仅为原生受理结果，仍需独立 GET。CDR 原始请求/响应及 SHA256 是真实对象序列化，不冒充网络抓包。

PX4 使用独立固定 `127.0.0.1:14661` UDP socket、peer `127.0.0.1:18591`，source 245/190、target 22/1；先核验未解锁 PX4 quadrotor HEARTBEAT。每次发送前有界排空并重置 parser，参数响应核验 peer、sysid/component、名字、REAL32 及当前上下文。PARAM_SET 后匹配 PARAM_VALUE 只记 observed，另发 PARAM_REQUEST_READ 核验。协议无原生 request_id，不能提供强因果关联，不能冒充 COMMAND_ACK、持久化介质落盘、重启持久性或飞行控制效果。

`parameter-write.json` 与 `result.json.task.parameter_write` 记录固定合同、源哈希、context/epoch、阶段、原值/请求/回复/恢复值、CDR 或原始 UDP 及 SHA256、地面证据、零重启和失败。`parameter_writes` 是保守的尝试计数（发送前持久化，因此也涵盖临发送检查或传输异常），各操作结果区分 unknown/native_accepted/native_rejected/observed。完整成功仍须正式 result.status=pass、物理门槛和清理通过；单独 write_read_restore_pass 不代表正式运行通过。

## 调用与离线验证

必须显式 `--run-id` 和不存在的新 `--output-root`。配置复用只读 probe 的校验，拒绝 joint、mission、display/telemetry/GCS、restart/promotion 扩展。wrapper 创建独立 net/ipc/mount namespace 与私有 `/dev/shm`，runtime 继续拥有私有 /tmp、预约、预检和子进程收尾。`--prepared` 继承 profile 原 setup_files 顺序，全部路径通过 bash 位置参数传入。

```sh
bash tools/run-parameter-write-probe.sh CONFIG --run-id UNIQUE --output-root NEW_DIRECTORY
```

本代理仅执行：Ubuntu-22.04 source /opt/ros/humble/setup.bash 后 `python3 -B -m unittest discover -s validation -p test_wksim_parameter_protocol.py -v`：6 tests pass（0.284s）；三个修改/新增 Python 文件 AST pass；wrapper bash -n pass。包含所有 AP 0.1 网格 float32 精确值/微小不匹配、无损恢复拒绝，以及流程在 trial/read-restored unknown 时无自动补写、非网格原值零写入。测试没有创建 ROS 节点、网络 socket 或飞控进程。真实运行必须由主代理串行审查后执行，#43 仍未完成真实参数写与飞控重启验收。
