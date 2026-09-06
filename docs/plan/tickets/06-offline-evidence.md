# 06 · 已有任务记录的离线回看

状态：2026-09-05主代理已验收本机实现；对应工单[ #16 ](https://github.com/unununnnn/wksim/issues/16)，具体证据与剩余边界见完成评论。

## Parent

[规格：Prometheus 到 wksim 完整仿真工具链移植](https://github.com/unununnnn/wksim/issues/10)；来源：[Wayfinder：Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS）](https://github.com/unununnnn/wksim/issues/1)。不改写或关闭父图。

## What to build

使用者打开一个既有真实实验的证据包，在不连接飞控的情况下回看状态与事件。

## Acceptance criteria

- [x] 以当前真实双栈日志为输入，按源时间显示命令、ACK、状态与物理真值的关联。
- [x] 缺失运行代次或其他旧日志字段显式标为未知，不补造为已记录。
- [x] 截断、缺段、格式错误和过期状态给出诊断；回看器不创建控制发布者。
- [x] 证明回看相同已记录样本和事件顺序；本票不承诺确定性重新仿真。
- [x] 交付实际命令、版本/身份、预期与结果、失败/未验证边界；主代理复核后才能关闭。

## Blocked by

None（可立即开始）

## Parallel boundary

本票建议归属：证据/回放。每个阶段只分配一个写入者；共享消息、调度或生命周期的修改由主代理分配，不能与另一子代理覆盖同一区域。真实SITL/UE测试通过主代理预约隔离资源。模型与推理强度显式gpt-6-astra/low，未经允许不再嵌套委派。
