# #25 独立六通道运行接缝与静态启动候选

2026-09-09 JST。新增 [hex_physics.py](../tools/hex_physics.py)、[hex_launch_plan.py](../tools/hex_launch_plan.py) 和 [10 项纯测试](../validation/test_hex_physics.py)。六路执行器按固定 Hex X 顺序接入原有 AP/PX4 物理循环，每 1 ms 保存保持输入与完整 120 个 native 输出。**本轮没有加载或推进 native 模型，没有构建或启动 FC、ROS、UE；#25 双栈闭环、冷重置及 UE 六旋翼验收仍未完成。**

`Simulator/wksim_core/ap_json.py`、`px4_mavlink.py`、`model.py`、`model.cpp`、`state_stream.py`、Control、默认 pin 与封存构建均未修改。新工具是明确的实验入口，既不注册生产配置，也不绕过原四旋翼准入。原有 `StateWriter(None)` 保持停用，不发送错误的 quad-X/四路 RPM 显示数据。

## 六通道接缝

AP 使用原始 `decode_servos` 核验 `<HHI16H` 长度、magic 18458、非零 rate 和前四 PWM；新增第 5/6 路同样的 `0 或 1000..2000` 检查。前六路逐项变成 `max(0,pwm−1000)/1000`，不使用电机测试顺序重新排列。收到的原始 16 PWM 与报文十六进制字节保留，6..15 源输出不参与物理输入，实际 native 对应输入强制为零。原 `Lockstep` 仍决定重复帧缓存回复、32 位连续帧及环绕、断序拒绝；原 UDP `serve` 仍只在首个有效报文后绑定 peer 并忽略其他地址。

PX4 仍由原 pymavlink 解析完整 HIL_ACTUATOR_CONTROLS 报文。已解锁时验证前六项有限且在 `[0,1]`，保持源输出数值直通，6..15 强制零；没有额外的 `[-1,1]→[0,1]` 变换。未解锁时沿用原来全零行为，包括无效/NaN 电机值不进入模型。报文 controls 长度必须为 16。原 `serve` 保留 lockstep flag、重复时间戳、倒退时钟、连接断开和五秒停流保护，IMU 仍为 250 Hz，每个传感器帧推进四个固定 1 ms 子步。启动阶段尚未收到执行器时的原循环也不改变。

依赖替换仅在专用进程的 context manager 内作用于 `Model` 与该栈的解码函数，退出/异常时恢复引用。没有网络对象或全局 socket 补丁；只有纯测试使用假的连接对象。不要将此 context manager 用于多线程共享服务。

### 身份与逐 tick 证据

加载前先执行已有 `verify_build`，验证配置、源参数化 recipe、wrapper recipe、全部 manifest 产物哈希，再要求以下本轮固定身份。`HexModel` 随后继续执行初始化前全部参数读回、Python/native 未用通道拒绝和一进程一个生命周期约束。

| 对象 | 固定身份 |
| --- | --- |
| native 库 | `/root/wksim-hex-candidate-private/build-ihnane6f/libwksim_hex_candidate.so` |
| 库 SHA256 | `b10ef333129b44ce41d2d8d944a1e3d1161db9201bb1aea9eca88e726a5a7c9c` |
| 配置身份 | `sha256:d703da7f888e7110e402aa32ff911cabcb24e0b01afb8bbf4c9ec1ccb897276a` |
| 静态启动方案身份 | `sha256:319c5cba50eb11b81f70ac3ade707879c2fdba252335aa039674e93b9168e1a0` |

原始 JSONL 的 start 保存配置、库身份及接缝/构建器/原适配器/模型/显示源文件哈希；initialized 保存实际初始化前参数读回。每条 step 保存整数 tick、调用组、组内子步、实际 input16、output120、保持执行器报文字节和墙钟观察时刻。六路 RPM 直接位于 `output120[16:22]`。初始 PX4 零输入的 `held_packet=null`，不伪造来源。

AP actuator 事件表示通过六路解码的收到报文，写入发生在原 Lockstep 的重复/断序判断前；它不单独证明物理已推进。只有关联 step 才证明输入用于模型。PX4 事件仅在原时钟/flag 校验后产生，重复包被原循环处理，因而不会作为新的输入事件重复记录；本工具不是完整网络抓包。故障写入 end 类型/原因，保留此前记录；SIGTERM 的有序退休会关闭模型和刷新文件。操作系统强杀仍可能截断缓冲末尾，不能将缺失轨迹算成通过。

