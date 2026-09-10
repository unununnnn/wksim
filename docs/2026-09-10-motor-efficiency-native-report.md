# 单电机效率原生接缝：已构建与原始验证

2026-09-10，承接 #105 的生成源定位。主代理负责本次新增的
`motor_efficiency_model.py`、`motor_efficiency_native.cpp/.h`、
`motor_efficiency_event.py`、原生 probe/audit 和测试。原 `model.cpp/model.py`、
固定生成 ZIP、飞控适配器及既有 PID 扰动实现均保留。

## 已完成

- 生成源解包后按原 SHA 和唯一匹配修改：仅对 0 号旋翼的 `Ct*omega²` 与
  `Cm*omega²` 乘 eta；只开放 1.0 / 0.97。没有缩放 PWM、共享 Ct/Cm、转速状态
  或陀螺项。其余三路系数始终为 1。
- 每个 1 ms 原生调用记录 4 旋翼 × 4 ODE4 子阶段，包含实际时间、major/minor、
  旋翼、eta、转速、原始推力/反扭矩、实际推力与反扭矩增量。原生读回四路 eta、
  tick 与 17 个真实 RandSeed 状态；同进程第二生命周期拒绝。
- 事件严格绑定运行/实例/epoch/模型与源码配置哈希；源区间
  `[origin+2000, origin+3000)` 恰好 1,000 步，提前至少 1,000 步加载。
  提前撤销、active 撤销与已失败事件不能重新激活，计划改写在下一积分前拒绝并读回 eta=1。
- 7 个独立进程的原生 bench 通过独立审计。eta=1 的全部 4,000×120 个 binary64
  输出与原固定模型逐位一致；故障两次跨进程重复输出逐位一致；17 个初始随机状态
  与逐步随机状态一致。所有 ODE4 子阶段符合独立 T/M 方程，电机转速动态保持一致。
- 重新解包/编译得到相同库 SHA；新进程 normal 的完整原始记录与先前 normal 相同。
  这包括 eta、初始与后续随机状态、16 子阶段和 120 输出，不是只重新创建 Python 对象。
- 7 项边界/独立审计测试通过，包含错身份/时间/字段、重复发布、额外旋翼被改、
  只改力矩日志而不改原生物理的负例；原生同生命周期第二事件也会锁存失败。

主要候选：`/root/wksim-efficiency-model-r97g_cit/libwksim_efficiency.so`，
SHA256 `a7325ebf754f6e61ebf25c5382fb67343659454cc176c0a7d50f980b3dcb9199`。
构建清单 SHA256 `e8e5aafa0352c851d67afbc617739c570ea9008b72750576ccaa343e87c1cef4`。
冷重建位于 `/root/wksim-efficiency-model-h48ywro3/`，库内容相同。
原始归档、逐文件 SHA 与审计在 `validation/44-efficiency-native/`。

## 准确边界

这些是无 ROS、无飞控、无 UE 的原生模型 bench。bench origin=0 只验证事件区间；
不冒充真实连续悬停 6 秒后的物理所有者 origin。固定开环输入 `[.55]*4+[0]*12`
用于证明效率进入积分；故障后轨迹明显变化，不表示已经满足悬停/恢复预算。
事件 seed=0 是无随机事件调度；模型使用另外读取的 17 个固定原生随机状态，二者不混称。

后继工作是独立的真实飞行运行器、原始 actuator→每步效率→物理→任务审计，以及
稳定悬停后精确 origin、8 秒恢复、取消/LAND/清理和同种子新 epoch 重跑。
#105/#44 此时仍未完成整场飞行验收；不提升默认模型，不改 R1 或 RateUnmet。
生成厂商源码仅留本机受控构建目录，没有复制进仓库。

## 可执行入口

在 wksim 根目录的 Ubuntu-22.04 中：

```sh
python3 -B -m Simulator.wksim_core.motor_efficiency_model
python3 -B tools/probe_motor_efficiency.py \
  --library /root/wksim-efficiency-model-r97g_cit/libwksim_efficiency.so \
  --case event --output /root/wksim-efficiency-native-new-event
python3 -B -m unittest validation.test_motor_efficiency_event -v
WKSIM_EFFICIENCY_NATIVE_AUDIT=1 python3 -B -m unittest validation.test_motor_efficiency_native_audit -v
```

每次原生 probe 使用新输出目录和新进程。完整七角色审计参数及源/原始结果已保存；
参考与候选的原始轨迹不能用结果摘要替代。早期 `/tmp` 构建随 WSL 临时文件回收不可持久，
候选构建已改用独立 `/root/wksim-efficiency-model-*` 目录。
