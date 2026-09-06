# #42 原生遥测基础与本机地面站边界

2026-09-06 JST。**双栈只读遥测、消费者断开/重连、观察进程退出后的正常任务继续已实测；#42仍 OPEN。**
这不是 QGC 实际界面或显式控制权交接的完成证明，不缩减 Full Goal。
本轮没有改变上一轮已保留的 P450 资产、UE5.5显示构建及 Python 远程配置。

## 实际交付

- 正式实验配置新增可选 `telemetry_socket`；私有运行目录、UID/权限、路径别名、跨实验消费 socket冲突均检查。不开主机UDP口，不接触串口/蓝牙/真实硬件。
- 独立只读观察进程从隔离网络中的真实飞控接收原生 MAVLink，向未绑定的 Unix datagram发送原字节包。没有 UDP发送、查询、GCS心跳、模式或解锁命令，没有返回路径。原生 DDS/Prometheus仍是任务控制链。
- 配套固定飞控XML生成器构建 PX4 development / ArduCopter ardupilotmega解析器；产物和完整生成证据均经 SHA256核验。未升级全局 pymavlink或修改原厂资源。
- 无接收端/满队列/断开均丢弃，不重放、不等待；观察进程就绪后退出只记录状态，不中止物理/飞控/Agent/任务。首次启动不可用仍在飞控启动前拒绝。
- [接口与复现说明](native-telemetry.md)、[本机QGC核对](qgc-local-launch.md)、构建/实际验证/独立审计脚本及边界回归已保留。

`observed_*`明确为应用取包墙钟，不是内核到达时间、飞控启动时间或权威仿真时间；未来消费端还需单独做状态新鲜度判定。身份过滤不是加密认证，不宣称任意外部GCS可安全连接。

## 失败、定位与修复

遵循 diagnosing-bugs：先保留红色实测，抽取一条真实PX4报文进行秒级重复失败，再补回归和修复；未用放宽CRC、源身份、起飞预检或任务超时来变绿。

| 尝试目录（位于validation） | PX4 | ArduCopter |
| --- | --- | --- |
| `sitl-telemetry-fyw7dgou` | 三航点正常落地；遥测gate失败，398包拒绝 | 三航点正常落地；遥测gate失败，只有0/49/111/242类消息，缺姿态/全球位置 |
| `sitl-telemetry-j5nt3lem` | 重现同类失败；保留8条原始拒绝样本 | 重现缺状态流；拒绝样本是5条启动控制台文本 |
| `sitl-telemetry-wvfousrd` | 专用解析器后pass，0非法帧 | 原生姿态/位置已出现、0非法帧，但DDS未启动，public_control_ready超时；没有发出起飞请求 |
| `sitl-telemetry-m5mam1zm` | 最终pass | 参数文件顺序修复后最终pass |

