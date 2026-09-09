# #35 Prometheus PID 纯算法移植与原函数对照

2026-09-09。仅交付外部位置 PID 库及离线对照，不代表 #35 的配置/UI、双栈定点、轨迹和扰动闭环验收完成。原 ROS1 源码未修改。

## 原始来源与直接读取

上游 Prometheus `5dcd8cfa764d558f3e15dcb88aa7d49e32c54cce`。原算法为 `Modules/uav_control/include/Position_Controller/pos_controller_PID.h`：65–94 行初始化、101–238 行 update；原调用 `Modules/uav_control/src/uav_controller.cpp` 的 `get_cmd_from_controller()` 在 PID 分支以 `update(200.0)` 计算后走姿态出口，区别于原生飞控位置环分支。

原 PID 文件 SHA256 `4f75efa91ead6518cf778a2b3294621944e842274a4c1826577fd32c63823f9e`。另外四个直接使用的原头文件完整 SHA 在 `tools/check_position_pid_source.py:PINS`，运行前强制验证。Codebase Memory 已先 list_projects/index_status，ready 为 50,865 节点/165,157 边；搜索定位了原 PID，再直接读取源码。精确路径覆盖为 `no_recorded_issue`、`metadata_changed`，不称当前源码完整入图。追踪给出的依赖含低置信启发边，因此数学和调用关系以真实头文件/调用源为准。没有依赖新 Python 结构的后续图查询，不重复全库索引。

上述为当前本地 CRLF 文件原始字节哈希；上游提交中的 LF blob SHA256 为 `0759179b865e051a8b3d1645e5451b0444dc7115fe0b0c42d8a65fb61a99a828`。已验证 CRLF→LF 后逐字节相等，五个原头文件对上游 `git diff --ignore-space-at-eol --exit-code` 均为零。oracle 使用当前原始文件字节而不重写文件，不把既有换行差异误称为原上游原始字节相同。

原 `init()` 默认：质量 1.0 kg、hover 0.5、Kp/Kv 各轴 2.0、Kvi 各轴 0.3、积分上限各轴 0.5、tilt 10°、g 固定 (0,0,9.8)。Ka 初始化为零且没有参与计算；加速度前馈直接相加。原 P450 YAML 为质量 1 kg、hover 0.47、Kp/Kv 3、积分上限 10、tilt 20°，不与构造默认混淆，也不自动当作当前仿真模型参数。

## 实现及有意保留的边界

`Simulator/wksim_control/position_pid.py` 仅使用 Python 标准库。`PIDConfig` 要求显式质量，`PIDState` 使用 ENU 位置/速度与 FLU→ENU wxyz 单位四元数，`PIDReference` 使用 ENU 位置/速度/加速度和偏航。`select_controller("pid", config)` 每次构建清零实例，UDE/NE/default/未知值立即拒绝。

`PositionPID.update(state, reference, dt_s=..., external_control_active=...)` 使用实际仿真时间差；原 200 Hz 等价于 dt=0.005。active 替换原 `mode == "OFFBOARD"` 的积分门控；AP GUIDED 和 PX4 OFFBOARD 的会话、定位、原生控制权验证归调用方，本库不猜测模式，也不发布命令。调用方在选择、接管、退出、重启和时间不连续时调用 `reset(reason)`。

保留原始运算顺序：非零参考速度先清积分；位置误差绝对值 >3 跳变为 ±1、速度误差 >3 跳变为 ±2；XY 小于原 float32 0.2、Z 小于 0.5 且 active 时按位置误差积分，否则该轴清零；逐轴积分限幅。移动参考在先清零后仍可能同拍积分，不改写为永不积分。反馈+直接加速度前馈形成加速度，再乘质量加重力。

竖直力低于 0.5mg 或高于 2mg 时整体向量按原比例缩放；XY 各自限制 `abs(Faxis/Fz) <= tan(tilt)`，这是逐轴限制，合成倾角可能大于 tilt 参数。保留负竖直力缩放导致水平力翻号的原行为。按**当前偏航**旋转力求 roll/pitch，输出目标 yaw；按**当前完整姿态**的 body +Z 投影求 u1。不是通用几何控制器，也没有换成飞控位置环。

