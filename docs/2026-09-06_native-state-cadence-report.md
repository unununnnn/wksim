# 原生状态新鲜度修复与独立 PX4 SITL 候选

本轮在真实双飞控闭环中复现了 PX4 estimator 状态超龄导致的降落失败，完成独立 PX4 重建、恢复入口修正及原子交接修正。最终当前源码的 PX4 Agent 失联、AP Agent 失联后慢速降落、健康暂停/完整公共任务三场均通过原始数据审计，审计重复结果逐字节一致。**完整 Goal、G2、#8/#19/#20/#22 仍开放；新候选尚未接入正式产品配置。**

承接[上一轮DDS审计收口](2026-09-06_joint-dds-recovery-report.md)，沿用已批准的1ms权威tick、4ms输入屏障、2s原生状态墙钟新鲜度及5s显式恢复上界。本轮没有改变这些数值、健康标志、原生解锁检查或任务位置/速度门槛。

## 根因证据与修复

旧样本 `kj284sh1` 的原始CDR/ULog已提示低频estimator状态可能超龄，但缺少Control实际接收时刻；不把旧推测追溯当作当时已证明的结论。本轮通过仅在独立实验中启用的 `tools/debug_px4_native_state.py`，记录原方法实际调用时的新鲜度结果、各源接收年龄、原生状态CDR及就绪变化。原回调、状态方法和新鲜度方法各调用一次，观察器不发命令、不替换判断。

`joint-public-flight-acl9ohp6` 在降落阶段加入有界慢速调度，复现了实际 `Task` 的 `Public state invalid or disconnected during scene task`：

| Control检查时的源 | 实际接收年龄 |
|---|---:|
| status | 1.351903s |
| position | 0.042319s |
| attitude | 0.017942s |
| GPS | 0.236439s |
| estimator | **2.004633s** |

当时 `connected=true`，只有estimator越过2s；位置/速度有效位、GPS fix、tilt/yaw、非dead-reckoning及非failsafe条件均正常，generation保持7，时钟未回退。失败发生于实际AUTO.LAND；新Task随后按既定规则失败。对应原始检查与回调来源在[诊断结果](../validation/joint-public-flight-acl9ohp6/native-state-inspection.json)，模型/执行器/传感器数据继续保留。

固定PX4的 `EKF2::PublishStatusFlags` 平时每1仿真秒发布，变化时立即发布；其已有DDS配置上限为5Hz。慢速推进时，1仿真秒可能超过2墙钟秒。候选补丁将周期改为200ms，保持即时变化发布、健康内容和原生时间戳语义。原2s判断继续执行，没有过滤无效样本。

诊断调度只在AUTO.LAND中按4tick循环起点安排12ms墙钟周期，用于放大原有慢速条件，不是正式倍率产品或性能预算。最终对照 `c8brdmu4` 的开始标记之后约0.3354 sim秒/墙钟秒，其中还包含离开LAND后的原速末段；完成屏障之间的间隔也不能当作循环起点间隔。此窗口的estimator实际接收最大间隔为 **0.624663s**，降落正常完成。全场最大间隔包含故障冻结期，不能与活动任务新鲜度混算。

Humble本机接口仅返回DDS source/received时间，不提供逐消息publisher GID。工具明确记录这一缺失，现场发现的GID另列，不冒称它是回调携带的来源证明。最终检查还复现CDR偏移23、41–43的非字段填充差异，解码字段完全相同，见[填充证明](../validation/native-state-observation-20260906/cdr-padding-proof.json)。观测器比较全部解码字段的精确表示，保留NaN无效值；原始CDR仍原样保存。

## 独立构建与运行依赖

重建揭示原固定PX4实际链接 `libgz-transport13` / `libgz-msgs10` 等库，见[原二进制依赖](../validation/native-state-observation-20260906/baseline-linked-libraries.log)。过去“不启动Gazebo进程”的记录仍成立，但不足以证明没有Gazebo运行库依赖。

在新私有源副本中，另一个补丁去掉SITL板配置的gz_msgs/gz_bridge/gz_plugins，保留自主物理使用的原生MAVLink仿真接入。原固定构建、源目录、全局库和厂商安装保持不变。首次仅改频率的 `cNIif6` 仍链接libgz，未用于飞行；新的准入会拒绝它。