新入口的未来用法（本轮未执行）：

```bash
python3 tools/hex_physics.py --stack arducopter \
  --library /root/wksim-hex-candidate-private/build-ihnane6f/libwksim_hex_candidate.so \
  --config /root/wksim-hex-candidate-private/build-ihnane6f/config.json \
  --port 19002 --trace "$run/truth.jsonl" --raw "$run/physics-1ms.jsonl"
```

PX4 用 `--stack px4 --port 4581` 对应既有 instance 21 的 `4560+instance`。路径必须为每次实验独立新文件；不传 duration 时由上级 supervisor 拥有寿命，已有停流保护仍生效。此命令仅启动物理端，不能据此声称已有完整六旋翼实验启动器、生产准入或飞行结果。

## 静态飞控启动方案

`python tools/hex_launch_plan.py` 仅输出 JSON，不读写参数存储、不启动子进程。输出有所有参数值、AP 参数文件文本、PX4 环境字典和 canonical 方案身份。方案称为 **source-template Hex X custom candidate**，不是任何真实机架标定。

### AP

固定源 `1511f27194f1dcc3728270883047bdf022b3fd53` 的 Hexa X 使用 `FRAME_CLASS=2`、`FRAME_TYPE=1`，输入顺序 R,L,FL,RR,FR,RL。方案冻结 `SERVO1_FUNCTION..SERVO6_FUNCTION=33..38` 和各路 MIN/MAX=1000/2000，以及 `MOT_PWM_MIN/MAX=1000/2000`。

未来新默认参数文件顺序应为原 `copter.parm`、方案中的独立 Hex 参数文件、最后加载的 DDS 参数文件；不能把原 `arducopter-quad-x.parm` 留在列表中。DDS 动态默认项依然放最后，避免既有 late-created 参数加载问题。其余原 JSON/rate=1000/端口与 DDS 路由沿用；每个 epoch 使用新 EEPROM 目录并在解锁前读回全部冻结参数。

本轮只读实际 AP `/root/wksim-ap-dds-yaw-state-4Wr27s/build/sitl/bin/arducopter` SHA256 为 `98c003de2a328b3aeb5813583070f4640dc6c935bde9f42fedaaaefad39ac9b5`。它是待复用的已封存原生候选身份，不是新 Hex 已飞行身份。

### PX4：保留 10016 引导，显式覆盖六路

实读固定源 `d6f12ad1c4f70ad3230afd7d86e971421e02fef4`：`rcS` 在参数重置之后、加载 airframe 之前，通过 `PX4_PARAM_*` 执行 `param set`；`10016_none_iris` 与它引用的 `rc.mc_defaults` 只对相关机型/几何/输出项使用 `param set-default`。因此可以不修改封存 PX4，以显式参数覆盖默认 Quad 设置。

方案给出 `PX4_SYS_AUTOSTART=10016`、`PX4_SIM_MODEL=none_iris`，清空 `PX4_SIMULATOR`/`PX4_SIM_HOSTNAME` 并选择 localhost；保留 simulator_mavlink 路线。**POSIX 目录没有 6001，不能声称 stock Hex startup 或直接设 6001。** 源通用 `6001_hexa_x` 只作为编号/符号的来源参考。

所有 `PX4_PARAM_*` 必须在干净、仅本实验的环境内应用；不能在继承有未知 PX4_PARAM 的环境中仅增量覆盖。既有 DDS/MAVLink/实例参数与私有 Linux namespace/进程组监管仍由未来实验启动器提供。其余配置为：

- `MAV_TYPE=13`、`CA_AIRFRAME=0`、`CA_ROTOR_COUNT=6`、`CA_R_REV=0`。
- 六路位置由半径 0.225 m 和角度 `[90,270,330,150,30,210]` 推导，PZ=0；推力轴 `(0,0,−1)`，TILT=0。
- KM=`−source_spin*Cm/Ct`，`Cm/Ct=0.016555621653777514 m`；旋向 `[+1,−1,+1,−1,−1,+1]`。PX4 参数按 FLOAT32 存储，未来回读必须按类型验证，不能要求十进制字符串逐字相同。
- `CA_ROTOR0_CT..CA_ROTOR5_CT=6.5` 保留固定 PX4 默认分配系数。该 CT 作用于输出信号，与 native 的 `1.681e−5 N/(rad/s)²` 单位/含义不同，不能直接替换或称为动力标定。
- `PWM_MAIN_FUNC1..6=101..106`，7..16=0，明确通道直通与未用输出。

