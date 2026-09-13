# 514743f 之后实施前沿分析报告（不受倍率与 G6 阻塞项）

**基线 Commit**：`514743f`（`feat: quantify native input waits and coordinate external agent checks`）
**分析日期**：2026-09-10
**审查者**：Antigravity (`antigravity`)
**协调边界声明**：
1. **OMP 分工**：全球航点（#47、#118、#119、#120）与 GNSS 中断恢复（#45、#121、#111、#112）由外部代理 OMP 独立负责推进，本文不重复覆盖。
2. **主会话分工**：联合倍率相关调度分析、Linux tracefs 取证器与飞控等待根因分析（#20、#62、#63、#64、#33、#82、#83、#84）由主会话统筹，本文不越权干预。
3. **本文范围**：针对剩余非倍率、非 G6 强阻塞的 8 张重点任务票（#99 RC、#102 规划、#103/#104 相机、#105 故障、#70 模型生成、#73/#76 DLL），梳理其实际技术前沿、现有入口、写入范围、验收判据及缺少的前置。
4. **不变量遵守**：不启动 SITL/UE，不更改生产代码、原证据或 GitHub Issue 状态，不进行 commit/push 或嵌套委派；保留用户对 `docs/Prometheus.gitmodules.reference` 的既有修改。

---

## 一、综合前沿概览表

| 票号 | 模块与稳定键 | 当前状态 | 阻塞归类 | 现有入口 / 依赖文件 | 实施前沿状态与关键缺口 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **#99** | RC 位置控制权<br>`38-runtime-flight` | OPEN | **前沿就绪**<br>(待复核关闭) | `tools/run-rc-flight.sh`<br>`tools/audit_rc_flight.py`<br>`validation/38-rc-flight/final-matrix.json` | **实验候选已全通**。两栈 6 场景共 12 场统一审计 PASS (12/12)；完全不受倍率/G6 阻塞；待 Astra 复核后关闭本票。 |
| **#105** | 单电机效率事件<br>`44-efficiency-seam` | OPEN<br>(needs-triage) | **前沿就绪**<br>(待复核关闭) | `Simulator/wksim_core/motor_efficiency_native.cpp/.h`<br>`tools/run_efficiency_flight.py`<br>`validation/44-efficiency-flight/matrix.json` | **原生与飞行验收已全通**。7 场原生 bench 与双栈 6 场真机仿真全部审计通过 (6/6 PASS)；#105/#106/#107/#108/#44 均具备关闭证据。 |
| **#103** | UE ArUco 真实场景<br>`40-real-scene` | OPEN<br>(needs-triage) | **进行中**<br>(主会话实采中) | `Simulator/ue55/.../WksimRgbFixture.cpp`<br>`Simulator/wksim_perception/aruco.py`<br>`docs/plan/40-aruco-live-scene-contract.md` | **主会话已实现候选 UE 并编译成功**。正在进行真实帧采集与标定核验；记录为进行中，未宣称通过。 |
| **#70** | 模型生成来源合同<br>`26-generation-source` | OPEN<br>(needs-triage) | **工具链/规范受限** | `docs/plan/26-generation-contract.md`<br>`docs/g6-material-index.md`<br>`tools/quad_model_parameters.py` | **合同已明确 e0 SLX 11.8 来源**。现有脚本仅支持旧 ZIP 编译，缺少新源码生成自动化入口，本地编译与分发许可界限需明确。 |
| **#104** | 相机闭环追踪<br>`40-closed-loop` | OPEN | **前置阻塞** | `Modules/tutorial_demo/advanced/aruco_tracking`<br>`Simulator/wksim_runtime/` | **强依赖 #103**。必须等待真实 UE 场景与标定 RGB 帧采集完成后方可实施闭环速度追踪。 |
| **#102** | 规划器绕障飞行<br>`39-planner-flight` | OPEN | **强依赖阻塞** | `Modules/ego_planner_swarm`<br>`Simulator/wksim_planning/trajectory_session.py`<br>`docs/plan/39-planner-contract.md` | **强依赖 #29 与 #33**。受障碍物理反馈（#29）及轨迹跟随/联合倍率（#33）阻塞；#102 自身缺 ROS2 规划构建包装写权。 |
| **#73** | 旧 ABI 隔离宿主<br>`27-host` | OPEN | **规范前置缺失** | `docs/plan/9-abi-environment-accepted.md`<br>`validation/.../abi-facts.json` | **#58 记录证据阻塞**。`DllSimCtrlAPI.py` 类型冲突未解，5 项 manifest/许可前置未齐，无可审阅的有效旧 ABI 样本。 |
| **#76** | 新 ABI 扩展输出<br>`28-modern-adapter` | OPEN | **强依赖与规范阻塞** | `docs/plan/9-abi-environment-accepted.md` | **受 #75/#73 及规范阻塞**。新 ABI 导出合同尚未经由决策票核准，处于序列等待状态。 |

