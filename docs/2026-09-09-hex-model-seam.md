# #25 六旋翼模型静态合同与最小接入路径

2026-09-09 JST。**固定生成源码支持平面 Hex X，`ModelParam_uavType=5`，六电机顺序与固定 ArduPilot Hexa X 完全对应；固定 PX4 通用 Hex X 也具有相同编号和旋向。当前产品仍只有四通道适配与四旋翼显示，不能仅改一个配置值就运行六旋翼。**

本轮交付源码核查及只读[复现探针](../tools/probe_hex_model_source.py)。没有构建、加载或推进 native 模型，没有启动 SITL、ROS、UE，没有修改生产参数、物理、控制、调度、显示或默认准入 pin；#25 的飞行/显示验收仍未完成。#17/#24 已关闭不等于本票的六旋翼验收通过。这里的“候选合同”可作为下一实现的输入，不是已经发布的机型或真实机架标定。

## 固定来源与实读方式

直接读取 `Simulator/wksim_core/model.py`、`model_parameters.py`、[四旋翼报告](2026-09-09-quad-parameters-report.md)与[参数对应表](../validation/model-reference-provenance-20260907/parameter-correspondence.json)，再独立校验本机 ZIP 和原始生成 cpp/h 字节，没有从四旋翼飞行结果推导六旋翼。

| 输入 | 本轮验证的身份 |
| --- | --- |
| `MulticopterModel.zip` | SHA256 `d528b5d247e13d943f1eaa7a37fd3cb4d15c7e9bb7a6b0e5988a1423e59d05ed` |
| `Exp1_MinModelTemp.cpp` | SHA256 `a35d7c8f39c94f2db8c27b19affee5b66c1b001c63ded334ba83c99f8be54019` |
| `Exp1_MinModelTemp.h` | SHA256 `2d89ad1b492c5e70e80682a9f53896e0538260946a0180a2ca44e500ba1589bd` |
| ArduPilot `/root/wksim-ap-dds-yaw-state-4Wr27s/src` | HEAD `1511f27194f1dcc3728270883047bdf022b3fd53`；本文涉及的 7 个文件逐字节等于固定 commit |
| PX4 `/root/wksim-px4-state-ONa1Kw/src` | HEAD `d6f12ad1c4f70ad3230afd7d86e971421e02fef4`；本文探针涉及的 5 个文件逐字节等于固定 commit |

生成头标明模型 **11.0 / R2022b**，生成时间 2025-12-08，原生成器验证栏为 `Not run`。本文行号均相对上述未参数化的原始源字节。ZIP 路径仍是 `E:/rflysimtools/RflySimAPIs/4.RflySimModel/1.BasicExps/e0_MinModelTemp/MulticopterModel.zip`。原始厂商代码仅临时保存在本机，不进入仓库。

仓库结构导航先实读 Codebase Memory：ready，50,865 节点 / 165,157 边；图定位 `Lockstep` 和 `ApplyPacket`，随后读真实源码。精确覆盖报告中 `model_parameters.py` 为 not_tracked，其余所查生产文件为 metadata_changed；没有用旧图证明完整性，也没有为本轮静态文档工作全库重建。新的生产结构查询仍须按项目规则检测/刷新。外部生成源和 WSL 飞控源不在该项目图内，均直接实读。

## 可冻结的平面 Hex X 合同

生成 cpp **3874–3899** 包含真实数组 `d[10]`、`e[80]`、`c[80]`；**4755–4790** 给出机型和旋向注释；**4823–4832** 实际选择 `d[uavType-1]` 及列优先地址 `10*input_index+uavType-1`。因此不是按连续六个浮点数误读表。`uavType=5` 选择六旋翼 X；6 为六旋翼 +，7 为三轴共轴六旋翼，后两项不属于本候选，也不从此表存在推断其飞行通过。

角度按 FRD 平面计算：`x=R*cos(angle)`、`y=R*sin(angle)`、`z=0`，x 向前、y 向右。下表位置使用源默认 `R=0.225 m`，展示值作舍入，探针保留原浮点导出值。

