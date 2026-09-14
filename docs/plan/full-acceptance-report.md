# Full/G0–G6 最终复核报告（#60，未通过）

工作类别：`acceptance-report`  
module / interface：Full/G0–G6 报告层（只读复核，不改实现）  
独占写入：仅本文件 `docs/plan/full-acceptance-report.md`  
直接依赖：`docs/plan/full-scope-expansion.md`、`docs/2026-09-09-numerical-conformance-report.md`、一次 `gh issue list`  
沿用 adapter：无  
受影响测试与实际验收：本切片不重跑、不新建测试、不关闭票  
交付后停止写入：本文件写完即停；不 add/commit/push

## 开工核验

```text
工作类别：acceptance-report
实际 cwd、分支、HEAD：C:/Users/PC/Documents/odid编译/wksim  main  5370b2324672c9036d41239cb93e21fc5eb42897
架构祖先检查退出码：0（f333316e6efa6b299b4288a9d91fb2bccedfb9d6 ⊆ HEAD）
已读：AGENTS.md、docs/architecture-implementation-20260912.md、docs/coordination/architecture-continuation-20260913.md、CONTEXT.md、GitHub #60、docs/plan/full-scope-expansion.md、docs/2026-09-09-numerical-conformance-report.md、docs/coordination/short-cycle-goal.md
本次 module / interface：Full/G0–G6 报告层
直接依赖：full-scope-expansion 48 机器键；一次 issue list 前置状态
沿用的 adapter：无
独占文件：docs/plan/full-acceptance-report.md
不在本次范围：native / model / MATLAB / ROS / DDS / SITL / FC / UE / build / flight / #83 重跑 / git / GitHub 写操作
```

开工时本文件不存在（`Test-Path` = False）。本报告不是 owner approval，不宣布 Full 或 G6 通过，不关闭 #1/#10/#60，不标记 Goal complete。

**终态：#1 OPEN；#10 OPEN；Goal OPEN。Full 未通过。G6 未通过。无 owner approval。**

## 机械计数

源文件：`docs/plan/full-scope-expansion.md`（SHA256 `85c15ad817afe35fcd325435f02ccb894ad33015e223537daa3cc3706a564fee`）  
计数规则：匹配源复核表数据行 `^\| (SIM|COMM|MODEL|OPS)-\d+ \|`  
源行数 = **48**  
源唯一键 = **48**  
源重复键 = **none**  
本报告复制行数必须 = 48，且键集合必须与源完全相同。

源键序列（机械抽出，保持原序）：

```text
SIM-01,SIM-02,SIM-03,SIM-04,SIM-05,SIM-06,SIM-07,SIM-08,SIM-09,SIM-10,SIM-11,SIM-12,COMM-01,COMM-02,COMM-03,COMM-04,COMM-05,COMM-06,COMM-07,MODEL-01,MODEL-02,MODEL-03,MODEL-04,MODEL-05,MODEL-06,MODEL-07,MODEL-08,MODEL-09,MODEL-10,MODEL-11,MODEL-12,MODEL-13,MODEL-14,MODEL-15,MODEL-16,OPS-01,OPS-02,OPS-03,OPS-04,OPS-05,OPS-06,OPS-07,OPS-08,OPS-09,OPS-10,OPS-11,OPS-12,OPS-13
```

源文件前文无机器键的模式/机型/操作表与上述 48 键一一对应，不另造第二套键。`requirement-coverage.md` 另有 US-01..US-48，不在本次“从 full-scope-expansion 逐项复制”集合内，不写入下行表。

verdict 只允许：`accepted` / `partial` / `blocked` / `not-tested`。  
本切片不深挖补证。证据不足以闭合 Full 行时不得写 `accepted`。源 `blocked` → `blocked`；源 `not-implemented` → `not-tested`；源 `evidenced` 且仍有剩余缺口 → `partial`。后继定义票 CLOSED 只表示合同定义，不把该行升为 `accepted`。

## 从 full-scope-expansion 逐项复制的 48 行