---

## 二、逐项实施前沿分析

### 1. #99 [Astra] 接入RC控制权并交付可验证双栈入口
- **父票关系**：原验收父票 #38（RC 位置控制与任务显式交接）。
- **当前状态**：OPEN（前置 #98 已 CLOSED）。
- **现有入口与已交付物**：
  - 执行入口：`tools/run-rc-flight.sh`（驱动单场私有命名空间运行）、`tools/run_rc_flight.py`。
  - 审计工具：`tools/audit_rc_flight.py`（独立重算死区、积分、CDR GID 与物理阶段）。
  - 核心实现：`Simulator/wksim_control/rc_input.py`、`prometheus_control/rc_transport.py`、`node.py`。
  - 验证证据与报告：`docs/2026-09-10-rc-flight-report.md`、`validation/38-rc-flight/final-matrix.json`、`docs/plan/38-rc-integration.md`。
- **写入范围（Issue 定义）**：
  - `docs/plan/38-rc-integration.md (new)`
  - `validation/38-rc-flight/ (new evidence)`
- **验收条件**：
  - 双栈（PX4 与 ArduCopter）覆盖 movement、recenter、yaw、stream-stall、mode-out、new-takeover 六大场景，通过统一独立原始审计。
  - 验证 CDR 逐包 GID 身份、权威时间新鲜度、显式空中接管与中立意图恢复；断流记录原生失联处理（Offboard failsafe 或保持目标），不宣称断流自动安全悬停。
- **缺少的前置与推进建议**：
  - **前置完备性**：#99 技术实现与候选级审计已完全就绪（12/12 PASS），自身不受倍率或 G6 阻断。
  - **阻塞消除**：目前仅为 GitHub 票据状态保持 OPEN，等待 Astra 或主会话正式审查后关闭 #99。父票 #38 的完全关闭仍保留对 #12、#14、#6 及生产准入的依赖。

---

### 2. #105 [Astra] 实现一次真实单电机效率事件及重置
- **父票关系**：原验收父票 #44（单电机效率故障的可复现实验）。
- **当前状态**：OPEN（待复核关闭；原生 7 场 + 飞行 6 场全部 PASS）。
- **现有入口与已交付物**：
  - 核心 Native 实现：`Simulator/wksim_core/motor_efficiency_native.cpp/.h`、`Simulator/wksim_core/motor_efficiency_model.py`、`Simulator/wksim_core/motor_efficiency_event.py`。
  - 原生报告与证据：`docs/2026-09-10-motor-efficiency-native-report.md`、`validation/44-efficiency-native/archive.json`（库哈希 `a7325ebf...`，7 个原生 bench 独立审计 PASS）。
  - 双栈飞行运行器与审计：`tools/run_efficiency_flight.py`、`tools/run-efficiency-flight.sh`、`tools/audit_efficiency_flight.py`、`tools/efficiency_physics.py`。
  - 飞行报告与矩阵：`docs/2026-09-10-motor-efficiency-flight-report.md`、`validation/44-efficiency-flight/matrix.json`（PX4 与 AP 的 baseline、fault、repeat 共 6 场审计全 PASS）。
