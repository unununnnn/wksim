# Prometheus 命令语义 ROS2 迁移验证

2026-09-05。本报告采用普通工程文档结构（flavor=null），不是安全评估报告。

## 结论与范围

已新增可由 Humble 独立构建的 `prometheus_control` 命令库，迁移主体是固定的 Prometheus 上游，而非 AeroTwinSim 的控制逻辑。两包全新构建、47项接口/104次CDR往返、代表性ROS2通信以及32项完整单元回归均通过。对固定上游原C++方法进行102组差分对照，有效参考量最大绝对差 `1.31750663356911e-6`，通过运行前写入脚本的绝对容差 `2e-5`、相对容差 `1e-6`。

**仅迁移了命令受理和参考量计算，不是完整飞控控制链路。** 差分容差针对C++ float32中间值与Python计算的数值差，不是CopterSim动力学/传感器等价预算，也不证明未覆盖输入上的全等价。当前阶段未启动真实飞控、UE或MATLAB；接口通信测试运行于私有网络命名空间，无飞行命令进入用户运行。

授权范围沿用[运行边界](sitl-runtime-proposal.md)与[完整复刻范围](coptersim-reconstruction.md)：在wksim内推进Prometheus移植，保留上游和既有本机资源。原ROS1文件未修改，无提交或推送。新源码与本报告目前仅在本地工作树。

## 来源和覆盖

上游：`amov-lab/Prometheus`，提交 `5dcd8cfa764d558f3e15dcb88aa7d49e32c54cce`，文件 [uav_controller.cpp](../Modules/uav_control/src/uav_controller.cpp)。Git blob SHA256为 `af30c0ef29d3637019009501dd3a8d99a3064d5916672ad841f4aa8123f99e5f`。Windows检出文件含CRLF，原始字节哈希不同；差分工具以换行规范化验证检出内容与固定提交相同，再直接抽取Git原文参与编译。

| 上游位置 | 移植内容 | 明确限制 |
| --- | --- | --- |
| `set_command_des`，474–649行 | 起点悬停、当前点悬停、降落意图、全部9种MOVE参考量 | 仅有效参考量，不含飞控输出 |
| `uav_cmd_cb`，717–752行 | 命令模式门控、绝对控制优先级、规划停止/恢复信号 | 本地受理不等于飞控ACK |
| `uav_state_cb`，866–892行 | 状态更新、解锁起点 | 宿主管理时间戳与状态新鲜度 |
| `check_failsafe`，1044–1105行 | 连接、RC、围栏、里程计检查优先级 | 无自动OFFBOARD重获或伪造降落确认 |
| `rotation_yaw`，1641–1645行 | BODY平面参考转换 | 第一次计算锚定，不逐帧重新锚定 |

实际API、坐标、BODY ID高水位、拒绝原因及有意改进见[包说明](../ros2/src/prometheus_control/README.md)。混合速度模式更新当前yaw rate、禁用外部姿态时显式拒绝、非有限值/非法输入拒绝、解除解锁清除运动状态均是有意变化，不计为上游全等价。

102组对照由固定种子5605生成：9种MOVE模式各8组，共72组；24组BODY重复命令改变当前位姿后仍保持原锚点；6组起点/绝对悬停/普通命令拒绝/退出绝对控制/降落序列。比较控制状态、停止/恢复逻辑值及激活的参考字段。混合模式的yaw-rate修复通过单元测试验证，不纳入“与旧缺陷相同”的差分声明。

差分oracle并非第二份人工重写实现：验证壳只提供原方法依赖的最小成员及本地布尔发布替身；从固定Git源码抽取三个原方法，使用ROS2生成的真实C++消息类型和原有Eigen安装编译。别名依据消息移植清单生成；原C++片段仅写入私有WSL构建目录。该oracle不包含原主循环、MAVROS、PID/UDE/NE或任何DDS飞控连接。

## 复现

从Windows PowerShell运行完整两包构建：