| row_key | source_status | verdict | requirement_copied | gap_copied | followup_copied | evidence |
| --- | --- | --- | --- | --- | --- | --- |
| SIM-01 | blocked | blocked | PX4_HITL：串口连接实体PX4并执行硬件在环 | 本阶段未验收；先取得硬件、串口、固件、移除动力风险的测试条件及明确授权，再单独拆票；#56承接逐模式硬件/固件/接口及授权确认，现缺该确认。 | #56 | source row SIM-01 in docs/plan/full-scope-expansion.md；#56 CLOSED 仅为决策边界，本切片未见硬件/串口/授权实测，missing |
| SIM-02 | evidenced | partial | PX4_SITL：通过TCP连接标准PX4软件在环 | 固定PX4独立DDS产品任务已验；冻结PX4_SITL的TCP模式选择、接口、停止重连映射未逐项核验。 | #122 | source row SIM-02 in docs/plan/full-scope-expansion.md；局部首期见 docs/2026-09-09-first-phase-acceptance-report.md；TCP/停止重连逐项核验 missing |
| SIM-03 | not-implemented | not-tested | PX4_SITL_RFLY：通过UDP连接Rfly定制PX4软件在环 | 需锁定本地定制固件、协议和使用条件；不能把标准PX4通过记为本模式通过 | #123 | source row SIM-03 in docs/plan/full-scope-expansion.md；本模式端到端证据 missing |
| SIM-04 | not-implemented | not-tested | Simulink&DLL_SIL：无飞控的纯模型运行 | 自主模型有局部构建证据；完整选择、初始化、运行、重置及导出流程另行验收，不要求日常运行必须启动Simulink | #124 | source row SIM-04 in docs/plan/full-scope-expansion.md；完整选择/初始化/运行/重置/导出 missing |
| SIM-05 | blocked | blocked | PX4_HITL_NET：网络连接实体PX4硬件在环 | 硬件/网络和安全授权先决；手册免费版标签不一致不影响它属于Full范围；#56承接逐模式硬件/固件/接口及授权确认，现缺该确认。 | #56 | source row SIM-05 in docs/plan/full-scope-expansion.md；硬件/网络授权实测 missing |
| SIM-06 | blocked | blocked | EXT_HITL_COM：MAVLink串口接外部飞控 | 先明确一个可核验外部飞控和接口，不将“外部”解释为任意厂商任意设备；#56承接逐模式硬件/固件/接口及授权确认，现缺该确认。 | #56 | source row SIM-06 in docs/plan/full-scope-expansion.md；可核验外部飞控与接口 missing |
| SIM-07 | not-implemented | not-tested | EXT_SIM_NET：连接外部仿真系统 | 先明确一个参考系统、物理权威、时钟和失败语义，再做单系统端到端票 | #125 | source row SIM-07 in docs/plan/full-scope-expansion.md；参考系统/时钟/失败语义端到端 missing |
| SIM-08 | evidenced | partial | APM_SITL_NET：连接ArduPilot软件在环 | 固定ArduCopter自主物理产品任务已验；APM_SITL_NET参考网络操作/停止重连映射未逐项核验，其他AP机型不能代验。 | #126 | source row SIM-08 in docs/plan/full-scope-expansion.md；局部首期见 docs/2026-09-09-first-phase-acceptance-report.md；网络操作/停止重连逐项核验 missing |
| SIM-09 | blocked | blocked | PX4_SIH_COM：SIH串口流程 | 需实体设备与对应固件；物理位于飞控内部，必须重新映射显示/任务时间而非再启动第二物理核心；#56承接逐模式硬件/固件/接口及授权确认，现缺该确认。 | #56 | source row SIM-09 in docs/plan/full-scope-expansion.md；实体SIH串口条件 missing |
| SIM-10 | blocked | blocked | PX4_SIH_NET：SIH网络流程 | 与串口分开验证连接、状态、停止和重连；保留硬件/固件条件；#56承接逐模式硬件/固件/接口及授权确认，现缺该确认。 | #56 | source row SIM-10 in docs/plan/full-scope-expansion.md；SIH网络连接/停止/重连 missing |
| SIM-11 | not-implemented | not-tested | PX4_SIH_SITL：软件飞控内运行SIH | 先核对固定PX4的该模式及接口，验证唯一物理权威和时间映射；当前外部物理SITL不覆盖它 | #127 | source row SIM-11 in docs/plan/full-scope-expansion.md；唯一物理权威/时间映射 missing |
| SIM-12 | blocked | blocked | PX4_SIH_FLY：SIH RFly流程 | 先核对RFly固件、模型、接口和授权，不按名称猜测可由标准固件代替；#56承接逐模式硬件/固件/接口及授权确认，现缺该确认。 | #56 | source row SIM-12 in docs/plan/full-scope-expansion.md；RFly固件/模型/接口/授权 missing |
| COMM-01 | not-implemented | not-tested | UDP_Full：参考完整UDP输出与消费，手册列168字节SOut2Simulator | 精确字段、布局、字节序、速率、目标地址及完整模式控制/反馈行为；对照本地SDK与实际观测 | #128 | source row COMM-01 in docs/plan/full-scope-expansion.md；字段/布局/速率对照 missing |
| COMM-02 | not-implemented | not-tested | UDP_Simple：参考简化带时间UDP输出，手册列112字节SOut2SimulatorSimpleTime | 字段和时间语义、简化丢失的量、非法报文拒绝及原SDK互操作 | #129 | source row COMM-02 in docs/plan/full-scope-expansion.md；简化语义与负向报文 missing |
| COMM-03 | evidenced | partial | Mavlink_Full：QGC与SDK所需完整MAVLink交互 | #42真实QGC双栈交接、#43两个参数事务/重启已验；Full SDK消息集合、字段、控制权与频率未冻结。 | #130 | source row COMM-03 in docs/plan/full-scope-expansion.md；Full SDK集合/频率冻结 missing |
| COMM-04 | not-implemented | not-tested | Mavlink_Simple：简化MAVLink交互 | 缺相对Full的消息删减、频率和参考采样；速度/yaw #32不是本模式证据。 | #131 | source row COMM-04 in docs/plan/full-scope-expansion.md；相对Full删减/频率 missing |
| COMM-05 | not-implemented | not-tested | Mavlink_NoSend：只接收，不主动发送 | 被动接收的副作用、是否允许响应及其参考证据；抓包证明发送约束 | #132 | source row COMM-05 in docs/plan/full-scope-expansion.md；抓包发送约束 missing |
| COMM-06 | not-implemented | not-tested | Mavlink_NoGPS：无GPS场景下的参考接口行为 | 传感器/定位与控制条件；GNSS故障切片不自动等价于此模式 | #133 | source row COMM-06 in docs/plan/full-scope-expansion.md；本模式接口行为 missing |
| COMM-07 | not-implemented | not-tested | Mavlink_Vision：视觉定位数据输出 | 缺视觉定位消息、坐标/协方差/采样时间与估计器接入合同；#30 RGB不是本模式证据。 | #134 | source row COMM-07 in docs/plan/full-scope-expansion.md；视觉定位消息/协方差 missing |
| MODEL-01 | blocked | blocked | 四旋翼 | #24已完成质量编辑、导出/导入和静态响应，正式产品参数运行入口尚未验收。仅定义所选质量配置从保存/导入到正式任务、UE、冷重建及结果身份的接线合同；数值精度路线由既有#59承接，不复制该票，不改R1。 R1仍numerical_failed。 | #135,#59 | source row MODEL-01 in docs/plan/full-scope-expansion.md；R1 见 docs/2026-09-09-numerical-conformance-report.md 与 validation/numerical-conformance-gxxh6xhr/run-index.json；正式产品参数运行入口 missing |
| MODEL-02 | not-implemented | not-tested | 六旋翼 | 静态18项与PX4-03 observed已记录，#52仅逐tick基础检查；完整原始审计、AP、两栈冷重置与真实显示由#65–#69及父#25承接。 | #65,#66,#67,#68,#69 | source row MODEL-02 in docs/plan/full-scope-expansion.md；本切片未复核 Hex 原始件，完整六旋翼 Full 行 missing |
| MODEL-03 | not-implemented | not-tested | 三旋翼 | 单独构型、驱动/舵机、模型与测试定义 | #136 | source row MODEL-03 in docs/plan/full-scope-expansion.md；构型/驱动/舵机/测试定义实现与运行 missing |
| MODEL-04 | not-implemented | not-tested | 三轴六旋翼 | 共轴影响、旋向、电机分配与具体参数 | #137 | source row MODEL-04 in docs/plan/full-scope-expansion.md；共轴/旋向/分配参数 missing |
| MODEL-05 | not-implemented | not-tested | 四轴八旋翼 | 独立构型、动力与混控校验 | #138 | source row MODEL-05 in docs/plan/full-scope-expansion.md；构型/动力/混控 missing |
| MODEL-06 | not-implemented | not-tested | 八旋翼 | 独立构型与适用飞控校验 | #139 | source row MODEL-06 in docs/plan/full-scope-expansion.md；构型与适用飞控 missing |
| MODEL-07 | not-implemented | not-tested | 固定翼、复合翼 | 各自模型来源、控制栈/执行器、运动工况；不能强行要求由ArduCopter控制固定翼 | #140,#141 | source row MODEL-07 in docs/plan/full-scope-expansion.md；固定翼/复合翼来源与工况 missing |
| MODEL-08 | not-implemented | not-tested | CarAckerman | 转向/驱动接口、轨迹与地形工况 | #142 | source row MODEL-08 in docs/plan/full-scope-expansion.md；转向/驱动/轨迹/地形 Full 行 missing |
| MODEL-09 | not-implemented | not-tested | CarR1Diff | 差速映射及对应运动/重置工况 | #143 | source row MODEL-09 in docs/plan/full-scope-expansion.md；差速映射/运动/重置 missing |
| MODEL-10 | not-implemented | not-tested | CarNoCtrl | 无控输入和模型观测，不依赖飞控也可验收 | #144 | source row MODEL-10 in docs/plan/full-scope-expansion.md；无控输入/观测 missing |
| MODEL-11 | not-implemented | not-tested | Trailer | 牵引/关节与场景耦合工况 | #145 | source row MODEL-11 in docs/plan/full-scope-expansion.md；牵引/关节/场景耦合 missing |
| MODEL-12 | not-implemented | not-tested | MulticopterNoCtrl | 无控模型输入、运动与复位定义 | #146 | source row MODEL-12 in docs/plan/full-scope-expansion.md；无控输入/运动/复位 missing |
| MODEL-13 | not-implemented | not-tested | MulticopterNOpx4 | 无飞控模型接口与适用控制方式，不按名称猜测实现 | #147 | source row MODEL-13 in docs/plan/full-scope-expansion.md；无飞控接口/控制方式 missing |
| MODEL-14 | not-implemented | not-tested | CopterSILVelCtrl | 纯模型速度控制工作流，不等同于真实FC速度票 | #148 | source row MODEL-14 in docs/plan/full-scope-expansion.md；纯模型速度工作流 missing |
| MODEL-15 | not-implemented | not-tested | MultSILSwarm | SIL集群场景、身份及共享时间映射，不能由双FC联合场景自动代验 | #149 | source row MODEL-15 in docs/plan/full-scope-expansion.md；SIL集群身份/共享时间 missing |
| MODEL-16 | not-implemented | not-tested | Exp1_MinModelTemp、Exp2_MaxModelTemp | 两个模板各自I/O、生成、构建、导入与运行流程；缺可编辑材料时明确阻塞 | #150,#151 | source row MODEL-16 in docs/plan/full-scope-expansion.md；两模板 I/O/生成/构建/导入/运行 missing |
| OPS-01 | evidenced | partial | 模型数据库/组件库：品牌组件参数、自定义参数、确认/计算、加入与删除机型、数据库导入导出、备份恢复 | 四旋翼参数表单不是完整数据库；删除只作用于用户明确选择的工作副本，不能改原厂库 | #152 | source row OPS-01 in docs/plan/full-scope-expansion.md；完整数据库/导入导出/备份恢复 missing |
| OPS-02 | evidenced | partial | 性能计算：悬停时间、油门、电流、转速、功率、能效及FlyEval关联的参考流程 | 在线服务存在不保证可访问或公式已公开；本地独立计算与服务集成分开记录 | #153 | source row OPS-02 in docs/plan/full-scope-expansion.md；本地独立计算与服务集成分开证据 missing |
| OPS-03 | not-implemented | not-tested | XML/模型元数据：ModelInfo、HoverInfo、FrameInfo、ClassID及默认值、单位和错误 | 能选一个DLL不等于XML模型配置可用 | #154 | source row OPS-03 in docs/plan/full-scope-expansion.md；XML 元数据可用 missing |
| OPS-04 | evidenced | partial | CLI/NoUI/GUI一致性：冻结手册16个启动参数、多值初态、GPS、串口/波特率、通信地址、自动启动、实时/日志选项 | 初期“点启动”仅覆盖一个正常产品路径，不能吞掉参数组合与错误流程 | #155 | source row OPS-04 in docs/plan/full-scope-expansion.md；局部首期见 docs/2026-09-09-first-phase-acceptance-report.md；16参数组合与错误流程 missing |
| OPS-05 | evidenced | partial | 网络与远程：UDP广播、指定主机、JSON联机、端口/身份、多实例与分布式场景 | 本机两独立实验隔离和同机场景各自仅覆盖子集；跨主机边界单独验证 | #156 | source row OPS-05 in docs/plan/full-scope-expansion.md；跨主机边界 missing |
| OPS-06 | evidenced | partial | 载具与场景资产：正确机体、旋翼、场景选择、导入资产、模型ClassID映射 | #48已有P450真实五场产品显示，Hex有几何静态夹具；全机型资产库、场景选择/导入及ClassID映射仍缺合同。 | #157 | source row OPS-06 in docs/plan/full-scope-expansion.md；#48 局部见 docs/2026-09-09-first-phase-acceptance-report.md；全机型资产库/ClassID missing |
| OPS-07 | not-implemented | not-tested | 环境反馈：地形、碰撞、动态对象/环境变化、过期反馈处理 | 单坡面/单障碍切片只是首例，不代表全部场景交互 | #158 | source row OPS-07 in docs/plan/full-scope-expansion.md；全部场景交互 missing；父 #29 OPEN |
| OPS-08 | evidenced | partial | 传感器：基础传感器标定/噪声/延迟、其余图像/点云能力与所需Prometheus输入 | RGB与深度生成点云不覆盖扫描LiDAR、分割及其他未细化能力 | #159 | source row OPS-08 in docs/plan/full-scope-expansion.md；扫描LiDAR/分割 missing |
| OPS-09 | not-implemented | not-tested | 故障：电机卡死/关闭、传感器偏置/冻结/丢失、环境扰动和通信异常的公开范围 | 单电机效率与GNSS中断各只覆盖一种事件 | #160 | source row OPS-09 in docs/plan/full-scope-expansion.md；其余故障公开范围 missing |
| OPS-10 | evidenced | partial | 控制/任务/算法：RC其他模式、更多规划/感知demo、多机任务与队形、公开实验来源逐项映射 | #32速度/yaw、#34姿态出口已验；PID有源对照/候选与preflight，UDE/NE、RC、规划/ArUco有现存链。其他公开算法/demo/多机队形的固定来源映射和单实验AC仍缺。 | #161 | source row OPS-10 in docs/plan/full-scope-expansion.md；其他公开算法/demo/多机队形映射 missing；#33 OPEN |
| OPS-11 | evidenced | partial | 日志与复现：源/接收时间、bag与飞控原生日志、完整事件流、回放/重演、容量与缺段策略 | 既有JSONL回看不自动完成全部记录系统或跨平台确定性 | #162 | source row OPS-11 in docs/plan/full-scope-expansion.md；完整记录系统/跨平台确定性 missing；#46 OPEN |
| OPS-12 | evidenced | partial | 资源自主交付：无原版程序/DLL依赖、模型/资产可获得性、构建说明与来源许可 | 本机能编译厂商ZIP不代表可以公开分发其源代码；本地UE staging素材同理 | #163 | source row OPS-12 in docs/plan/full-scope-expansion.md；可公开分发/许可状态 missing；#9/#26/#27/#28 OPEN |
| OPS-13 | blocked | blocked | 性能与规模：目标载具数、步频、吞吐、CPU/GPU负载、记录容量、时间偏差与恢复窗口 | 单机3倍速或两机验证不证明十机、任意硬件或分布式实时性能 | #164 | source row OPS-13 in docs/plan/full-scope-expansion.md；十机/分布式实时性能 missing；RateUnmet 保留见 docs/coordination/short-cycle-goal.md |

