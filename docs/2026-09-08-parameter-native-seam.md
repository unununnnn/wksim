# #43 参数原生接缝（只读调查，未验收）

2026-09-08。已读本项目 AGENTS.md、CONTEXT.md、docs/plan/goal-objective.md 和 GitHub #43。没有启动 SITL、UE、MATLAB 或硬件，没有修改产品或发布 Issue。主代理核验本代理实际会话为 gpt-6-astra / low 后开始。Codebase Memory index_status 为 ready、50,515 nodes / 163,780 edges；没有重复索引或依据旧图推断新结构。以下为已知路径直接源读取；外部飞控源不属于该图。

## 最小实现建议

先交付单个隔离独立实验的地面参数读写，随后同一实验的受监督飞控重启与重新发现；联合场景恢复另需同步物理会话，不能直接复用单机重启。仅允许运行器持有的载具、进程与参数目录，disarmed + landed + 新鲜原生状态 + 物理地面证据且无活动任务时写入。每次一个参数、一个在途操作，先读旧值，写入，独立回读，记录实际浮点值；未准入名字、NaN/Inf、错误类型、范围外、旧 epoch、未知原生身份均拒绝。

| 栈 | 原生名/类型 | 固定源码范围及单位 | 产品首批建议 | 重启及作用边界 |
| --- | --- | --- | --- | --- |
| ArduCopter | WP_SPD / float，经 DDS DOUBLE | 0.10–20.00 m/s，步进0.10 | 3.0–5.0 m/s；试验4.0，最后恢复原值 | 参数可运行中被导航代码检查；不是重启必需参数。地面写仅确认存储回读，不证明飞行速度 |
| PX4 | MPC_XY_CRUISE / REAL32 | 3–20 m/s，增量1，默认5 | 3.0–5.0 m/s，整数步；试验4.0，最后恢复原值 | 参数元数据无 reboot_required；FlightModeManager处理parameter_update。作用于自主模式，不保证wksim offboard任务速度改变 |

注意 AP 当前名称已经迁移：ArduCopter/Parameters.cpp:367–369 注册 WP_；libraries/AC_WPNav/AC_WPNav.cpp:49–56 注册 SPD，:150–162把旧厘米单位转换到米，:685–693检查更新。不能沿用旧 WPNAV_SPEED 或向当前值额外乘100。上述产品范围是拟议收窄范围，不是飞行安全验收结论。

## 真正的协议入口与确认语义

AP 已有原生 DDS：libraries/AP_DDS/AP_DDS_Service_Table.h 的 SET_PARAMETERS/GET_PARAMETERS 使用 rcl_interfaces/srv/SetParameters、GetParameters；请求主题为 rq/ap/set_parametersRequest 与 rq/ap/get_parametersRequest。GET 的 service_name 字符串是单数 get_parameterService，但请求/响应主题是复数，实际 ROS 客户端服务发现须实测，不能根据字符串猜调用成功。AP_DDS_config.h:160–161默认开启 AP_DDS_PARAMETER_SERVER_ENABLED；本次未证明实际二进制服务可发现。

AP_DDS_Client.cpp:1111–1302：最多8项；只接受整数/双精度输入，转float；拒绝未知参数、非有限数和只读/内部参数；调用set_and_save_by_name_ifchanged后给successful=true、reason=Parameter accepted。这个结果不是消费者已应用或持久化介质已落盘证明，也没有检查产品范围/armed条件。GET 返回位置对应的类型和值，未知值为PARAMETER_NOT_SET。反序列化失败/数量超限可没有回复，必须有超时。首批固定一项规避批量部分成功，SET成功后另发GET核对类型和值。

PX4 固定 src/modules/uxrce_dds_client/dds_topics.yaml 全文没有参数读写主题；现成vehicle_command/ack不能当成参数ACK。现有 src/modules/mavlink/mavlink_parameters.cpp:98–138明确支持PARAM_SET，检查目标system/component和类型，param_set后send_param；:172–208支持按名字PARAM_REQUEST_READ（index=-1）；:475起send_param使用param_get编码PARAM_VALUE。没有独立请求ID，没有COMMAND_ACK，未知名字或类型错主要日志报错/不回值，必须将超时报为unknown/timeout，不能伪造native_rejected。

因此 PX4 有两条显式选择：新增独立、受运行器管理的 MAVLink 参数端口/客户端，仍让任务控制走DDS；或实现并维护飞控原生 DDS 参数服务补丁。前者工程量较小，但必须明确作为新增参数协议而非“现有DDS已支持”。不得借诊断观察器制造控制包：当前 Simulator/wksim_runtime/telemetry.py 支持可选GCS字节桥，但其文档和实现边界是原始GCS字节转发，不构造原生命令。参数客户端需独立所有权、端口、日志与能力开关，并处理GCS并发写入（首批应互斥）。