明确差异：原构造/init 未初始化 `int_e_v`，移植版初始化/重置为零；原 Fz=0 会除零，移植版拒绝且不提交积分；无效/非有限输入、非单位四元数、非正 dt 拒绝。浮点运算采用 Python double，不承诺跨语言逐位一致；原 float 参数与 Eigen 计算的差异通过冻结容差检查。

`PIDOutput` 提供原始反馈加速度（不含重力、在限力前）、限幅 ENU 力、ENU roll/pitch/yaw、当前 body Z 投影力、积分和质量。`NativeThrustConfig` 要求 stack、固定 model_identity、质量和独立 hover 标定，校验模型/质量后按原 `u=u1/(m*9.8/hover)` 并夹在 [0.1,1]。这是悬停附近线性近似，不是模型电机力曲线。AP 使用正 collective，PX4 FRD `thrust_body=(0,0,-u)`；既有姿态适配器继续负责 ENU/FLU→NED/FRD。不同栈的 hover 数值不能互换；测试中的 0.313/0.531 仅为区分映射的示例输入，不在库内冒充实测标定或提供默认。

## 构建前冻结的私有 oracle fixture 协议

工具路径：`tools/check_position_pid_source.py`；构建前文件 SHA256 `fe23b230fb7a132096ce119d7056301e1c72e128d848d80b0ba26938d2cce8ce`。

主复核要求补持久证据后，仅扩充记录层，最终待运行工具 SHA256 `4f89450406fd7a2a0e82bb41c91aaad86b19bf5e1fd12458b0ed7a61c7a01260`。`--evidence` 要求不存在的新目录，保留协议、fixture 代码、实际 Python 源副本、编译 argv/版本/日志、Eigen 版本、每参数组输入/原 C++ 输出/逐样本 Python 比较 JSONL，以及结果或失败 traceback；超时也保留部分输出。清理临时二进制前记录其 SHA256。下述协议、fixture 字符串、案例、预算哈希均未改动。

`python tools/check_position_pid_source.py --describe` 只打印输入协议，不编译、不启动飞控/模型。其 canonical JSON（sort_keys=True、separators=(',',':')、UTF-8）SHA256：`076bd5bbd3502fe11eacc4189c21e24bbf1a300fe4daf5b4493710be35914f61`；ROS shell + UAVState shell + C++ fixture 字符串 SHA256：`9d4c5c388b76667e120310465ac374553af74839d56bef26667c958eb43baa7a`。

942 个固定输入：悬停 1、正负误差边界 12、积分饱和 600、移动参考 20、inactive 1、竖直/倾角限力 4、当前姿态投影 4、确定性正弦反馈轨迹 300。各在两套明确参数下运行，共 1,884 次原 C++ update。参数数组顺序为 mass/hover/Kp/Kv/Kvi/int_limit/tilt：`[2,.5,2,2,.3,.5,10]`、`[1.25,.75,1.5,2.5,.25,.02,12]`。逐样本比较积分3轴、限幅力3轴、roll/pitch/yaw3轴、归一化油门，共10量。全部判定固定为 `abs_error <= max(2e-6, 2e-7*max(abs(a),abs(b)))`；不得看结果后放宽。

oracle 直接 include 原 PID、controller_utils、math_utils、geometry_utils、printf_utils，运行真实 `/usr/include/eigen3`。只提供 ROS NodeHandle 参数读入 shell 和实际字段类型的 UAVState shell（position/velocity 为 float32，quaternion 为 double，mode 为 string），不模拟 ROS 运行时。预先 include 所有依赖，然后 `#define private public` 仅改变 PID 类可见性，读取原 F_des/int_e_v；未修改原函数体。fixture 明确将原未初始化积分置零，并在冻结 reset 行置零。输出日志通过临时 cout buffer 隔离，没有替换原数学函数。构建 g++ `-std=c++17 -O0`，临时目录自清理，超时分别 60s/30s；不链接或启动 FC/model/ROS 节点。