### 行键分布（机械）

| family | source_count | report_count |
| --- | ---: | ---: |
| SIM-01..SIM-12 | 12 | 12 |
| COMM-01..COMM-07 | 7 | 7 |
| MODEL-01..MODEL-16 | 16 | 16 |
| OPS-01..OPS-13 | 13 | 13 |
| total unique keys | 48 | 48 |

### verdict 统计（本报告，非功能完成率）

| verdict | count | 含义 |
| --- | ---: | --- |
| accepted | 0 | 无一行达到 Full 行 accepted |
| partial | 12 | 源 evidenced，局部证据不足以闭合 |
| blocked | 8 | 源 blocked，资源/授权/保留失败仍在 |
| not-tested | 28 | 源 not-implemented，本切片不补运行证据 |
| total | 48 | 必须等于源 48 |

partial 12 = SIM-02, SIM-08, COMM-03, OPS-01, OPS-02, OPS-04, OPS-05, OPS-06, OPS-08, OPS-10, OPS-11, OPS-12。  
blocked 8 = SIM-01, SIM-05, SIM-06, SIM-09, SIM-10, SIM-12, MODEL-01, OPS-13。  
not-tested 28 = 其余源 not-implemented 行。

## G0–G6 门

下表 `exit_summary` 是基于 `docs/plan/goal-objective.md` 里程碑用户结果列与必须具备的退出证据列的忠实摘要，不是逐字抄录。本切片只读已确认文件与一次 issue list，不从原始运行重解门。任何门都不是 `accepted`。