| 项目 | 最终身份 |
|---|---|
| PX4来源 | `d6f12ad1c4f70ad3230afd7d86e971421e02fef4` |
| 独立PX4清单 | `/root/wksim-px4-state-ONa1Kw/wksim-build.json` |
| PX4清单SHA256 | `d7e905b35250d184e185ada70e3fe43f0223f1c605832d81c3c58eeb123d4cb6` |
| PX4固件SHA256 | `93b4ebe0d83a5897131ec24ee58d732c8999972bb7730f429fc396bc8d10602a` |
| Control清单 | `/root/wksim-joint-control-8xt3WC/build.json` |
| Control清单SHA256 | `28c58fb755f9ef9c0a207db67517f90da2fde65379f4b4207c7aa90197302492` |
| AP清单 | `/root/wksim-ap-clock-stop-OXQqdR/wksim-build.json` |
| AP清单SHA256 | `f347ba252fbfc33bc92baffba08660f33c3a0e4462e90177ba84bdc11408660a` |

PX4清单覆盖42,012个源文件、40个Git仓库，逐项核对参考与候选。除两处已声明源修改及省略旧运行文件清单外，没有其他源内容差异。全部生成运行文件、alias、构建日志和动态依赖纳入封存；合法空 `rc.serial` 保留其真实字节身份，固件和alias仍要求非空。外部清单SHA必须明确提供，启动前重新枚举核对。

候选只链接系统C/C++运行库及ELF加载器。最终三场均在运行初期和任务完成后保存实际 `/proc/<owned-pid>/maps`，核对进程身份及映射哈希，未加载Gazebo、ignition或MATLAB库。每场原始审计同时复核封存清单、当前实际源码、固件和加载映射。构建入口及两个补丁见[PX4补丁说明](../patches/px4/README.md)。

工具版本为Ubuntu22.04.5、Python3.10.12、CMake3.22.1、GCC11.4.0、Git2.34.1，见[版本记录](../validation/native-state-observation-20260906/tool-versions.log)。未复制或分发厂商模型资源；Prometheus固定上游与原ROS1基线保留。

## 同时修复的恢复与交接问题

- **恢复状态快照会变化。** `a04c93yc` 中物理就绪确认时尚无failsafe，新Task读取时已出现。原条件offer使Task一直等待。现在新PX4恢复任务明确选择公开AUTO.LOITER入口，等待原生确认/真实健康后再请求COMMAND_CONTROL；动作仍是新run/control/request身份下明确授权的新任务，不恢复旧任务、不清除飞控标志。每个新请求均与实际发送日志、原始DDS ACK事件和受理/接管确认关联。
- **定位就绪不覆盖接管全部前提。** `0l_skmzi` 已收到AUTO.LOITER原生确认，后续接管仍被真实节点以 `missing_home_or_landed_state` 拒绝。恢复确认现在同时要求控制器home已初始化、原生 `flying=true` 且新鲜，并在ACK报告；5s恢复上界不变。
- **交接文件可能被读到半写入状态。** `n4njgjkm` 起飞前读取刚创建的空 `go.json` 而失败。`save` 现先写完同目录临时文件，再原子替换。确定性读者窗口测试覆盖首次发布和已有文件替换；非有限启动数据的真实无效标记继续保留。
- **请求编号需要预留LAND空间。** 显式原生保持会增加一次请求，现提前按实际操作序列校验uint32 LAND command_id上限，超界时不发送任何请求。

上述失败、先失败再通过的接缝测试及源码均保留；没有用重试同一拒绝命令、强制解锁或放宽数值门槛解决它们。

## 最终当前源码实测

三场均使用ONa1Kw PX4、8xt3WC Control和固定AP候选，模型/FC/Control及成功的新Task正常退出0；故障实验中的旧Task自然失败退出1。Agent中断与清理退出另记，不能混称全部Task都成功。

| 场景 | 原始目录 | 共同tick | 显式恢复墙钟秒 | 自建进程组 |
|---|---|---:|---:|---:|
| PX4 Agent中断/新任务降落 | `joint-public-flight-8k0pfleo` | 63020 | 0.166935 | 15 |
| AP Agent中断/慢速降落 | `joint-public-flight-c8brdmu4` | 64452 | 2.316231 | 13 |
| 健康暂停/单步/完整任务 | `joint-public-flight-8_xg9ibk` | 69032 | 不适用 | 10 |

两个故障场景在故障/仅Agent重连、尚未显式恢复时均增加0个物理步。两个旧Task失败；AP新请求4/5/6，PX4新请求4/5/6/7，每个请求都有自身原生ACK与公开受理证据。新任务2仿真秒保持期间，AP/PX4最大位置误差/速度分别为：

| 场景 | AP | PX4 |
|---|---|---|
| PX4 Agent中断 | 0.03737m / 0.03104m/s | 0.29489m / 0.40512m/s |
| AP Agent中断 | 0.05586m / 0.04211m/s | 0.08483m / 0.03921m/s |

健康场在51440tick暂停4.00164s，仅四步至51444，再暂停4.00206s；显式继续后在51948收到双Control新原生确认。原六条公共输入完成航点/降落，两机同时高于1m共14020tick，即 **14.020仿真秒**。AP/PX4航点驻留最大物理误差为0.19032/0.46090m。它们是既有任务门槛，不是G6动力学等价预算。

