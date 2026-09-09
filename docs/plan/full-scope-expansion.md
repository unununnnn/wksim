# Full范围扩展账本

冻结范围记录于2026-09-05；当前状态复核于2026-09-09（#55）。**38张初始草案、17个剩余父票均不是完整Full功能总数。** 下列原始表格保留冻结时的文字，历史“尚未实现”等不代表当前状态；当前判定与后继以文末复核表及requirement-coverage.md为准。

依据是已冻结的公开手册及本地盘点，不能把今天网页的后续变化自动纳入，也不能把文档版本当成本机Full程序二进制或授权已经确认。冻结手册SHA256为 `29da779803edaa15c8a751500e96a88243dfc6b71ed6c66e462bf228956143c3`。

## 仿真模式逐项映射

下列名称与ID来自冻结手册。每种模式只验证实际适用的组合，不承诺12种仿真与7种通信的全部笛卡尔积。

| ID | 名称 | 对应用户流程 | 当前证据与后续门槛 |
| --- | --- | --- | --- |
| 0 | PX4_HITL | 串口连接实体PX4并执行硬件在环 | 本阶段未验收；先取得硬件、串口、固件、移除动力风险的测试条件及明确授权，再单独拆票 |
| 1 | PX4_SITL | 通过TCP连接标准PX4软件在环 | 当前自主物理与原生任务链已部分证明；正式产品入口及参考模式操作映射仍需验收 |
| 2 | PX4_SITL_RFLY | 通过UDP连接Rfly定制PX4软件在环 | 需锁定本地定制固件、协议和使用条件；不能把标准PX4通过记为本模式通过 |
| 3 | Simulink&DLL_SIL | 无飞控的纯模型运行 | 自主模型有局部构建证据；完整选择、初始化、运行、重置及导出流程另行验收，不要求日常运行必须启动Simulink |
| 4 | PX4_HITL_NET | 网络连接实体PX4硬件在环 | 硬件/网络和安全授权先决；手册免费版标签不一致不影响它属于Full范围 |
| 5 | EXT_HITL_COM | MAVLink串口接外部飞控 | 先明确一个可核验外部飞控和接口，不将“外部”解释为任意厂商任意设备 |
| 6 | EXT_SIM_NET | 连接外部仿真系统 | 先明确一个参考系统、物理权威、时钟和失败语义，再做单系统端到端票 |
| 7 | APM_SITL_NET | 连接ArduPilot软件在环 | 当前ArduCopter物理/任务候选有证据；不泛化为所有ArduPilot机型或原厂模式全兼容 |
| 8 | PX4_SIH_COM | SIH串口流程 | 需实体设备与对应固件；物理位于飞控内部，必须重新映射显示/任务时间而非再启动第二物理核心 |
| 9 | PX4_SIH_NET | SIH网络流程 | 与串口分开验证连接、状态、停止和重连；保留硬件/固件条件 |
| 10 | PX4_SIH_SITL | 软件飞控内运行SIH | 先核对固定PX4的该模式及接口，验证唯一物理权威和时间映射；当前外部物理SITL不覆盖它 |
| 11 | PX4_SIH_FLY | SIH RFly流程 | 先核对RFly固件、模型、接口和授权，不按名称猜测可由标准固件代替 |

每个模式升为实施票时必须描述：选择/配置→连接→真实输入输出→状态与物理权威→停止→重连→结果。缺设备的项目是阻塞，不是通过；硬件模式不会因为首期SITL结束而被删除。

## 通信模式逐项映射

| ID | 名称 | 最小可观测契约 | 下一步需锁定的内容 |
| --- | --- | --- | --- |
| 0 | UDP_Full | 参考完整UDP输出与消费，手册列168字节SOut2Simulator | 精确字段、布局、字节序、速率、目标地址及完整模式控制/反馈行为；对照本地SDK与实际观测 |
| 1 | UDP_Simple | 参考简化带时间UDP输出，手册列112字节SOut2SimulatorSimpleTime | 字段和时间语义、简化丢失的量、非法报文拒绝及原SDK互操作 |
| 2 | Mavlink_Full | QGC与SDK所需完整MAVLink交互 | 消息集合、身份、控制权、参数和状态映射；已有QGC切片不自动覆盖全部功能 |
| 3 | Mavlink_Simple | 简化MAVLink交互 | 相对Full的准确删减与频率；不能只复用Full实现并改模式标签 |
| 4 | Mavlink_NoSend | 只接收，不主动发送 | 被动接收的副作用、是否允许响应及其参考证据；抓包证明发送约束 |
| 5 | Mavlink_NoGPS | 无GPS场景下的参考接口行为 | 传感器/定位与控制条件；GNSS故障切片不自动等价于此模式 |
| 6 | Mavlink_Vision | 视觉定位数据输出 | 坐标、协方差、采样时刻、消息与估计器接入；真实相机图像接口不能代替本模式 |

