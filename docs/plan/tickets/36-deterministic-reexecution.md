# 36 · 固定输入实验的确定性重新运行

状态：2026-09-05用户“确认开始”批准；ready-for-agent。阻塞未清除前不进入执行前沿。

## Parent

[规格：Prometheus 到 wksim 完整仿真工具链移植](https://github.com/unununnnn/wksim/issues/10)；来源：[Wayfinder：Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS）](https://github.com/unununnnn/wksim/issues/1)。不改写或关闭父图。

## What to build

使用者用已记录配置和执行器输入重新运行自主模型，得到约定容差内的状态轨迹。

## Acceptance criteria

- [ ] 区别离线状态回放与重新计算物理，输入、种子、模型和时间条件完整可得。
- [ ] 源运行记录不足时拒绝声称可重演，不对降采样缺口自行插值成真值。
- [ ] 同一受控构建的重演满足预先预算，并记录平台差异而非要求跨平台位级一致。
- [ ] 异常事件、暂停/单步与重置身份可追溯，重演不向真实飞控或原运行发送控制。
- [ ] 交付实际命令、版本/身份、预期与结果、失败/未验证边界；主代理复核后才能关闭。

## Blocked by

- [已有任务记录的离线回看](https://github.com/unununnnn/wksim/issues/16)
- [联合场景暂停单步与冷重置](https://github.com/unununnnn/wksim/issues/20)
- [四旋翼参数保存导入与真实运行](https://github.com/unununnnn/wksim/issues/24)

## Parallel boundary

本票建议归属：复现/记录。每个阶段只分配一个写入者；共享消息、调度或生命周期的修改由主代理分配，不能与另一子代理覆盖同一区域。真实SITL/UE测试通过主代理预约隔离资源。模型与推理强度显式gpt-6-astra/low，未经允许不再嵌套委派。