Fz=0、原未定义初始积分、ROS时序、物理悬停规律、飞控执行不属于此 oracle；前两项由纯 Python 拒绝/初始化检查覆盖，后三项需要正式后续集成验证。

## 验证状态

`python -m unittest validation.test_position_pid -v`：12 项通过。首次零竖直力负例因已有 Z 积分贡献而实际 Fz 非零，修正测试输入使其进入真实除零分支后通过；未修改算法规避失败。

主代理 RUN RELEASE 后，run1 数值比较全部通过，但其重新计算的三角函数输入在 Windows/WSL 间有26个末位差异（最大 1.1102230246251565e-16）；协议 SHA 为 `b6e353c7f99b5a04cb26cb4d29356ed7f091dfad5ddc2e2d917fb70cc7b4836c`，未达到已批准输入身份要求。原 `result.json` 不覆盖，追加 `validation/pid-source-20260909-run1/protocol-review.json` 明确 `accepted_frozen_protocol=false` 并逐项保存差异。不能把数值 pass 当作精确冻结输入验收。

修正输入消费方式：将 Windows 的原批准 canonical JSON 固定到 `validation/pid-source-20260909-protocol.json`，其 SHA 仍为 `076bd5bbd3502fe11eacc4189c21e24bbf1a300fe4daf5b4493710be35914f61`。工具新增必需 `--protocol`，先验其原始字节 SHA，再检查原 fixture 字符串、源码 pins 和容差均一致；Linux 直接消费该输入文件，不重新生成平台三角函数值。此时最终工具 SHA256 为 `a5ecfcf77063bd9faa37abb42e544345e7d1d398c813a0e4534b9808566a109b`。原案例与预算没有变更。

主代理重新核算两 SHA 并 RUN2 RELEASE 后实际命令：

```powershell
wsl -d Ubuntu-22.04 -- python3 '/mnt/c/Users/PC/Documents/odid编译/wksim/tools/check_position_pid_source.py' --protocol '/mnt/c/Users/PC/Documents/odid编译/wksim/validation/pid-source-20260909-protocol.json' --evidence '/mnt/c/Users/PC/Documents/odid编译/wksim/validation/pid-source-20260909-run2'
python -m unittest validation.test_position_pid -v
```

Linux 重现可在仓库根目录执行 `python3 tools/check_position_pid_source.py --protocol validation/pid-source-20260909-protocol.json --evidence validation/pid-source-new-run`；证据目录必须尚不存在，原输入文件需保留且不可重新生成替换。

run2 实际使用 g++ 11.4.0（Ubuntu 11.4.0-1ubuntu1~22.04.3）、Eigen 3.4.0；协议 SHA 与批准值完全一致。1,884 样本 × 10 通道全部通过，共18,840值，最大误差：积分 1.38778e-17、X/Y 力 2.2290918799683368e-7 N、Z 力0、roll/pitch 8.705038051504133e-9 rad、yaw与归一化油门0。原冻结 `abs=2e-6, rel=2e-7` 未放宽。

run2 `result.json` SHA256 `eb08f2cb3c0095069edc7d426ca6e31459b7229521943d34ba463f8da9101d00`；编译二进制 SHA256 `c98261e64741de7e68b9e8a7339c110222b23f3e4bda100e6ceb51b911f932f5`。全部原始输入/输出、逐项对照与实际源码副本在 `validation/pid-source-20260909-run2/`；`artifact-sha256.json` 自身 SHA256 `0a303647398881d8cf0910cb141832c3a2280b4e63d932172d04398a173f6970`。两个 comparison JSONL 各942行，实际Python源码副本与当前源码逐字节哈希一致；12项单元检查与 `git diff --check` 通过。小型原函数进程已退出，临时编译目录按协议清理，没有启动 FC/model/ROS。

#35 保持开放；这些证据证明纯算法与明示边界，配置/UI 和双栈定点/轨迹/预声明扰动的冻结物理预算仍由主线实现及验收。PID 的实际输出消费必须经已验收的姿态/推力出口，不能回退飞控位置环后仍标为外部 PID。