PX4 PARAM_VALUE的身份+名字+类型+值匹配仅能证明本epoch内观察到目标存储值，不是强请求关联。固定peer、单在途、发送前排空、发送后独立读回与新epoch关闭旧socket可减小混淆；协议本身不能证明某个相同值回包必然对应某次写。不要把本地request_id冒充原生ACK字段。若要求严格因果请求ID，应选择新增DDS服务补丁。

## 重启切片与文件范围

现有 Simulator/wksim_runtime/runtime.py:212–229 的restart_control只重启control，明确不重启physics和FC；不能以此满足#43飞控重启。建议新增 parameters.py（白名单/状态机），parameter_native.py（AP服务与显式PX4参数协议），参数协议测试；runtime.py/config.py/isolation.py负责可选能力、端口、持有的FC进程和私有参数目录。task.py及控制session接缝由主代理独占审查：重启前撤销控制许可、使旧请求失效，终止在途参数操作；重启后必须新发现、新鲜定位、显式接管，不恢复旧任务。UI/CLI只在这些后端状态完成后接入。共享消息或飞控补丁不能与其他写入者并改。

重启先停止自身FC进程并确认退出，保留自身参数存储目录，清理其通信对象后重建；不能删存储导致“恢复默认”却声称持久化。AP/PX4物理握手和boot时间重置对现有物理worker的影响仍需主代理实现前读取并验证。本调查不宣称已有安全FC重启实现。

## 验证顺序

1. 无SITL协议测试：白名单/类型/范围/epoch/地面拒绝；AP部分成功与NOT_SET/超时；PX4错误peer/sysid/component、旧包、错误类型、超时、值不匹配、重复包；读取状态不等于控制效果。
2. 主代理预约隔离资源后：保存源SHA、二进制身份、启动命令和参数目录；双栈分别真实服务/协议发现，读原值→写4.0→原生回复→独立回读；恢复原值。AP服务未编入或发现失败即失败，不降级伪造。
3. 正式持有进程重启：写4.0并回读；撤销epoch；停/启自己的FC；新发现后回读4.0验证持久化，重新定位且等待显式接管；发送旧epoch命令确认拒绝且无原生发布；恢复原值并再次核实。
4. 记录失败/超时和未知状态，停止时不重试写操作。若需要声称“飞行控制已生效”，另设计自主模式行为实验，不能用地面GET或现有offboard轨迹替代。

## 固定源身份

AP 根 /root/wksim-ap-clock-stop-OXQqdR/src，HEAD 1511f27194f1dcc3728270883047bdf022b3fd53；PX4 根 /root/wksim-px4-state-ONa1Kw/src，HEAD d6f12ad1c4f70ad3230afd7d86e971421e02fef4。两树均有既有修改，以下SHA256固定实际读取源，不能只以HEAD声称干净上游。

| 实际源（相对相应根） | SHA256 |
| --- | --- |
| AP libraries/AP_DDS/AP_DDS_Client.cpp | e41fd119b40aac34d357b41f9588e04f5ea95b9a88ee0175968ec5341b6401c1 |
| AP libraries/AP_DDS/AP_DDS_Service_Table.h | 90441f1e02f7a29f28788a735e720d879ca23a8dfc4635aadb9eab01e7176e3a |
| AP libraries/AP_DDS/AP_DDS_config.h | 53d8a5c54901d47ee9e6ad00eddb0f18574b7334cbcbfba3d22e56b171a676fc |
| AP libraries/AC_WPNav/AC_WPNav.cpp | a3806e409508b78e4e280b4a0d45909198333e48b855ecfce296b0c9f95c390a |
| AP ArduCopter/Parameters.cpp | 4a4248b8395b16dc17551819206add0dc38c1badab585099c3b5374288458fe0 |
| PX4 src/modules/mavlink/mavlink_parameters.cpp | 1f3c0d1cc1195564ad5b8ec0f1d742b47496273ca848cfee855c8a66dc07eb53 |
| PX4 src/modules/uxrce_dds_client/dds_topics.yaml | 7e9c730d45b22af92acfebbb81cb5de4e4a69ac0ca46b012b71ed8fa5c89cbc0 |
| PX4 src/modules/mc_pos_control/multicopter_autonomous_params.c | a3ef2f0d3d29fe85a4d8270bc5a4410f29ed6451f78e165ddf3bab291804adb7 |

PX4参数元数据在multicopter_autonomous_params.c:34–46；FlightModeManager.cpp:90–94读取parameter_update并updateParams，FlightTaskAuto.cpp:372读取MPC_XY_CRUISE。未运行编译/协议/重启测试；#43仍未满足验收。