| gate | name | exit_summary | verdict | evidence | unresolved |
| --- | --- | --- | --- | --- | --- |
| G0 | 可执行范围 | 已批准的规格、验收接缝、逐票阻塞关系和运行能力清单；规格/票据已发布；既有HITL未被代答；每项需求有票据或明确待决策归属；代码与资源来源可追溯 | partial | docs/plan/goal-objective.md；docs/plan/full-scope-expansion.md；docs/plan/requirement-coverage.md；#10/#1 仍 OPEN | 48 Full 行无一 accepted；HITL 行 blocked；Goal 仍 OPEN |
| G1 | 首期双栈产品闭环 | 同一配置/任务入口分别选择PX4和ArduCopter，启动、飞行、UE查看、停止、回看；真实双栈任务和独立真值通过 | partial | docs/2026-09-09-first-phase-acceptance-report.md（#48 首期，默认不重跑） | 首期不等于全部公开模式/机型；G1 未升为 Full 通过 |
| G2 | 联合场景 | 一个PX4与一个ArduCopter共享物理场景和权威仿真时间；暂停/单步/继续/倍速、掉队和重置证据 | blocked | docs/coordination/short-cycle-goal.md；#20 OPEN；#33 OPEN | RateUnmet 保留；正式 MIXED 证据集仍为空；不重跑 |
| G3 | Prometheus实验 | 按迁移矩阵执行控制模式、单机/多机任务、规划/感知demo；支持/拒绝与动作完成有真实证据 | partial | source row OPS-10 in docs/plan/full-scope-expansion.md；#35/#36/#37/#38/#39/#40 CLOSED | 其他公开算法/demo/多机队形映射 missing；#33 OPEN |
| G4 | Full工具与互操作 | 配置、模型/场景导入、CLI/NoUI/UI、协议、日志、故障和公开模式逐项可操作；缺口不能隐藏 | blocked | 本报告 48 行；#9/#26/#27/#28/#29/#46 OPEN | 28 行 not-tested、8 行 blocked；定义票 CLOSED 不闭合 Full 行 |
| G5 | MATLAB可选接入 | 在已确认范围使用真实MATLAB客户端和可选TCP/JSON桥；断开、粘包/碎片、非法输入、身份、超时和不重放 | partial | docs/2026-09-09-first-phase-acceptance-report.md 记载首期可选 MATLAB | 本切片禁止 MATLAB 操作；完整 G5 负向/许可边界 missing |
| G6 | 完整验收与交接 | 完整覆盖账本无未解决必需项；硬件有授权/实测；构建/运行/失败记录完整；来源及许可清楚；固定场景/初态/输入/种子与预先数值预算 | blocked | docs/2026-09-09-numerical-conformance-report.md；validation/numerical-conformance-gxxh6xhr/run-index.json；docs/coordination/short-cycle-goal.md | R1 仍 5684/numerical_failed；无获批逐量预算；#1/#10/Goal OPEN；无 owner approval |