DDS是任务/模块组织与飞控原生接入选择，不删除上述公开互操作能力。协议定义核对后，每种模式至少一张可独立运行、正负报文与行为均可验证的纵向票；扩展命令按真实影响再拆，不把整个协议族放进一张无限范围票。

## 机型与模型材料

| 功能行 | 当前拆分归属或缺口 | 升为实施票的条件 |
| --- | --- | --- |
| 四旋翼 | 固定数值对照、参数运行切片已列，尚未实现这些新增票 | 固定模型/参数/预算和来源 |
| 六旋翼 | 单独端到端切片已列 | 正确动力、惯量、电机/旋翼映射及适用飞控 |
| 三旋翼 | 未被四旋翼或六旋翼票覆盖 | 单独构型、驱动/舵机、模型与测试定义 |
| 三轴六旋翼 | 未被平面六旋翼覆盖 | 共轴影响、旋向、电机分配与具体参数 |
| 四轴八旋翼 | 未覆盖 | 独立构型、动力与混控校验 |
| 八旋翼 | 未覆盖 | 独立构型与适用飞控校验 |
| 固定翼、复合翼 | 未覆盖 | 各自模型来源、控制栈/执行器、运动工况；不能强行要求由ArduCopter控制固定翼 |
| CarAckerman | 未覆盖 | 转向/驱动接口、轨迹与地形工况 |
| CarR1Diff | 未覆盖 | 差速映射及对应运动/重置工况 |
| CarNoCtrl | 未覆盖 | 无控输入和模型观测，不依赖飞控也可验收 |
| Trailer | 未覆盖 | 牵引/关节与场景耦合工况 |
| MulticopterNoCtrl | 未覆盖 | 无控模型输入、运动与复位定义 |
| MulticopterNOpx4 | 未覆盖 | 无飞控模型接口与适用控制方式，不按名称猜测实现 |
| CopterSILVelCtrl | 未覆盖 | 纯模型速度控制工作流，不等同于真实FC速度票 |
| MultSILSwarm | 未覆盖 | SIL集群场景、身份及共享时间映射，不能由双FC联合场景自动代验 |
| Exp1_MinModelTemp、Exp2_MaxModelTemp | 生成模型切片只验证选定样本 | 两个模板各自I/O、生成、构建、导入与运行流程；缺可编辑材料时明确阻塞 |

每个新增构型或模型应单独完成“选择/编辑→导入/构建→运行→正确显示→重置→结果”，不把所有机型堆成一个代理任务。模型库名字只是资源线索，不说明分发许可或二进制兼容已经成立。

## 仍需逐项展开的操作、环境和实验