- **写入范围（Issue 定义）**：
  - `Simulator/wksim_core/motor_efficiency_event.py (new)`
  - `validation/test_motor_efficiency_event.py (new)`
  - `docs/plan/44-motor-efficiency-contract.md (new)`
- **验收条件**：
  - 单电机气动损失进入 ODE4 子阶段推力与力矩方程（$T_0 = \eta C_t \omega_0^2$、$M_0 = \eta C_m \omega_0^2$）；
  - 严格绑定运行身份、1ms 离散 tick 与种子；Native 子阶段读回必须匹配事件计划；
  - 故障结束后 8 秒内姿态/位置恢复；新运行冷重置验证四路 $\eta$ 均为 1.0。
- **现状结论与推进建议**：
  - **证据完备性**：原生接缝与 6 场真实双栈飞行仿真已完全交付并经受独立审计（6/6 PASS），满足 #105、#106、#107、#108 及父容器 #44 的全部既定验收标准；
  - **推进动作**：本票与 #106/#107/#108/#44 已处于可关闭状态，等待正式复核收口。

---

### 3. #103 [Astra] 创建一个真实UE ArUco场景并核验标定
- **父票关系**：原验收父票 #40（真实相机驱动 ArUco 目标跟踪）。
- **当前状态**：OPEN / 进行中（In-progress）。
- **现有入口与已交付物**：
  - 场景合同：`docs/plan/40-aruco-live-scene-contract.md`（DICT_6X6_250，ID 23，50cm 标靶，相机 640×480/90° FOV，运动与遮挡时序）。
  - 图像消费者与单测：`Simulator/wksim_perception/aruco.py`、`validation/test_aruco_consumer.py`（12 项测试全部通过）。
  - UE 候选组件（主会话最新实现）：`Simulator/ue55/Source/WksimVisual/WksimRgbFixture.cpp/.h`、`WksimVisualGameMode.cpp`、`Simulator/wksim_console/visual.py`。
- **写入范围（Issue 定义）**：
  - `docs/plan/40-aruco-live-scene-contract.md (new)`
  - `validation/40-aruco-live-scene/ (new evidence)`
- **验收条件**：
  - 真实 UE5.5 渲染环境生成标靶网格与材质，驱动权威步运动与遮挡；
  - 独立角点反投影残差 $\le 2$ 像素，重投影 RMS $\le 1$ 像素，各轴平移误差 $\le 0.035$ m；
  - 包含外观、运动、遮挡、恢复各 $\ge 5$ 帧有效数据。
- **现状结论与推进建议**：
  - **实施前沿**：主会话已完成 ArUco 候选 UE C++ 组件实现并编译成功，完成 `run-514743f-03` 真实 39 帧渲染采集；
  - **审计结果**：权威 `now_step` 证实跳步处速度为空系旧目标合法过期，主会话按原合同“连续新鲜帧才比较速度”完成审计修正（`audit-02.json`，四阶段各 $\ge 5$ 帧，角点反投影残差最大 0.485 px，平移误差最大 0.0043 m），并跑通 6 项真实数据负例单测，标定证据已达标。

---

### 4. #104 [Astra] 接入相机跟踪并提供双栈真实验收入口
- **父票关系**：原验收父票 #40。
- **当前状态**：OPEN（被 #103 与 #53 阻塞）。
- **现有入口与已交付物**：
  - 上游参考算法：`Modules/tutorial_demo/advanced/aruco_tracking/src/aruco_tracking.cpp`。
  - 公共控制接缝：`Simulator/wksim_runtime/` 下公共速度指令发布接口。
- **写入范围（Issue 定义）**：
  - `docs/plan/40-aruco-run-contract.md (new)`
  - `validation/40-aruco-flight/ (new evidence)`