```powershell
wsl.exe -d Ubuntu-22.04 --exec bash /mnt/c/Users/PC/Documents/odid编译/wksim/tools/build-prometheus-ros2.sh
```

需要现有Ubuntu22.04/Humble、ament、colcon与标准消息包；差分编译还需本机已有g++、CMake、Eigen3。脚本不安装依赖，私有网络命名空间需要WSL root。每次产生新的构建/证据目录，不覆盖旧运行；看 `exit-code.txt` 判断整条构建链是否成功。

在WSL Bash使用本次已验证的安装目录：

```bash
source /root/wksim-ros2-UO3Fz2/install/setup.bash
cd /mnt/c/Users/PC/Documents/odid编译/wksim
python3 -m unittest validation.test_wksim_core validation.test_sitl_dds validation.test_ue55_bridge validation.test_prometheus_interfaces validation.test_prometheus_control -v
python3 -m tools.validate_prometheus_commands
```

若使用新构建，source脚本打印的对应安装目录。差分验证拒绝直接从仓库加载命令模块，也拒绝安装模块与仓库源码不一致。不要以直接执行文件方式替代上述 `-m tools.validate_prometheus_commands`，它需要仓库根目录作为模块上下文。

## Evidence

下列路径相对于仓库根目录。观察时间均为UTC；离线复现要求保留固定Git对象及本机已有依赖。每项 `supersedes=none`，旧失败记录未覆盖；`linked_workitem` 均为 [Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS）](https://github.com/unununnnn/wksim/issues/1) 的已授权实施工作。

### E-001 原方法来源

- title: 固定上游方法和102组可重复输入。
- observed_at: 2026-09-05T07:30:20Z。
- source_type: file。
- source_ref / artifact_path: `validation/prometheus-command-e_8fywjj/oracle-input.txt`。
- content_hash: `4ae392f23a7d4393f7c08f6926ab065c3a0cb3a0b5de929d054da5cddd8fe991`。
- repro_command: 在上述WSL环境运行 `python3 -m tools.validate_prometheus_commands`；源码可用 `git show 5dcd8cfa764d558f3e15dcb88aa7d49e32c54cce:Modules/uav_control/src/uav_controller.cpp` 只读核对。
- raw_excerpt: `cases=102; seed=5605`；上游方法直接参与oracle构建。

### E-002 构建和完整回归

- title: 两包构建成功及32项回归。
- observed_at: 2026-09-05T07:29:13Z（完整回归日志写入时间）。
- source_type: log。
- source_ref / artifact_path: `validation/prometheus-ros2-kpuV2O70/all-tests.log`。
- content_hash: `9fa815de730211dcf04f11361bbe80c3f999d9f2f96d108624ea5d617e7d49a2`。
- repro_command: 上节完整 `python3 -m unittest ... -v` 命令；构建使用 `tools/build-prometheus-ros2.sh`。
- raw_excerpt: `Ran 32 tests in 2.633s; OK`。
- 配套记录：同目录 `build.log` SHA256 `78e6a3041cdeb29aeedfb8972d8b8db6333bc592df92eb94e99e313f66a3edf2`；`control-tests.log` SHA256 `131290a7318df76bbc7c35cdd5709f711e30305b36760ead444d6458f05a56af`，8项通过；`result.json` SHA256 `e0436198b32fec2df78db8b203fa0d7bed2f39ebc816d5e7fad1b9ff82d2c930`，47项接口/104次CDR及代表性RMW通过；`exit-code.txt=0`。

### E-003 原C++方法差分与源码完整性

- title: 安装模块一致性与102组参考量对照。
- observed_at: 2026-09-05T07:30:20Z。
- source_type: file。
- source_ref / artifact_path: `validation/prometheus-command-e_8fywjj/result.json`。
- content_hash: `4945fd1abcf5f684662ef8ab157c0177dab12369e71550f0f8f8055964f77e66`。
- repro_command: `python3 -m tools.validate_prometheus_commands`。
- raw_excerpt: `status=pass; cases=102; maximum_absolute_error=1.31750663356911e-06`。
- 模块源码SHA256：`38c2899e53d9946faa47691cb98586e70e6db349fad9772bf65a9d1b09d284dc`。仓库源、`/root/wksim-ros2-UO3Fz2/src/prometheus_control/prometheus_control/command.py`、安装文件三者一致；测试实际从安装文件加载。结果同时记录测试、oracle和验证脚本哈希。

### E-004 保留的首次失败

- title: 初始测试误把ROS2默认Quaternion当作零四元数。
- observed_at: 2026-09-05T07:16:22Z（日志写入时间）。
- source_type: log。
- source_ref / artifact_path: `validation/prometheus-ros2-naKMvc1l/control-tests.log`。
- content_hash: `60629c5975395e99e24431bfed762046372566ddca5bf724cbd146dd15420ef3`。
- repro_command: 当前测试已修正；只读检查此保留日志及 `validation/test_prometheus_control.py` 的显式 `Quaternion(w=0.0)` 用例。
- raw_excerpt: `AssertionError: ValueError not raised`。
- 原因及处理：默认Quaternion的w为1，不应被零四元数守卫拒绝；修改测试构造显式零四元数，未放宽生产代码校验。随后全新构建通过E-002，独立差分通过E-003。

## Findings 与调用路径

### F-001 已迁移的命令层有来源与运行证据

- severity: n/a_re；category: other；status: validated；confidence: high。
- evidence_ids: [E-001, E-002, E-003]。
- location: `ros2/src/prometheus_control/prometheus_control/command.py`。
- impact: 可独立复用Prometheus命令受理、优先级、BODY锚定和参考量计算；不能替代输出修整与飞控适配。
- repro_steps: 按上节构建、运行完整回归、运行C++差分，检查新生成结果。
- remediation: 继续从原上游迁移剩余控制层；保持有意变化与兼容性对照分别验收。
- optional_attack: n/a，普通工程迁移。

### F-002 测试错误已修正，未用放宽生产守卫掩盖

- severity: n/a_re；category: other；status: validated；confidence: high。
- evidence_ids: [E-002, E-004]。
- location: `validation/test_prometheus_control.py`。
- impact: 默认合法四元数与显式非法零四元数区别明确；失败证据保留。
- repro_steps: 阅读首次失败日志，再运行8项命令测试确认零四元数用例。
- remediation: 保持真实生成消息作为测试输入，不用自造消息替身假设默认值。
- optional_attack: n/a。

### P-001 从原方法到已安装模块的验证路径

- path_type: callflow。
- start: 固定Git上游方法与ROS2生成消息。
- goal: 已安装命令库产生可对照的有效参考量。
- steps:
  1. action: 抽取原C++方法并编译oracle；evidence: E-001；finding: F-001。
  2. action: `update_state → enter_control → accept → step → Desired`，分别输入相同工况；evidence: E-002, E-003；finding: F-001。
  3. action: 比较控制状态、停止/恢复信号、有效参考字段，另测拒绝路径与改进；evidence: E-002, E-003, E-004；finding: F-001, F-002。
- residual_risks: 输入样本有限；无输出整形、完整主循环或真实飞控联测；宿主仍须提供运行隔离、新鲜状态、权限/能力检查、时基和超时处理。

## 后续实施边界

保留完整Full目标，下一控制阶段仍须移植速度死区、按轴位置保持、方向切换与偏航保持等输出修整，以及PID/UDE/NE、RC处理和实验任务。不得将本库中的 `RC_POS_CONTROL` 固定悬停当作完整RC控制。原上游混合速度输出中的状态变量交叉使用需要单独对照与明确修复。真实双原生DDS产品适配、联合场景共享时间、MATLAB可选桥、DLL导入及场景反馈均未因本阶段通过而完成。

Codebase Memory已刷新到07:22:53 UTC的44,795节点/145,330边，并定位新库方法；覆盖与freshness限制见[索引说明](codebase-memory.md)。计数并非功能完成比例。