| 输入下标 | 位置 | 角度 ° | x / y m | 源旋向符号 | 从上方看旋向 | RPM 输出下标 |
| ---: | --- | ---: | --- | ---: | --- | ---: |
| 0 | 正右 R | 90 | 0 / +0.225 | +1 | CW | 16 |
| 1 | 正左 L | 270 | 0 / −0.225 | −1 | CCW | 17 |
| 2 | 前左 FL | 330 | +0.194855715851499 / −0.1125 | +1 | CW | 18 |
| 3 | 后右 RR | 150 | −0.194855715851499 / +0.1125 | −1 | CCW | 19 |
| 4 | 前右 FR | 30 | +0.194855715851499 / +0.1125 | −1 | CCW | 20 |
| 5 | 后左 RL | 210 | −0.194855715851499 / −0.1125 | +1 | CW | 21 |

源注释定义 −1=anticlockwise、+1=clockwise。更可靠的物理符号依据是实际方程：每个电机 `T=Ct*omega²`，FRD 反扭矩 `Mz=−Cm*omega²*source_spin`；滚转/俯仰力矩为 `−R*sin(angle)*T`、`R*cos(angle)*T`（cpp **4833–4855**）。这是机体受到的反扭矩，不能把旋翼旋向直接当作机体偏航力矩符号。源码还实际累计陀螺力矩项；4753 的旧注释与执行式不一致时，以执行式为准。

输入仍是 **16 个有限 `[0,1]` 归一化命令**。cpp **4641–4702** 将 `inPWMs[0..5]` 逐一送入 MotorNonlinearDynamic1–6；**4731–4738** 再逐一组装旋翼角速度。候选必须拒绝非零的 **6..15** 通道，不能继续四旋翼适配中的静默截断。native 输出仍是 120 doubles；cpp **7851–7862** 明确映射六个电机到 `output[16:22]`。保持 1 ms 固定积分和每载具独立进程边界。

`ModelParam_uavMotNumbs` 在参数对应表中明确没有同名生成参数，本次提取也只有 **22 个具名 initializer**。电机数量由机型表产生，不能添加一个虚构的可写数量字段。生成参数结构是固定 `P_Exp1_MinModelTemp_T`，不是可变长六电机组件列表；电机/旋翼系数是所有电机共用的标量。

## 参数候选与未标定边界

最小独立静态模型可以只在新构建目录中，将唯一的 `ModelParam_uavType` initializer 从 3 改为 5，保留其他源参数。下列默认数值能明确冻结为**源模板数值**，但没有证据称它们是某台真实六旋翼的质量惯量和动力标定。

| 参数组 | 源模板值与单位 |
| --- | --- |
| 质量、惯量 | 1.515 kg；FRD 对角惯量 `[0.0211,0.0219,0.0366] kg·m²`，交叉项 0 |
| 半径 | 0.225 m，重心至电机 |
| 共用电机 | Cr=842.1 rad/s/command，Wb=22.83 rad/s，T=0.0214 s，Jm=0.0001287 kg·m²，minThr=0.05 |
| 共用旋翼 | Ct=1.681e−5 N/(rad/s)²，Cm=2.783e−7 N·m/(rad/s)² |
| 阻力、气动中心 | Cd=0.055 N/(m/s)²，CCm=`[0.0035,0.0039,0.0034]` N·m/(rad/s)²，Dearo=0.12 m |
| 初态 | 位置、欧拉角、机体系速度/角速度均零；ModelInit_RPM 固定零，不开放其非零输入单位 |
| 环境 | GPS `[40.1540302,116.2593683]` °，envAltitude=−50 m |

参数布局/默认值来自 cpp **80–196**、header **543–553** 附近；不是从文档中的“六旋翼”名称自动推算惯量。若保留这些值，候选应明确命名为模板 Hex X。不能把 #24 的 0.5–5 kg 编辑范围称为已验证六旋翼飞行包线，也不能根据电机数按 6/4 自动缩放质量或惯量。

`ModelParam_3DType` 与 `uavType` 是不同字段：前者默认 3，cpp **7750** 只复制到 vehicleType，**7821** 输出到 Vehicle[1]；本源没有六旋翼显示枚举注册表。不能猜它也应改为 5。六旋翼 UE 显示应由新配置身份及明确的六旋翼元数据选择，并记录保留的 source-native 3DType；不能把它误当作已经正确表达六旋翼的显示类型。

## 双栈适用配置：有源码基础，尚无六旋翼运行证据