| 功能域 | 必须保留的行 | 不能误认为已被什么覆盖 |
| --- | --- | --- |
| 模型数据库/组件库 | 品牌组件参数、自定义参数、确认/计算、加入与删除机型、数据库导入导出、备份恢复 | 四旋翼参数表单不是完整数据库；删除只作用于用户明确选择的工作副本，不能改原厂库 |
| 性能计算 | 悬停时间、油门、电流、转速、功率、能效及FlyEval关联的参考流程 | 在线服务存在不保证可访问或公式已公开；本地独立计算与服务集成分开记录 |
| XML/模型元数据 | ModelInfo、HoverInfo、FrameInfo、ClassID及默认值、单位和错误 | 能选一个DLL不等于XML模型配置可用 |
| CLI/NoUI/GUI一致性 | 冻结手册16个启动参数、多值初态、GPS、串口/波特率、通信地址、自动启动、实时/日志选项 | 初期“点启动”仅覆盖一个正常产品路径，不能吞掉参数组合与错误流程 |
| 网络与远程 | UDP广播、指定主机、JSON联机、端口/身份、多实例与分布式场景 | 本机两独立实验隔离和同机场景各自仅覆盖子集；跨主机边界单独验证 |
| 载具与场景资产 | 正确机体、旋翼、场景选择、导入资产、模型ClassID映射 | 当前几何占位四旋翼与城市显示不是最终机型/场景库 |
| 环境反馈 | 地形、碰撞、动态对象/环境变化、过期反馈处理 | 单坡面/单障碍切片只是首例，不代表全部场景交互 |
| 传感器 | 基础传感器标定/噪声/延迟、其余图像/点云能力与所需Prometheus输入 | RGB与深度生成点云不覆盖扫描LiDAR、分割及其他未细化能力 |
| 故障 | 电机卡死/关闭、传感器偏置/冻结/丢失、环境扰动和通信异常的公开范围 | 单电机效率与GNSS中断各只覆盖一种事件 |
| 控制/任务/算法 | RC其他模式、更多规划/感知demo、多机任务与队形、公开实验来源逐项映射 | PID/UDE/NE、单规划器与ArUco只是明确的首批路径，不能代表全部Prometheus算法 |
| 日志与复现 | 源/接收时间、bag与飞控原生日志、完整事件流、回放/重演、容量与缺段策略 | 既有JSONL回看不自动完成全部记录系统或跨平台确定性 |
| 资源自主交付 | 无原版程序/DLL依赖、模型/资产可获得性、构建说明与来源许可 | 本机能编译厂商ZIP不代表可以公开分发其源代码；本地UE staging素材同理 |
| 性能与规模 | 目标载具数、步频、吞吐、CPU/GPU负载、记录容量、时间偏差与恢复窗口 | 单机3倍速或两机验证不证明十机、任意硬件或分布式实时性能 |

## 如何继续拆票

1. 先由“实验能力预检与候选身份核验”维护功能行与可用证据，保留未知/未观测状态。
2. 在对应决策或资源事实明确后，每次将一个机型、模式、协议或操作的端到端路径升为详细票据，填写真实阻塞与预先验收条件。
3. 不把未定义的外部系统、未授权的硬件或未知数值预算伪装成ready-for-agent的已明确任务。
4. 未能升为票据的行继续阻止完整Goal完成，但不锁住无关的已批准前沿。
5. 完整Full验收必须逐行闭合参考→实现→构建→运行→通过证据；合法且必要的范围变化由用户确认，不能由代理自行删行。

Redis_Full、Redis_Simple及厂商定制Logo服务属于已排除的定制版扩展。wksim自有品牌与界面仍在要求内。对照与资源分析继续限于用户授权本机范围，不绕过许可或外传厂商私有材料。

## 2026-09-09 #55当前覆盖与后继

96行完整复核见 [需求覆盖](requirement-coverage.md) 与 [机器台账](full-followup-tickets.json)。以下48行均保留未闭合的Full义务；evidenced仅认可具体局部证据，blocked/not-implemented不算通过。#23、#24、#48等关闭证据已读，原历史描述不覆盖这些现状。#59数值路线、#60完整验收、#56硬件/资源确认和Hex #65–#69直接复用；新增#122–#164只交付专家合同定义。