最终[集成记录](../validation/native-state-observation-20260906/integration.json)包含三份完整审计及重复哈希；每份重复执行后逐字节一致。最终6个证据篡改负例均在对应门拒绝，见[负向结果](../validation/native-state-observation-20260906/final-audit-negatives.json)。

## 回归与全部尝试

| 检查 | 结果 | 日志目录 |
|---|---|---|
| 当前源接缝 | 64项：58通过、6跳过 | `scene-lifecycle-checks-MoYmTNpH` |
| 最终安装Control | 74/74通过 | `joint-control-checks-MI6yJFOV` |
| 默认产品矩阵 | 310项：283通过、27跳过 | `session-product-checks-keSjg7ye` |
| 旧版准入 | 11/11通过 | 同上 |
| 观测字段/真实RMW | 2/2通过 | `final-audits-resumed.log` |
| 候选准入正负 | 5/5通过 | `candidate-admission.json` |

Task恢复13项和原子交接/非有限数据2项包含于相关矩阵，不累加成覆盖率。完整哈希与源码指纹见[回归摘要](../validation/native-state-observation-20260906/regression-summary.json)。默认产品仍拒绝实验PX4，缺少/错误外部哈希、错误清单位置及旧libgz候选均被拒绝。

本轮10场尝试共 **127个自建进程组**，最终按当前内核重新查询均无残留；原AP PID828/start_ticks19268/argv在各场前后及最终查询保持一致。清单逐项保留成功和失败，不只选择通过样本：

| 后缀 | 结果及适用范围 |
|---|---|
| `ueydtnu6` | 固定PX4/JlC29M带观测的AP恢复通过，按封存源码。 |
| `acl9ohp6` | 固定PX4慢速降落实际estimator超龄失败，根因负对照。 |
| `68f_gxw1` | 独立PX4/JlC29M慢速降落通过；后续Task/Node改变后按封存源码。 |
| `03quqqlx` | 独立PX4/JlC29M健康生命周期通过，属于较早Control组合。 |
| `a04c93yc` | 新Task条件offer受failsafe时序影响，等待失败。 |
| `0l_skmzi` | 原生保持已确认，接管前提缺失而拒绝。 |
| `n4njgjkm` | 起飞前读到半写入交接文件而失败。 |
| `8k0pfleo`、`c8brdmu4`、`8_xg9ibk` | 最终当前源码三场通过及重复审计。 |

## 复现与下一步

Ubuntu-22.04/root，项目目录 `/mnt/c/Users/PC/Documents/odid编译/wksim`：

```bash
bash tools/build-px4-state-cadence.sh
bash tools/build-joint-control.sh
# 新构建使用它们实际输出的目录与外部SHA，不能覆盖或冒用下列封存身份。

bash tools/run-joint-flight.sh \
  --ap-manifest /root/wksim-ap-clock-stop-OXQqdR/wksim-build.json \
  --ap-sha256 f347ba252fbfc33bc92baffba08660f33c3a0e4462e90177ba84bdc11408660a \
  --control-manifest /root/wksim-joint-control-8xt3WC/build.json \
  --control-sha256 28c58fb755f9ef9c0a207db67517f90da2fde65379f4b4207c7aa90197302492 \
  --px4-manifest /root/wksim-px4-state-ONa1Kw/wksim-build.json \
  --px4-sha256 d7e905b35250d184e185ada70e3fe43f0223f1c605832d81c3c58eeb123d4cb6 \
  --scene-lifecycle
# PX4失联：追加 --dds-loss px4
# AP慢速降落对照：追加 --dds-loss arducopter --native-state-trace --probe-land-freshness

bash tools/check-scene-lifecycle-source.sh
bash validation/native-state-observation-20260906/final-audits.sh
```

正式入口目前仍采用原固定配置。下一步须把已验证的独立候选纳入正式产品配置/联合启动及操作流程，继续完成正式倍率、迟到掉队、完整cold-reset旧队列隔离、UI/UE和全部Full余项，不能长期以诊断入口代替产品。任意网络丢包、其他模型/载具、HIL/SIH、MATLAB、插件/环境与G6正式预算并未因此通过。

本轮未改UE/P450、SDK、原固定飞控或真实硬件，未推送代码或厂商资源。主代理独立执行，无新子代理。Codebase Memory仍可读600527节点/712312边；Node/Task为metadata_changed，工具被排除，见[精确覆盖](../validation/native-state-observation-20260906/index-coverage.json)。已知源直接读取，外部PX4源按固定提交/哈希核对；没有依赖新结构的图查询，不冒称此前持久化问题已修复。