- **验收条件**：
  - 在同一次物理运行中，由实时感知的相机位姿解算控制量，完成双栈目标追踪飞行；
  - 满足预设跟踪精度与收敛时间，禁止以离线回放数据充当实时跟踪证据。
- **缺少的前置与推进建议**：
  - **强依赖 #103**：在真实 UE 场景与标定 RGB 数据流就绪前，本票无法单独前行；属于次序等待项。

---

### 5. #70 [Astra] 确定一个实际可用的模型生成来源及合同
- **父票关系**：原验收父票 #26（生成模型构建导入与无 MATLAB 运行）。
- **当前状态**：OPEN / needs-triage（队列处于 ready，父票依赖 #24、#9）。
- **现有入口与已交付物**：
  - 来源资料：`docs/g6-material-index.md` 索引的 RflySim 工作流文档、教程及本地安装模板 `Exp1_MinModelTemp.slx`（v11.8）；
  - 来源合同：`docs/plan/26-generation-contract.md`；
  - 历史构建工具：`tools/quad_model_parameters.py`（仅限旧 ZIP v11.0）。
- **写入范围（Issue 定义）**：
  - `docs/plan/26-generation-contract.md (new)`
- **验收条件**：
  - 确定一条具有明确许可来源、可编辑模板及生成规范的模型生成路径，提供明确构建与导入合同；若因许可阻断则需完整记录证据。
- **缺少的前置与推进建议**：
  - **构建工具链缺口**：缺少调用真实 MATLAB R2022b 的无头批处理构建入口脚本（持续推进已授权无需额外申请写入权限；需调用 `slbuild('Exp1_MinModelTemp')` 与 `ert.tlc` 生成 C++ 源码并输出至隔离目录）；
  - **构建期与日常运行期界限**：SLX 代码生成在构建期必须使用真实 MATLAB/Simulink/Embedded Coder 工具链，不能混淆为无 MATLAB 脚本直接生成；编译出的动态库 `libwksim_e0.so` 在后续仿真日常运行期无 MATLAB 依赖。

---

### 6. #73 [Astra] 实现一个已确认旧ABI的隔离宿主
- **父票关系**：原验收父票 #27（可选旧 ABI 模型 DLL 生命周期闭环）。
- **当前状态**：OPEN（前置 #58 已关闭）。
- **现有入口与已交付物**：
  - 合同与事实：`docs/plan/9-abi-environment-accepted.md`、`validation/lunar-57-6d85dab1b5ff4b84a3a5e58b1fc467a1/abi-facts.json`。
- **写入范围（Issue 定义）**：
  - `Simulator/wksim_plugins/legacy_host.py (new)`
  - `Simulator/wksim_plugins/legacy_manifest.py (new)`
  - `validation/test_legacy_host.py (new)`
- **验收条件**：
  - 实现独立进程的 DLL 加载、初始化、单步计算、重置与卸载；
  - 提供宿主崩溃、非法布局的错误边界测试，不篡改原厂安装。
- **缺少的前置与推进建议**：
  - **证据阻断（来自 #58）**：现有厂商 `DllSimCtrlAPI.py` 存在浮点数组类型定义冲突（float 与 double 混用），且缺乏完整符号与错误码声明。按 #58 决议，在 5 项前置 manifest 完备前保持阻断；
  - **目录脚手架**：`Simulator/wksim_plugins/` 目录尚未建立。

---

### 7. #76 [Astra] 实现一个已确认新ABI与扩展输出适配
- **父票关系**：原验收父票 #28（可选新 ABI 模型 DLL 与扩展输出）。
- **当前状态**：OPEN（依赖 #73 $\rightarrow$ #74 $\rightarrow$ #75 串行链路推进；#58 决议明确未批准新 ABI）。
- **现有入口与已交付物**：
  - 合同依据：`docs/plan/9-abi-environment-accepted.md`。