G0–G6 verdict 分布：accepted=0，partial=4（G0/G1/G3/G5），blocked=3（G2/G4/G6），not-tested=0。

## 前置票表

状态来自本切片唯一一次 `gh issue list --repo unununnnn/wksim --state all --limit 200 --json number,title,state`。不逐票再查，不写 GitHub。

| issue | title_at_list | state_at_list | role | effect_on_#60 |
| --- | --- | --- | --- | --- |
| #1 | Wayfinder：Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS） | OPEN | 根图 / Goal 父 | 保持 OPEN |
| #10 | 规格：Prometheus 到 wksim 完整仿真工具链移植 | OPEN | 验收父票 | 保持 OPEN |
| #60 | [Astra] 按完整原规格及G0–G6进行最终Full复核 | OPEN | 本票 | 保持 OPEN；本文件是未解决清单，不是通过结论 |
| #55 | [Astra] 复核Full台账并把真实缺口转换为实施票 | CLOSED | #60 前置 | 台账可引用；不宣布 Full 通过 |
| #56 | [决策] 明确Full硬件/资源的具体可验收边界 | CLOSED | #60 前置 | 决策边界不等于硬件实测；SIM 硬件行仍 blocked |
| #59 | [Astra] 确定来源一致的 G6 数值验收路线并保留R1失败 | CLOSED | #60 前置 | 路线存在；R1 失败保留，G6 仍 blocked |
| #20 | 联合场景暂停单步与冷重置 | OPEN | #60 前置 | G2 blocked |
| #25 | 六旋翼从参数配置到双栈运行 | CLOSED | #60 前置 | 不把 Hex 升为 MODEL-02 accepted |
| #26 | 生成模型构建导入与无MATLAB运行 | OPEN | #60 前置 | MODEL-16 / OPS-12 未闭合 |
| #27 | 可选旧ABI模型DLL生命周期闭环 | OPEN | #60 前置 | OPS-12 / 插件行未闭合 |
| #28 | 可选新ABI模型DLL与扩展输出 | OPEN | #60 前置 | OPS-12 / 插件行未闭合 |
| #29 | 坡面与障碍场景的物理反馈 | OPEN | #60 前置 | OPS-07 未闭合 |
| #33 | 双栈混合轴与轨迹跟随 | OPEN | #60 前置 | RateUnmet 保留；G2/G3 未闭合 |
| #35 | Prometheus PID控制器选择与闭环 | CLOSED | #60 前置 | 局部链，不闭合 OPS-10 |
| #36 | Prometheus UDE控制器闭环 | CLOSED | #60 前置 | 局部链，不闭合 OPS-10 |
| #37 | Prometheus NE控制器闭环 | CLOSED | #60 前置 | 局部链，不闭合 OPS-10 |
| #38 | RC位置控制与任务显式交接 | CLOSED | #60 前置 | 局部链，不闭合 OPS-10 |
| #39 | 单机规划绕障到真实飞行 | CLOSED | #60 前置 | 局部链，不闭合 OPS-10 |
| #40 | 真实相机驱动ArUco目标跟踪 | CLOSED | #60 前置 | 局部链，不闭合 OPS-10 |
| #44 | 单电机效率故障的可复现实验 | CLOSED | #60 前置 | 单事件，不闭合 OPS-09 |
| #45 | GNSS中断与状态有效性恢复 | CLOSED | #60 前置 | 单事件，不闭合 COMM-06/OPS-09 |
| #46 | 固定输入实验的确定性重新运行 | OPEN | #60 前置 | OPS-11 未闭合 |
| #47 | 双栈全球航点与home基准 | CLOSED | #60 前置 | 不升为 Full 行 accepted |
| #9 | 可选模型插件与场景反馈接口决策 | OPEN | #60 前置 | OPS-12 / 插件决策未闭合 |
| #48 | 首期SITL产品流程集成验收 | CLOSED | 首期保留 | 默认不重跑；不升 G1/Full |
| #83 | [Luna] 执行一次最终组合PV任务和原始审计 | CLOSED | 已通过、不重跑 | 见下节；不重跑，不改写 |
| #84 | [Astra] 提升同一已证实组合并验证正式入口 | OPEN | 同一次 list 可见，非 #60 关闭条件 | 正式入口仍 OPEN；不据此宣称 Full |