**ArduPilot：**固定 [AP_MotorsMatrix.cpp](https://github.com/ArduPilot/ardupilot/blob/1511f27194f1dcc3728270883047bdf022b3fd53/libraries/AP_Motors/AP_MotorsMatrix.cpp#L775-L805) 的 Hexa X 六行是 `90,−90,−30,150,30,−150` °，旋向 `CW,CCW,CW,CCW,CCW,CW`，与上表逐项相同。`add_motors` **561–566** 用数组下标作为电机号；第三列 `[2,5,6,3,1,4]` 是测试顺序，不能拿来重排运行输入。

固定 `AP_Motors_Class.h` **57/80** 给出 `FRAME_CLASS=2`、`FRAME_TYPE=1`。`Tools/autotest/default_params/copter-hexa.parm` / `copter-X.parm` 也分别设这两个值。固定 `SRV_Channel.h` **82–87** 的 Motor1–6 功能号是 33–38；`AP_Motors_Class.cpp` **96–104** 按 motor function 输出，**214–220** 设置默认通道。未来独立参数文件应显式冻结 `SERVO1_FUNCTION..SERVO6_FUNCTION=33..38` 与已验证的 1000–2000 PWM 端点，并在实际启动后读回，避免持久化参数意外重映射。AP 的 yaw factor CW=−1、CCW=+1，恰好是源反扭矩符号。

**PX4：**固定 [6001_hexa_x](https://github.com/PX4/PX4-Autopilot/blob/d6f12ad1c4f70ad3230afd7d86e971421e02fef4/ROMFS/px4fmu_common/init.d/airframes/6001_hexa_x) 设 `MAV_TYPE=13`、`CA_ROTOR_COUNT=6`，六个位置按序为 `(0,.5),(0,−.5),(.43,−.25),(−.43,.25),(.43,.25),(−.43,−.25)`；KM 为 `−,+,−,+,+,−`。固定 `module.yaml` **184–225** 给出 axis-z 默认 −1、CT 默认 6.5、KM 默认 +0.05，并说明 KM 为 Torque/Thrust，CCW 正、CW 负。`ActuatorEffectivenessRotors.cpp` **195–204** 执行 `moment=ct*(position×axis)−ct*km*axis`，其符号与本模型一致。

但这不是精确同一个几何/动力参数集合：6001 的斜臂角偏离精确 30° 约 **0.17352003°**，半径约 0.5 而不是 0.225；默认 `|KM|=0.05`，源模型 `Cm/Ct=0.016555621653777514 m`。后续配置可按上表精确坐标和 `KM=−source_spin*Cm/Ct` 建立候选，再验证分配/闭环效果。PX4 的 CT 作用于其输出信号，模型 Ct 作用于 rad/s，两者不能直接以同名互换；归一化、推力曲线和控制增益须在六旋翼实验中明确记录，不宣称本轮已完成标定。

**不能直接运行 `PX4_SYS_AUTOSTART=6001`。**该源码的 POSIX `rcS` **218–239** 只寻找 `etc/init.d-posix/airframes/<id>_*`；本轮实际目录里没有 `6001_*`，已有 `3011_jsbsim_hexarotor_x` 和 `10044_sihsim_hex` 分别属于另一仿真后端。应使用当前 simulator_mavlink 路径建立独立六旋翼启动脚本/配置，明确 Motor1–6 输出功能及其通道，并保留当前 DDS/无 Gazebo 模块边界；不能改选 JSBSim/SIH 后称为自主模型运行。`SimulatorMavlink.cpp` **116–127** 将 `actuator_outputs[i]` 按通道复制到 HIL controls，只有正确的输出功能配置才能形成上表的直通映射。

两个飞控的源码组合均有平面 Hex X 依据，本轮没有发现可据以标成“不适用”的理由。当前状态应是“待实现与运行验证”；Hex+、共轴 Y6、其他电机排列均不在本合同内。

## 当前接缝与下一轮最小工作

以下均实读实际源后确认；这里只列需要工作的具体边界，不创建通用组件库。

| 已有文件 | 当前限制 | 下一轮所需的最小变化 |
| --- | --- | --- |
| `Simulator/wksim_core/model_parameters.py` | 严格 Quad X、只改质量、拒绝 4..15 非零 | 新的具名 Hex X 配置及唯一 uavType 参数化 recipe，保存/导入/身份和构建字节验证；默认 Quad 配置保持可独立使用 |
| `Simulator/wksim_core/model.cpp` / `model.py` | native 桥已接收 16、输出 120；模型参数共享 static | 沿用桥接口与独立进程，不因六旋翼改 native ABI；新配置初始化前读回 uavType、质量、惯量等冻结项 |
| `Simulator/wksim_core/ap_json.py` | decode_servos 只验证/归一化 `pwm[:4]` | 明确 Hex 配置验证六通道、未用通道规则及 PWM 端点，保持已有序号/重复包/时钟保护 |
| `Simulator/wksim_core/px4_mavlink.py` | actuator_commands 只接收 `controls[:4]` | 明确 Hex 配置验证六通道及 output function 映射，保持 lockstep/停流保护 |
| `Simulator/wksim_core/state_stream.py` | METADATA 固定 quad-X / FR,RL,FL,RR；emit 切片 `[16:20]` | 定义有身份的 Hex X 状态合同，六个 RPM、上表顺序；沿用新鲜度和单调性校验 |
| `Simulator/ue55/Source/WksimVisual/WksimVisualGameMode.cpp` | BeginPlay **190–212** 构造 P450 四旋翼；ApplyPacket **403–439** 验证 quad-X 与四个 RPM | 独立 Hex X 机体和六个旋翼几何，按实际六路 RPM/符号显示；正确接收六旋翼合同并对错误构型拒绝 |

下一资源窗口按以下顺序实施，前一层取得证据后再进入后一层：

1. **配置与 native 静态响应。**新目录、新身份、精确源 pin；只参数化明确 initializer，构建 manifest 记录原始/修改源/包装/库/配置 SHA、编译器、命令和 1 ms profile。初始化前读回配置。先静止与六路相同输入，再对每个电机做独立小扰动。预声明以初始 FRD 零角速率下的 roll/pitch/yaw 加速度符号核对上表，尤其是第 5/6 个输入及相反反扭矩；同时保存六路 RPM、完整 120 输出、冷重置和配置回读。这一步不需要 FC/ROS/UE，当前尚未执行。
2. **单栈逐个闭环。**先将独立 AP Hex 参数与六通道后端接入单载具，再准备独立 PX4 simulator_mavlink 六旋翼脚本；每次使用新参数存储/进程空间，不复用当前主线运行实例。分别保留启动参数读回、飞控二进制/源码/补丁身份、原始执行器与真值，并完成起飞、保持、航点、降落、冷重置。几何/旋向成立不能代替闭环结果，失败原样留证。
3. **UE 六旋翼表达。**在资源释放后采用上表精确电机位置构造六臂/六旋翼几何，保留原权威 Actor 姿态转换；源中没有真实机体外形、桨直径或厂商 Hex 资产 pin，可先做诚实标明的示意机体。检查前向标识、六个旋翼、实际六路 RPM 与 CW/CCW 符号，单电机低速可辨方向验证后再录制飞行/重置；不能沿用 P450 四旋翼占位物冒充六旋翼。UE 资产操作需另按资产技能和项目命名规则执行。

本轮没有一个已实现的 `hex build/run` CLI，因此不提供会误执行默认 Quad 的伪复现命令；上面的步骤描述的是待写接缝，而下面的命令已真实运行且只读。

## 本轮实际复现与结果

在 Ubuntu-22.04 中，仓库根目录执行：

```bash
python3 tools/probe_hex_model_source.py \
  --archive /mnt/e/rflysimtools/RflySimAPIs/4.RflySimModel/1.BasicExps/e0_MinModelTemp/MulticopterModel.zip \
  --ap-source /root/wksim-ap-dds-yaw-state-4Wr27s/src \
  --px4-source /root/wksim-px4-state-ONa1Kw/src
```

探针退出 **0**：ZIP/cpp/h pin、22 项布局、真实列优先表选取、六路输入/RPM、AP 六行顺序/旋向、两栈固定 commit 及所读文件原始字节、PX4 默认轴/CT/KM 均通过；它报告 PX4 几何差异和 POSIX 6001 缺失，不把这些差异藏入“相同”结论。额外错误 ZIP 负例在访问 FC 路径前抛出 `Archive SHA256 differs`。没有导入 `ctypes`，也没有执行编译器、模型或飞控进程。

私有证据目录：`C:/Users/PC/AppData/Local/Temp/wksim-hex-static-qf_zk7m8/`。`contract.json` SHA256 为 `febef0e502f4cb55187a8718a7ce3d21842b3ca57e19e7069af7273b3e6cf385`，包含全部静态数值和 12 个飞控文件哈希；`negative-check.json` 保存错误 ZIP 拒绝结果。目录另有原生成源的私有副本，不得将整个目录打包入库。上述静态结果不改变 R1 numerical_failed、G6 未通过的既有边界，也不满足 #25 的 native/双栈/UE 运行验收或关闭条件。