本轮逐项检查实际构建 `parameters.xml`：方案中的全部 PX4 参数存在，含六路各位置/轴/CT/KM/TILT 和 16 项 PWM_MAIN_FUNC；没有缺项。该无 Gazebo 候选的 `SIM_GZ_EN` **不存在**，方案不生成这个无效覆盖项。`px4-rc.simulator` 的 else 路线仍启动 `px4-rc.mavlinksim`。

未来 FC argv 可沿原 `runtime.launch_spec` 形状使用已封存 binary、`-d <px4_root>/build/px4_sitl_default/etc`、`-t <px4_root>/test_data`、`-i 21`、`-w <fresh-private-fc-dir>`，加上上述显式环境；不需要新编译或修改 airframe 文件。完整候选准入还需将此 argv、环境、参数文件、运行脚本、DDS/控制身份及 Hex 物理脚本作为**新的实验清单**封存；不能修改或冒用原 Quad 的生产 preflight pin。

### 本轮实际只读身份核查

以下文件逐字节等于上述 PX4 commit；其中前五个还逐字节等于实际 `build/px4_sitl_default/etc` 对应运行文件。

| 源文件 | SHA256 |
| --- | --- |
| `init.d-posix/rcS` | `8f7c3edd7ab4622f42f30b281584464b325c947e21152c4fcac0cb4acba17705` |
| `init.d-posix/airframes/10016_none_iris` | `593880f1b72c76195bc0d8d8c487bfd402e2fb0da24f42ec2298d7c3040baf29` |
| `init.d/rc.mc_defaults` | `7b2cd6724104c10ffd048b53656e36e61aaeccfbb9e9c1ab09ad0261f478f711` |
| `init.d-posix/px4-rc.simulator` | `6a1c29d1d5ab59e726914072ac2bdaadc23bc15750104fa62a761e4f577445b2` |
| `init.d-posix/px4-rc.mavlinksim` | `c73f2b7fb9e34cecb5f91ee2c235d83104770828709d357b1e796f74040d80d1` |
| `src/modules/control_allocator/module.yaml` | `92a1538b75173b1902135d1e4091c921f63bb23d626233ee7f45dd7b7eeb07aa` |

PX4 根为 `/root/wksim-px4-state-ONa1Kw/src`，实际 binary SHA256 `93b4ebe0d83a5897131ec24ee58d732c8999972bb7730f429fc396bc8d10602a`，实际 parameters.xml SHA256 `639ef45050f77593983c94a37b15bb9a87c089a0533ac62f11c0b2756d827d7b`。Hex 库本輪 `verify_build` 和期望库 SHA 校验再次成功，未调用 CDLL 或 initialize。

## 验证与下一次飞行冻结边界

`python validation/test_hex_physics.py -v` 实际通过 10/10，约 0.013 s。报文由源协议一致的 `<HHI16H` 与 pymavlink v2 encoder 构造，并经真实 parser/原 Lockstep/原 serve 消费。它们是纯测试 wire fixtures，**不是飞控采集数据**。覆盖旧四路与新六路差异、六个 active channel 的边界/非有限拒绝、未用通道零化、AP frame wrap/duplicate/discontinuity/peer、PX4 CRC/分片/duplicate/backward/lockstep flag/disconnect/timeout、原四子步保持、观察器逐毫秒记录，以及错误库在加载前拒绝。

下一次真实实验前仍需单独冻结并封存完整 flight protocol：两栈各用独立新参数目录，真实启动参数回读、原始执行器、1 ms 全输出、原生反馈和公开任务证据；按起飞→保持→航点→降落→确认落地→冷重置→重复同一任务的顺序执行。位置/姿态/保持时间/重置通过条件必须在首飞前写入该协议并取得独立身份，本静态接缝报告不新增或拟合飞行容差。

UE 层需另建确实有六臂、六旋翼及前向标识的几何，接收新的 Hex 身份和实际六路 RPM/旋向，不能沿用 P450 四旋翼 Actor 或猜测 native `3DType=3` 意味着已支持 Hex。没有这部分真实显示和两栈任务/冷重置证据，不能关闭 #25，也不能扩大本次源模板数值的适用性。
