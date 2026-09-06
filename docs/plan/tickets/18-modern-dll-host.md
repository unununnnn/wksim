# 18 · 可选新ABI模型DLL与扩展输出

状态：2026-09-05用户“确认开始”批准；ready-for-agent。阻塞未清除前不进入执行前沿。

## Parent

[规格：Prometheus 到 wksim 完整仿真工具链移植](https://github.com/unununnnn/wksim/issues/10)；来源：[Wayfinder：Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS）](https://github.com/unununnnn/wksim/issues/1)。不改写或关闭父图。

## What to build

用户选择一个合法可用的新ABI模型，运行并获取经过布局验证的传感器/载具与扩展输出。

## Acceptance criteria

- [ ] 明确区分旧/新命名和真实ABI，不依靠函数名相近猜测可互换。
- [ ] 验证该样本全部已声明输入输出长度、单位、有效性及生命周期。
- [ ] 按批准预算与固定输入完成新ABI对照，非法布局明确拒绝。
- [ ] 旧ABI回归保持通过，新旧DLL均不成为核心必需依赖；未测扩展I/O单列后续。
- [ ] 交付实际命令、版本/身份、预期与结果、失败/未验证边界；主代理复核后才能关闭。

## Blocked by

- [可选旧ABI模型DLL生命周期闭环](https://github.com/unununnnn/wksim/issues/27)
- [可选模型插件与场景反馈接口决策](https://github.com/unununnnn/wksim/issues/9)

## Parallel boundary

本票建议归属：模型插件。每个阶段只分配一个写入者；共享消息、调度或生命周期的修改由主代理分配，不能与另一子代理覆盖同一区域。真实SITL/UE测试通过主代理预约隔离资源。模型与推理强度显式gpt-6-astra/low，未经允许不再嵌套委派。