仍 OPEN 且阻塞 Full/G6 的前置至少：#9, #20, #26, #27, #28, #29, #33, #46，以及父 #1/#10 与本票 #60。

## 保留失败与已通过不重跑

### R1 / 5684

`docs/2026-09-09-numerical-conformance-report.md`：三工况有效运行，R1 零误差判据未通过；比较 180,360 个值，严格不等 **5,684**；结果 `numerical_failed`。C0/C2G/C3G 失败值 2/1943/3739。本切片不重跑对照，不改预算，不把失败改成通过。

已确认索引：`validation/numerical-conformance-gxxh6xhr/run-index.json`（SHA256 `2a964b731d585ca11c26ec2cc01f9d2b653942c8fc94b347b826c4280e605a94`）。#59 CLOSED 只承接路线并保留该失败。

### RateUnmet

`docs/coordination/short-cycle-goal.md`：最新无探针场 `oayggl_s` 失败，`failed@tick108004`，`RateUnmet`；正式 MIXED 证据集仍为空。#33 OPEN。本切片不重跑、不归因、不宣称修复。

### #83 已通过，不重跑

同一次 issue list：#83 CLOSED。`docs/coordination/short-cycle-goal.md` 写明 `#83` 已 CLOSED（`1w6dru32` PV 真实 PASS）。已确认报告：`docs/2026-09-13-final-combo-pv-pass.md`（SHA256 `d3c70b49da4f090748ee19fc6101d0d86f5021b5daafef1ede5ef15dd146e512`）。本切片禁止 #83 操作，不重跑。#83 通过不等于 MIXED/Full/G6 通过。