1. **方言不匹配。** 实际58字节ESC_INFO290包完整，线缆头部系统22/组件1；已装PyPI pymavlink2.4.49的ardupilotmega/common/development/all均把它解作UNKNOWN_290，返回系统/组件0。专用本地生成解析器恢复语义和CRC验证，原始包回归已先红后绿。PyPI定义来自ArduPilot fork而可能与MAVLink/mavlink不同，这一差别也有[官方说明](https://mavlink.io/en/mavgen_python/)。
2. **流速参数名称变化。** 固定ArduCopter源码 `ArduCopter/Parameters.cpp:590` 的MAV组、`libraries/GCS_MAVLink/GCS.cpp:80` 的第1通道，以及 `GCS_MAVLink_Parameters.cpp:156/166/185`共同组成 `MAV1_POSITION/EXTRA1/EXTRA3`。新增仅遥测启用的10/10/5Hz配置，原历史profile不改写。
3. **动态DDS默认值装载顺序。** `libraries/AP_Param/AP_Param.cpp`的`read_param_defaults_file`逐文件覆盖`done_all_default_params`，动态子树加载只在该标志为false时重读默认值。`AP_DDS_Client::start`在装载后看到enabled为0会正常返回而不建DDS线程。新增遥测文件放在最后时掩盖前面尚未解析的DDS参数；只把它移到DDS文件前，保持DDS最后，真实双栈恢复。固定飞控二进制未修改；回归防止再次把新文件追加到DDS之后。

生成器还保留两次准备失败：首次严格字节检查发现本机XML为CRLF（经逐文件与git blob核对，仅换行不同），后允许且明确记录CRLF/LF差别；第二次使用全局旧生成器时ArduCopter新`superseded` XML元素验证失败。最终改用各飞控已固定的配套生成器，**没有关闭XML验证**。失败的未完成输出目录保留，不作为可加载产物。

临时`[DEBUG-tlm-raw]`采样已从源码移除；原日志留在失败证据中。无外部固件修复、全局pip升级、参数健康检查降低或自动控制权抢回。

## 真实最终结果与独立审计

共同入口：`tools/validate_sitl_telemetry.py --stack both`，底层使用未替换的 `tools/run-wksim.sh`正式入口、真实已固定飞控、已安装Prometheus session_v1控制和原三航点任务。验证器只收包、断开自己的接收端，以及终止精确归属的观察子进程；不代发飞控命令。

| 项目 | PX4 | ArduCopter |
| --- | --- | --- |
| run_id | `telemetry-px4-fb46c62b38` | `telemetry-arducopter-472c121c53` |
| 实收原生数据报 | 3298 | 3335 |
| 非法MAVLink / 错误来源 | 0 / 0 | 0 / 0 |
| 非MAVLink启动文本（拒绝） | 0 | 5 |
| 丢弃计数 | 2548 | 522 |
| 消费端缺席时权威时间推进 | 10.82→16.84s | 46.08→52.12s |
| 停止观察器时 / 最终权威时间 | 16.90→42.70s | 52.24→75.94s |
| 正式任务结局 | 三航点、正常降落、disarmed | 三航点、正常降落、disarmed |

消费者在独立物理真值高度>2m时关闭，2墙钟秒后新建接收socket；收到新序号包后终止观察器。心跳、有限姿态、全球位置/推进的原生boot时间均从实际字节再解析核对；没有给原生报文重新编码。两实验仍各自计时，**不是联合场景共享时间验收**。

最终证据：`validation/sitl-telemetry-m5mam1zm/`。
独立审计：`validation/telemetry-integration-20260906/audit.json`，SHA256
`758a5f5bff24f87d923b763fcc6721cfa37fb328eb0ae15b8e39001bbc96694e`。
审计覆盖全部8次尝试、40个本轮Linux进程组，无残留，接收socket均清理；旧失败不重判为pass。
最终双栈实际源文件哈希与当前文件逐项一致，真实飞控二进制哈希仍匹配准入基线。
原飞控PID828/start_ticks19268/命令行不变；用户UE编辑器PID35256/创建时间02:20:00.42221+09:00/项目命令行不变，未启动QGC或本轮UE。

当前解析器完整生成清单：`/root/wksim-telemetry-dialects-20260906-3/manifest.json`；活动引用
`Simulator/wksim_runtime/telemetry-dialects.json`。
PX4解析器SHA256 `71d04ba008488ece917fbed9e98fae690213d8d4e235161f934b19fe3b4270dd`，
AP解析器SHA256 `5ad06d4f2a92f3958aef0948c2cc9b38e38ab985910703ed50b44e657ad24b02`。
输入覆盖各自4/9个XML和23个生成器输入文件，源码和生成器均有submodule commit核验。

## 回归、并行与记忆

- 最终WSL：194项session/模型/协议/任务等检查 + 10项带真实固定资源的legacy preflight检查，无跳过。日志 `validation/session-product-checks-ksQ1g1lz/`。其中14项遥测协议/真实Unix与UDP socket边界在私有net namespace内运行，不冒充真实飞行。
- Windows控制台88项回归另测；最终日志 `validation/telemetry-integration-20260906/windows-console-final.log`。UE和浏览器UI没有在本轮重新验收。
- 两个互斥写入子代理均显式且实读turn_context为gpt-6-astra/low：Sartre只交付QGC只读核对文档；Tesla只交付独立遥测边界测试。主代理实现、诊断、集成、增加真实失败回归并执行全部真实SITL/审计。两代理已关闭，无嵌套委派。
- Codebase Memory原失败在本轮同命令重试即恢复，未查明此前瞬态失败根因，不声称某项配置修复生效。代码完成后再次刷新成功：**2026-09-05 19:06:54 UTC，83,249节点 / 191,465边**，artifact19:07:05 UTC。精确查询、覆盖与图的启发式误连限制详见[记忆说明](codebase-memory.md)。

## 未完成边界

本机QGC.exe真实release/source对应及隔离settings启动方式未验证；参考源码UDP监听全部IPv4且动态学习其他peer。没有启动它、写用户settings、打开主机wildcard socket或绕过浏览器管理策略。

本轮[进度已发布并读回#42仍OPEN](https://github.com/unununnnn/wksim/issues/42#issuecomment-5554161577)。实际代理配置、用户编辑器身份和工单读回归档于`validation/telemetry-integration-20260906/coordination.json`。没有推送含其他用户改动的工作区。

当前只读出口不能传GCS命令。`Task`收到control_revoked仍走现有失败/隔离实验清理，尚未实现“物理和飞控保持运行、任务停止输出、等待新显式恢复请求”的交接生命周期。QGC实际查看/交接/恢复都未完成，#42不能关闭。#18实际浏览器流程、UE冷启动稳定性，以及既有Full/HITL范围也继续开放。父Wayfinder#1和完整规格#10未改写或关闭。