| ID | 状态（范围见正文） | 归属父票 / 相关原AC | 剩余缺口 | 后续真实票号 |
| --- | --- | --- | --- | --- |
| SIM-01 | blocked | [#1](https://github.com/unununnnn/wksim/issues/1) / [#1](https://github.com/unununnnn/wksim/issues/1) | 本阶段未验收；先取得硬件、串口、固件、移除动力风险的测试条件及明确授权，再单独拆票；#56承接逐模式硬件/固件/接口及授权确认，现缺该确认。 | [#56](https://github.com/unununnnn/wksim/issues/56) |
| SIM-02 | evidenced | [#1](https://github.com/unununnnn/wksim/issues/1) / [#1](https://github.com/unununnnn/wksim/issues/1)、[#12](https://github.com/unununnnn/wksim/issues/12)、[#48](https://github.com/unununnnn/wksim/issues/48) | 固定PX4独立DDS产品任务已验；冻结PX4_SITL的TCP模式选择、接口、停止重连映射未逐项核验。 | [#122](https://github.com/unununnnn/wksim/issues/122) |
| SIM-03 | not-implemented | [#1](https://github.com/unununnnn/wksim/issues/1) / [#1](https://github.com/unununnnn/wksim/issues/1) | 需锁定本地定制固件、协议和使用条件；不能把标准PX4通过记为本模式通过 | [#123](https://github.com/unununnnn/wksim/issues/123) |
| SIM-04 | not-implemented | [#1](https://github.com/unununnnn/wksim/issues/1) / [#26](https://github.com/unununnnn/wksim/issues/26) | 自主模型有局部构建证据；完整选择、初始化、运行、重置及导出流程另行验收，不要求日常运行必须启动Simulink | [#124](https://github.com/unununnnn/wksim/issues/124) |
| SIM-05 | blocked | [#1](https://github.com/unununnnn/wksim/issues/1) / [#1](https://github.com/unununnnn/wksim/issues/1) | 硬件/网络和安全授权先决；手册免费版标签不一致不影响它属于Full范围；#56承接逐模式硬件/固件/接口及授权确认，现缺该确认。 | [#56](https://github.com/unununnnn/wksim/issues/56) |
| SIM-06 | blocked | [#1](https://github.com/unununnnn/wksim/issues/1) / [#1](https://github.com/unununnnn/wksim/issues/1) | 先明确一个可核验外部飞控和接口，不将“外部”解释为任意厂商任意设备；#56承接逐模式硬件/固件/接口及授权确认，现缺该确认。 | [#56](https://github.com/unununnnn/wksim/issues/56) |
| SIM-07 | not-implemented | [#1](https://github.com/unununnnn/wksim/issues/1) / [#1](https://github.com/unununnnn/wksim/issues/1) | 先明确一个参考系统、物理权威、时钟和失败语义，再做单系统端到端票 | [#125](https://github.com/unununnnn/wksim/issues/125) |
| SIM-08 | evidenced | [#1](https://github.com/unununnnn/wksim/issues/1) / [#1](https://github.com/unununnnn/wksim/issues/1)、[#12](https://github.com/unununnnn/wksim/issues/12)、[#48](https://github.com/unununnnn/wksim/issues/48) | 固定ArduCopter自主物理产品任务已验；APM_SITL_NET参考网络操作/停止重连映射未逐项核验，其他AP机型不能代验。 | [#126](https://github.com/unununnnn/wksim/issues/126) |
| SIM-09 | blocked | [#1](https://github.com/unununnnn/wksim/issues/1) / [#1](https://github.com/unununnnn/wksim/issues/1) | 需实体设备与对应固件；物理位于飞控内部，必须重新映射显示/任务时间而非再启动第二物理核心；#56承接逐模式硬件/固件/接口及授权确认，现缺该确认。 | [#56](https://github.com/unununnnn/wksim/issues/56) |
| SIM-10 | blocked | [#1](https://github.com/unununnnn/wksim/issues/1) / [#1](https://github.com/unununnnn/wksim/issues/1) | 与串口分开验证连接、状态、停止和重连；保留硬件/固件条件；#56承接逐模式硬件/固件/接口及授权确认，现缺该确认。 | [#56](https://github.com/unununnnn/wksim/issues/56) |
| SIM-11 | not-implemented | [#1](https://github.com/unununnnn/wksim/issues/1) / [#1](https://github.com/unununnnn/wksim/issues/1) | 先核对固定PX4的该模式及接口，验证唯一物理权威和时间映射；当前外部物理SITL不覆盖它 | [#127](https://github.com/unununnnn/wksim/issues/127) |
| SIM-12 | blocked | [#1](https://github.com/unununnnn/wksim/issues/1) / [#1](https://github.com/unununnnn/wksim/issues/1) | 先核对RFly固件、模型、接口和授权，不按名称猜测可由标准固件代替；#56承接逐模式硬件/固件/接口及授权确认，现缺该确认。 | [#56](https://github.com/unununnnn/wksim/issues/56) |
| COMM-01 | not-implemented | [#1](https://github.com/unununnnn/wksim/issues/1) / [#1](https://github.com/unununnnn/wksim/issues/1) | 精确字段、布局、字节序、速率、目标地址及完整模式控制/反馈行为；对照本地SDK与实际观测 | [#128](https://github.com/unununnnn/wksim/issues/128) |
| COMM-02 | not-implemented | [#1](https://github.com/unununnnn/wksim/issues/1) / [#1](https://github.com/unununnnn/wksim/issues/1) | 字段和时间语义、简化丢失的量、非法报文拒绝及原SDK互操作 | [#129](https://github.com/unununnnn/wksim/issues/129) |
| COMM-03 | evidenced | [#1](https://github.com/unununnnn/wksim/issues/1) / [#1](https://github.com/unununnnn/wksim/issues/1)、[#42](https://github.com/unununnnn/wksim/issues/42)、[#43](https://github.com/unununnnn/wksim/issues/43) | #42真实QGC双栈交接、#43两个参数事务/重启已验；Full SDK消息集合、字段、控制权与频率未冻结。 | [#130](https://github.com/unununnnn/wksim/issues/130) |
| COMM-04 | not-implemented | [#1](https://github.com/unununnnn/wksim/issues/1) / [#1](https://github.com/unununnnn/wksim/issues/1) | 缺相对Full的消息删减、频率和参考采样；速度/yaw #32不是本模式证据。 | [#131](https://github.com/unununnnn/wksim/issues/131) |
| COMM-05 | not-implemented | [#1](https://github.com/unununnnn/wksim/issues/1) / [#1](https://github.com/unununnnn/wksim/issues/1) | 被动接收的副作用、是否允许响应及其参考证据；抓包证明发送约束 | [#132](https://github.com/unununnnn/wksim/issues/132) |
| COMM-06 | not-implemented | [#1](https://github.com/unununnnn/wksim/issues/1) / [#45](https://github.com/unununnnn/wksim/issues/45) | 传感器/定位与控制条件；GNSS故障切片不自动等价于此模式 | [#133](https://github.com/unununnnn/wksim/issues/133) |
| COMM-07 | not-implemented | [#1](https://github.com/unununnnn/wksim/issues/1) / [#1](https://github.com/unununnnn/wksim/issues/1) | 缺视觉定位消息、坐标/协方差/采样时间与估计器接入合同；#30 RGB不是本模式证据。 | [#134](https://github.com/unununnnn/wksim/issues/134) |
| MODEL-01 | blocked | [#1](https://github.com/unununnnn/wksim/issues/1) / [#1](https://github.com/unununnnn/wksim/issues/1)、[#23](https://github.com/unununnnn/wksim/issues/23)、[#24](https://github.com/unununnnn/wksim/issues/24) | #24已完成质量编辑、导出/导入和静态响应，正式产品参数运行入口尚未验收。仅定义所选质量配置从保存/导入到正式任务、UE、冷重建及结果身份的接线合同；数值精度路线由既有#59承接，不复制该票，不改R1。 R1仍numerical_failed。 | [#135](https://github.com/unununnnn/wksim/issues/135)、[#59](https://github.com/unununnnn/wksim/issues/59) |
| MODEL-02 | not-implemented | [#25](https://github.com/unununnnn/wksim/issues/25) / [#25](https://github.com/unununnnn/wksim/issues/25) | 静态18项与PX4-03 observed已记录，#52仅逐tick基础检查；完整原始审计、AP、两栈冷重置与真实显示由#65–#69及父#25承接。 | [#65](https://github.com/unununnnn/wksim/issues/65)、[#66](https://github.com/unununnnn/wksim/issues/66)、[#67](https://github.com/unununnnn/wksim/issues/67)、[#68](https://github.com/unununnnn/wksim/issues/68)、[#69](https://github.com/unununnnn/wksim/issues/69) |
| MODEL-03 | not-implemented | [#1](https://github.com/unununnnn/wksim/issues/1) / [#1](https://github.com/unununnnn/wksim/issues/1) | 单独构型、驱动/舵机、模型与测试定义 | [#136](https://github.com/unununnnn/wksim/issues/136) |
| MODEL-04 | not-implemented | [#1](https://github.com/unununnnn/wksim/issues/1) / [#1](https://github.com/unununnnn/wksim/issues/1) | 共轴影响、旋向、电机分配与具体参数 | [#137](https://github.com/unununnnn/wksim/issues/137) |
| MODEL-05 | not-implemented | [#1](https://github.com/unununnnn/wksim/issues/1) / [#1](https://github.com/unununnnn/wksim/issues/1) | 独立构型、动力与混控校验 | [#138](https://github.com/unununnnn/wksim/issues/138) |
| MODEL-06 | not-implemented | [#1](https://github.com/unununnnn/wksim/issues/1) / [#1](https://github.com/unununnnn/wksim/issues/1) | 独立构型与适用飞控校验 | [#139](https://github.com/unununnnn/wksim/issues/139) |
| MODEL-07 | not-implemented | [#1](https://github.com/unununnnn/wksim/issues/1) / [#1](https://github.com/unununnnn/wksim/issues/1) | 各自模型来源、控制栈/执行器、运动工况；不能强行要求由ArduCopter控制固定翼 | [#140](https://github.com/unununnnn/wksim/issues/140)、[#141](https://github.com/unununnnn/wksim/issues/141) |
| MODEL-08 | not-implemented | [#1](https://github.com/unununnnn/wksim/issues/1) / [#1](https://github.com/unununnnn/wksim/issues/1) | 转向/驱动接口、轨迹与地形工况 | [#142](https://github.com/unununnnn/wksim/issues/142) |
| MODEL-09 | not-implemented | [#1](https://github.com/unununnnn/wksim/issues/1) / [#1](https://github.com/unununnnn/wksim/issues/1) | 差速映射及对应运动/重置工况 | [#143](https://github.com/unununnnn/wksim/issues/143) |
| MODEL-10 | not-implemented | [#1](https://github.com/unununnnn/wksim/issues/1) / [#1](https://github.com/unununnnn/wksim/issues/1) | 无控输入和模型观测，不依赖飞控也可验收 | [#144](https://github.com/unununnnn/wksim/issues/144) |
| MODEL-11 | not-implemented | [#1](https://github.com/unununnnn/wksim/issues/1) / [#1](https://github.com/unununnnn/wksim/issues/1) | 牵引/关节与场景耦合工况 | [#145](https://github.com/unununnnn/wksim/issues/145) |
| MODEL-12 | not-implemented | [#1](https://github.com/unununnnn/wksim/issues/1) / [#1](https://github.com/unununnnn/wksim/issues/1) | 无控模型输入、运动与复位定义 | [#146](https://github.com/unununnnn/wksim/issues/146) |
| MODEL-13 | not-implemented | [#1](https://github.com/unununnnn/wksim/issues/1) / [#1](https://github.com/unununnnn/wksim/issues/1) | 无飞控模型接口与适用控制方式，不按名称猜测实现 | [#147](https://github.com/unununnnn/wksim/issues/147) |
| MODEL-14 | not-implemented | [#1](https://github.com/unununnnn/wksim/issues/1) / [#1](https://github.com/unununnnn/wksim/issues/1) | 纯模型速度控制工作流，不等同于真实FC速度票 | [#148](https://github.com/unununnnn/wksim/issues/148) |
| MODEL-15 | not-implemented | [#1](https://github.com/unununnnn/wksim/issues/1) / [#1](https://github.com/unununnnn/wksim/issues/1) | SIL集群场景、身份及共享时间映射，不能由双FC联合场景自动代验 | [#149](https://github.com/unununnnn/wksim/issues/149) |
| MODEL-16 | not-implemented | [#1](https://github.com/unununnnn/wksim/issues/1) / [#26](https://github.com/unununnnn/wksim/issues/26) | 两个模板各自I/O、生成、构建、导入与运行流程；缺可编辑材料时明确阻塞 | [#150](https://github.com/unununnnn/wksim/issues/150)、[#151](https://github.com/unununnnn/wksim/issues/151) |
| OPS-01 | evidenced | [#1](https://github.com/unununnnn/wksim/issues/1) / [#24](https://github.com/unununnnn/wksim/issues/24) | 四旋翼参数表单不是完整数据库；删除只作用于用户明确选择的工作副本，不能改原厂库 | [#152](https://github.com/unununnnn/wksim/issues/152) |
| OPS-02 | evidenced | [#1](https://github.com/unununnnn/wksim/issues/1) / [#23](https://github.com/unununnnn/wksim/issues/23) | 在线服务存在不保证可访问或公式已公开；本地独立计算与服务集成分开记录 | [#153](https://github.com/unununnnn/wksim/issues/153) |
| OPS-03 | not-implemented | [#1](https://github.com/unununnnn/wksim/issues/1) / [#26](https://github.com/unununnnn/wksim/issues/26) | 能选一个DLL不等于XML模型配置可用 | [#154](https://github.com/unununnnn/wksim/issues/154) |
| OPS-04 | evidenced | [#1](https://github.com/unununnnn/wksim/issues/1) / [#18](https://github.com/unununnnn/wksim/issues/18) | 初期“点启动”仅覆盖一个正常产品路径，不能吞掉参数组合与错误流程 | [#155](https://github.com/unununnnn/wksim/issues/155) |
| OPS-05 | evidenced | [#1](https://github.com/unununnnn/wksim/issues/1) / [#13](https://github.com/unununnnn/wksim/issues/13)、[#19](https://github.com/unununnnn/wksim/issues/19) | 本机两独立实验隔离和同机场景各自仅覆盖子集；跨主机边界单独验证 | [#156](https://github.com/unununnnn/wksim/issues/156) |
| OPS-06 | evidenced | [#1](https://github.com/unununnnn/wksim/issues/1) / [#1](https://github.com/unununnnn/wksim/issues/1)、[#25](https://github.com/unununnnn/wksim/issues/25)、[#48](https://github.com/unununnnn/wksim/issues/48) | #48已有P450真实五场产品显示，Hex有几何静态夹具；全机型资产库、场景选择/导入及ClassID映射仍缺合同。 | [#157](https://github.com/unununnnn/wksim/issues/157) |
| OPS-07 | not-implemented | [#1](https://github.com/unununnnn/wksim/issues/1) / [#29](https://github.com/unununnnn/wksim/issues/29) | 单坡面/单障碍切片只是首例，不代表全部场景交互 | [#158](https://github.com/unununnnn/wksim/issues/158) |
| OPS-08 | evidenced | [#1](https://github.com/unununnnn/wksim/issues/1) / [#30](https://github.com/unununnnn/wksim/issues/30)、[#31](https://github.com/unununnnn/wksim/issues/31) | RGB与深度生成点云不覆盖扫描LiDAR、分割及其他未细化能力 | [#159](https://github.com/unununnnn/wksim/issues/159) |
| OPS-09 | not-implemented | [#1](https://github.com/unununnnn/wksim/issues/1) / [#44](https://github.com/unununnnn/wksim/issues/44)、[#45](https://github.com/unununnnn/wksim/issues/45) | 单电机效率与GNSS中断各只覆盖一种事件 | [#160](https://github.com/unununnnn/wksim/issues/160) |
| OPS-10 | evidenced | [#1](https://github.com/unununnnn/wksim/issues/1) / [#1](https://github.com/unununnnn/wksim/issues/1)、[#35](https://github.com/unununnnn/wksim/issues/35)、[#36](https://github.com/unununnnn/wksim/issues/36)、[#37](https://github.com/unununnnn/wksim/issues/37)、[#38](https://github.com/unununnnn/wksim/issues/38)、[#39](https://github.com/unununnnn/wksim/issues/39)、[#40](https://github.com/unununnnn/wksim/issues/40) | #32速度/yaw、#34姿态出口已验；PID有源对照/候选与preflight，UDE/NE、RC、规划/ArUco有现存链。其他公开算法/demo/多机队形的固定来源映射和单实验AC仍缺。 | [#161](https://github.com/unununnnn/wksim/issues/161) |
| OPS-11 | evidenced | [#1](https://github.com/unununnnn/wksim/issues/1) / [#16](https://github.com/unununnnn/wksim/issues/16) | 既有JSONL回看不自动完成全部记录系统或跨平台确定性 | [#162](https://github.com/unununnnn/wksim/issues/162) |
| OPS-12 | evidenced | [#1](https://github.com/unununnnn/wksim/issues/1) / [#26](https://github.com/unununnnn/wksim/issues/26)、[#1](https://github.com/unununnnn/wksim/issues/1) | 本机能编译厂商ZIP不代表可以公开分发其源代码；本地UE staging素材同理 | [#163](https://github.com/unununnnn/wksim/issues/163) |
| OPS-13 | blocked | [#1](https://github.com/unununnnn/wksim/issues/1) / [#1](https://github.com/unununnnn/wksim/issues/1) | 单机3倍速或两机验证不证明十机、任意硬件或分布式实时性能 | [#164](https://github.com/unununnnn/wksim/issues/164) |

仅复核规划覆盖，不宣布Full或G0–G6通过。冻结原文在#55证据目录input-expansion.md保留，原#54台账不改写。每个后继的真实运行、协议/物理预算和资源仍需独立验收。
