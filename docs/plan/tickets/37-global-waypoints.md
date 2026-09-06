# 37 · 双栈全球航点与home基准

状态：2026-09-05用户“确认开始”批准；ready-for-agent。阻塞未清除前不进入执行前沿。

## Parent

[规格：Prometheus 到 wksim 完整仿真工具链移植](https://github.com/unununnnn/wksim/issues/10)；来源：[Wayfinder：Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS）](https://github.com/unununnnn/wksim/issues/1)。不改写或关闭父图。

## What to build

使用者以经纬度和明确home相对高度给出航点，两套飞控执行同义目标。

## Acceptance criteria

- [ ] 补齐并验证PX4全球位置适配，保持AP已明确的home与局部转换边界。
- [ ] 经纬度、AMSL/相对高度、ENU/NED之间的转换有显式基准与数值检查。
- [ ] 全球目标真实飞行、越界拒绝和home变化后的旧目标失效在两栈分别通过。
- [ ] 不能把EKF origin当home，也不能将未校验的全球目标静默改成局部位置。
- [ ] 交付实际命令、版本/身份、预期与结果、失败/未验证边界；主代理复核后才能关闭。

## Blocked by

- [正式入口启动与停止一次双栈可选实验](https://github.com/unununnnn/wksim/issues/12)
- [控制节点重启后的旧命令隔离](https://github.com/unununnnn/wksim/issues/14)
- [四旋翼固定工况数值对照](https://github.com/unununnnn/wksim/issues/23)

## Parallel boundary

本票建议归属：原生控制。每个阶段只分配一个写入者；共享消息、调度或生命周期的修改由主代理分配，不能与另一子代理覆盖同一区域。真实SITL/UE测试通过主代理预约隔离资源。模型与推理强度显式gpt-6-astra/low，未经允许不再嵌套委派。
