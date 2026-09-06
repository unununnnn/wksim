# 07 · 单载具产品状态流接入UE5.5

状态：2026-09-05主代理已验收本机实现；对应工单[ #17 ](https://github.com/unununnnn/wksim/issues/17)，具体证据与剩余边界见完成评论。

## Parent

[规格：Prometheus 到 wksim 完整仿真工具链移植](https://github.com/unununnnn/wksim/issues/10)；来源：[Wayfinder：Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS）](https://github.com/unununnnn/wksim/issues/1)。不改写或关闭父图。

## What to build

真实产品实验直接向UE5.5提供当前权威状态，显示机体、旋翼与LIVE/STALE状态。

## Acceptance criteria

- [x] 复用现有UE模块、坐标验证和本机环境，以正式状态输出代替共享诊断JSONL尾读。
- [x] PX4和ArduCopter分别完成真实共同任务，UE坐标/姿态回读与同一来源状态一致。
- [x] 载具身份、源时间、序号、单位和构型元数据有明确契约，非法或旧运行报文被拒绝。
- [x] 断开显示后物理继续，恢复只显示当前状态；本票仍是单载具，不宣称联合场景。
- [x] 交付实际命令、版本/身份、预期与结果、失败/未验证边界；主代理复核后才能关闭。

## Blocked by

None（可立即开始）

## Parallel boundary

本票建议归属：UE/状态分发。每个阶段只分配一个写入者；共享消息、调度或生命周期的修改由主代理分配，不能与另一子代理覆盖同一区域。真实SITL/UE测试通过主代理预约隔离资源。模型与推理强度显式gpt-6-astra/low，未经允许不再嵌套委派。
