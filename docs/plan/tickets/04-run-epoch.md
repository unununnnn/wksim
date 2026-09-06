# 04 · 控制节点重启后的旧命令隔离

状态：2026-09-05 14:00:01 UTC，主代理验收后按completed关闭并读回。证据见[第二批报告](../../2026-09-05_product-second-wave-report.md)。

## Parent

[规格：Prometheus 到 wksim 完整仿真工具链移植](https://github.com/unununnnn/wksim/issues/10)；来源：[Wayfinder：Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS）](https://github.com/unununnnn/wksim/issues/1)。不改写或关闭父图。

## What to build

使用者在同一实验内重启任务控制节点后，旧命令和旧确认不能控制或完成新操作。

## Acceptance criteria

- [x] 定义最小运行身份与代次边界并贯穿公开命令、事件和状态；兼容旧接口的过渡行为显式说明。
- [x] 注入旧代次命令、重复MOVE ID及迟到ACK时，记录拒绝且不发送新设定值。
- [x] 重启后仅新请求可以重新接管；本地撤销不冒称取消飞控内部已接受命令。
- [x] 源时间与接收新鲜度分别保留，重置/时钟回退不会刷新旧状态。
- [x] 交付实际命令、版本/身份、预期与结果、失败/未验证边界；主代理复核后才能关闭。

## Blocked by

- [正式入口启动与停止一次双栈可选实验](https://github.com/unununnnn/wksim/issues/12)

## Parallel boundary

本票建议归属：控制生命周期。每个阶段只分配一个写入者；共享消息、调度或生命周期的修改由主代理分配，不能与另一子代理覆盖同一区域。真实SITL/UE测试通过主代理预约隔离资源。模型与推理强度显式gpt-6-astra/low，未经允许不再嵌套委派。