## 源码 / 配置身份

本切片只记录已核验只读身份，不新建构建。

| item | value |
| --- | --- |
| cwd | C:/Users/PC/Documents/odid编译/wksim |
| branch | main |
| HEAD | 5370b2324672c9036d41239cb93e21fc5eb42897 |
| architecture ancestor | f333316e6efa6b299b4288a9d91fb2bccedfb9d6，exit 0 |
| frozen handbook SHA256（源文抄录） | 29da779803edaa15c8a751500e96a88243dfc6b71ed6c66e462bf228956143c3 |
| numerical contract SHA256（对照报告抄录） | 23d72e26da5dfc7df0b41b96d090664d0ec022d777f6258e409bf7080f2c08f0 |
| docs/plan/full-scope-expansion.md | SHA256 85c15ad817afe35fcd325435f02ccb894ad33015e223537daa3cc3706a564fee |
| docs/plan/requirement-coverage.md | SHA256 ad659194f12ee52df56278466d5e786c1ea21a25ac5ba1ff63990e84011bbc79 |
| docs/plan/full-followup-tickets.json | SHA256 3747d09a939f70152cc236bf34769e75d68f2ba44a777f9168ac1c8c1a95f5a0 |
| docs/plan/goal-objective.md | SHA256 e035a9a467708fd0240a39866f56d69ca64fa58a4a1e555c0c0aac1894d020a5 |
| docs/2026-09-09-numerical-conformance-report.md | SHA256 82539300993f12fc6509e35ad8147caa57a2777d84e9a1aafac2a6a22c2d4561 |
| docs/2026-09-09-first-phase-acceptance-report.md | SHA256 4135836babb67ba1a8257cb2a8568a0312d8ea900dcfadfbe93d61d3deb9f65a |
| docs/2026-09-13-final-combo-pv-pass.md | SHA256 d3c70b49da4f090748ee19fc6101d0d86f5021b5daafef1ede5ef15dd146e512 |
| docs/coordination/short-cycle-goal.md | SHA256 d6339f23b61e3b1fee4e5d729b283bf1378da2622d9538a8ce29affaa606c71c |
| docs/architecture-implementation-20260912.md | SHA256 2c0d23b204b0cd70da9343106c4f3749f8adef56563cefdf39f0539706500d4d |
| docs/coordination/architecture-continuation-20260913.md | SHA256 665890489b087085d1bf143143b8ae7ddfa0a37af4d3506f3525c31372c1295d |
| CONTEXT.md | SHA256 7932cda0d609c4de74a3df4cbc47553f8f7951fc3ae6c61319b9733dd2d512a2 |
| AGENTS.md | SHA256 144d5157d37e90412840cb38b728581d66293f178a4645c93d3778447f4edac8 |
| validation/numerical-conformance-gxxh6xhr/run-index.json | SHA256 2a964b731d585ca11c26ec2cc01f9d2b653942c8fc94b347b826c4280e605a94 |