- **写入范围（Issue 定义）**：
  - `Simulator/wksim_plugins/modern_host.py (new)`
  - `Simulator/wksim_plugins/modern_manifest.py (new)`
  - `validation/test_modern_host.py (new)`
- **验收条件**：
  - 适配独立新 ABI 样本声明的扩展 I/O 通道与生命周期，严格拒绝不匹配清单。
- **缺少的前置与推进建议**：
  - **依赖状态与内容缺口精细区分**：决策票 #58 实时状态已为 **CLOSED**，但其决议内容明确记录新 ABI 同样未予批准（仅有 `16H28f` 等协议线索，缺权威 step、epoch 及状态机定义）；阻断来源并非等待工单关闭，而是缺少已核准的具体样本清单规范；
  - **执行序列**：需在旧 ABI 宿主（#73）及自主核心无 DLL 运行（#75）验证后，且新样本规范经核准后实施。

---

### 8. #102 [Astra] 接入规划器并验证一个真实绕障场景
- **父票关系**：原验收父票 #39（单机规划绕障到真实飞行）。
- **当前状态**：OPEN（前置 #101 已关闭，但受 #29 与 #33 阻塞）。
- **现有入口与已交付物**：
  - 规划器源：`Modules/ego_planner_swarm`（EGO rebound 算法）；
  - 轨迹适配会话：`Simulator/wksim_planning/trajectory_session.py`（单测 `validation/test_trajectory_session.py` 覆盖停止优先与 ID 严格单调）；
  - 测试规格：`docs/plan/39-planner-contract.md`（定义单一盒体点云地图 `ego-single-box-v1`）。
- **写入范围（Issue 定义）**：
  - `docs/plan/39-planner-run-contract.md (new)`
  - `validation/39-planner-flight/ (new evidence)`
- **验收条件**：
  - 真实点云 $\rightarrow$ EGO 规划 $\rightarrow$ 公共轨迹修整 $\rightarrow$ 双栈飞行执行；
  - 全程无物理碰撞，包围球至障碍净空 $\ge 0.30$ m，到达目标后稳定悬停，指令 ID 递增。
- **缺少的前置与推进建议**：
  - **强依赖阻塞**：受 #29（坡面/障碍物理碰撞反馈）与 #33（双栈混合轴与轨迹跟随）阻断；且 #33 直连联合倍率阻塞（#82/#83）；
  - **工程写权**：#102 缺少在 ROS2 下编译 EGO 节点及桥接点云的源码写入授权。

---

## 三、推进优先级与前沿路线图建议

根据依赖解耦程度与实施就绪度，不受倍率与 G6 影响的工作前沿推荐推进顺序如下：

```
[阶段 1: 成果收口（证据完备，待正式复核关闭）]
  ├── #99 RC 控制权（及父票 #38）：实验矩阵 12/12 审计全 PASS，建议发起评审并关闭 #99。
  ├── #105 / #106 / #107 / #108 / #44 单电机效率全套工况：原生 bench 7 场 + 双栈 6 场飞行仿真审计全 PASS，建议统一复核并关闭。
  └── #103 UE 机载相机与 ArUco 场景：真实渲染采集 39 帧，audit-02.json 审计与 6 项负例全 PASS，标定证据达标。

[阶段 2: 独立推进项（#70 模型代码生成）]
  └── #70 模型生成：已锁定 SLX 11.8 来源与真实商业 MATLAB R2022b 工具链，持续推进授权下待编写无头批处理生成入口脚本，严格分离构建期与日常无 MATLAB 运行期。

[阶段 3: 次级与深层依赖等待]
  ├── #104 相机闭环追踪：#103 实采标定已就绪，等待双栈跟踪闭环入口接入。
  ├── #73 / #76 DLL 宿主：等待厂家 ABI 样本清单与使用授权明确（#58 决议）。
  └── #102 规划绕障：等待 #29 物理反馈与 #33 轨迹控制闭环。
```
