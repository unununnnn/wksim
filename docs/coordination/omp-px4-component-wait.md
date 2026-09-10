# OMP PX4 组件等待定位（tracking-18 tick9388 / 219.973566ms）

日期：2026-09-11。只读固定候选 `/root/wksim-px4-land-7RjMjQ/src`（PX4 树；
实际布局为 <root>/src 下含 boards/platforms/src）。未编译/运行/改源码。
结论区分假设，不定 AP/PX4 根因；TCP_NODELAY 已启用不作为新修复。

## 准确等待条件（实读）

`SimulatorMavlink::send()` 循环（`src/modules/simulation/simulator_mavlink/SimulatorMavlink.cpp:1040-1066`）：

1. `px4_poll(fds, 1, 100)`（:1044）——等 `actuator_outputs` ORB 数据，上限 100ms；
   超时 `pret==0` 直接 continue（不含任何组件等待）。
2. POLLIN 到达后：parameters/vehicle_status/battery 更新，然后
   `px4_lockstep_wait_for_components()`（:1064，注释自述"等 logger 或 ekf2"），
   通过才 `send_controls()`。
3. `LockstepComponents::wait_for_components()`
   （`platforms/posix/src/px4/common/lockstep_scheduler/src/lockstep_components.cpp`
   末尾）：无注册组件立即返回；否则 sem_wait 直到**所有**注册组件在同一周期
   `lockstep_progress` 置位（最后置位者 post 信号量）。
4. 注册者（register_component 实读全 src 仅三处含义两处）：logger
   （`src/modules/logger/logger.cpp:693`，仅 `_polling_topic_meta` 配置存在时，
   每个循环处理结束后 :902 置进度后 poll 其 topic 20ms）与 SimulatorMavlink 自身
   （`:511` 首个 IMU id0 注册，`:547` HIL_SENSOR 处理时置进度）。ekf2 在该树中
   **没有** register_component 调用——注释里的 ekf2 与现状不符。

所以一次循环的两段独立等待是：actuator_outputs 的 100ms 量化 poll，和其后
无界但由组件进度驱动的 lockstep 信号量。

**不能区分**：poll 超时虽以 100ms 名义上限空转，但调度与读取延迟会改变墙钟，
按 100ms 倍数反推不成立（初版该断言已撤回）。现有记录也不能把组件等待
再分给 logger 还是 simulator 自身——必须靠插桩区分。

## 最小只读诊断插桩方案（建议，未实施）

1. `SimulatorMavlink.cpp` send()：围绕 :1044 poll 与 :1064 wait_for_components
   加单调 ns 时间戳对（T0 poll 前 / T1 POLLIN 后 / T2 lockstep 后 / T3
   send_controls 后），连同 pret/revents 写入既有调试通道。
   字段：`poll_ns`、`lockstep_ns`、`send_ns`、`pret`、`revents`。
2. `lockstep_components.cpp` `wait_for_components()` 入口记录
   `_components_used_bitset & ~_components_progress_bitset`（缺谁）与等待时长。
3. `logger.cpp:902` 循环末尾迭代时间戳（logger 进度节拍），判读其
   20ms topic poll 是否拖住组件进度。

实现行数依完整安全检查而定，不移除任何 barrier 参与者、不停用日志、不改门槛。
当前无新 SITL；18 已 retire，等待主会话决定是否在下一候选固件上实施。

## 实际补丁复核（0005，6478B，SHA256 E95E3165…，git apply --check 主会话已过）

- 三处 sem/bitset/register 原行全部保留；`used==0` 早返回在 trace 块之前未变；
  原 continue 分支保留；注册 CAS/进度置位/释放信号量算法不动。
- off 模式：ternary 短路，无额外 clock 读取、无输出；on 模式仅 wait>2ms、
  poll>20ms 或 POLLIN 后段>2ms 才输出——正常 0.5× 约 8ms poll 不逐轮刷。
- release 观测存单一 component bit（非全集），独立 atomics，不进屏障数据。
- 残余风险（观察级，不阻止构建）：release 观测在 `value<1` 守卫内，上游自述的
  双释放竞态下可能漏记一次释放；release_ns 与 component 为 acquire/relaxed 非
  原子对，极端下可读到错位组合——仅观测用途可接受。syscall 失败时时间戳为 0。