当前工作树存在他方未提交文件；本切片只新增本报告，不把工作树当作已发布身份。

## 只读命令

实际执行过、且仅用于核验/计数的命令：

```text
git rev-parse HEAD
git branch --show-current
git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD
Test-Path docs/plan/full-acceptance-report.md
gh issue view 60 --repo unununnnn/wksim --json number,title,state,body,labels,comments
gh issue list --repo unununnnn/wksim --state all --limit 200 --json number,title,state
Select-String -LiteralPath docs/plan/full-scope-expansion.md -Pattern '^\| (SIM|COMM|MODEL|OPS)-\d+ \|'
Get-FileHash -Algorithm SHA256  （仅已确认存在的引用文件）
```

未执行：native / model / MATLAB / ROS / DDS / SITL / FC / UE / build / flight / #83 / git write / gh write。未创建任何辅助或临时脚本文件。

## 失败边界与未解决清单

1. Full 未通过；G6 未通过；无 owner approval。
2. #1 OPEN，#10 OPEN，Goal OPEN，#60 OPEN。本文件满足“显式未解决清单保持开放”，不满足“Every required Full row and gate accepted”。
3. 48 行 accepted=0。blocked=8，partial=12，not-tested=28。
4. R1 保持 `numerical_failed` / 5684，不重跑。
5. RateUnmet 保持，#33/#20 OPEN，不重跑。
6. #83 已通过，不重跑；不转移为 Full/G6。
7. #48 首期保留，默认不重跑。
8. 仍 OPEN 前置：#9, #20, #26, #27, #28, #29, #33, #46。
9. 硬件 HITL/SIH 行仍 blocked；#56 CLOSED 不是实测授权。
10. 未知证据一律 `missing`，不猜测路径，不深挖补证。
11. 不关闭任何票，不改 GitHub，不 add/commit/push。

**结论：#60 本切片交付的是未通过复核报告。禁止将本文件解读为 Full、G6 或 Goal 完成。**
