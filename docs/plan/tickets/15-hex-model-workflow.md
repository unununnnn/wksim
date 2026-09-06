# 15 · 六旋翼从参数配置到双栈运行

状态：2026-09-05用户“确认开始”批准；ready-for-agent。阻塞未清除前不进入执行前沿。

## Parent

[规格：Prometheus 到 wksim 完整仿真工具链移植](https://github.com/unununnnn/wksim/issues/10)；来源：[Wayfinder：Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS）](https://github.com/unununnnn/wksim/issues/1)。不改写或关闭父图。

## What to build

用户选择六旋翼构型，配置、运行并在UE观察正确数量与方向的旋翼。

## Acceptance criteria

- [ ] 冻结这一构型的模型、参数、质量惯量、电机编号和旋向以及适用飞控配置。
- [ ] 独立模型及适用双栈配置完成起飞、保持、航点、降落和重置证据。
- [ ] UE几何与旋翼表达符合构型，不能仍显示四旋翼占位模型。
- [ ] 不适用的飞控组合列明依据，缺少实现的组合保持未完成；不推断三轴六旋翼等其他构型同样通过。
- [ ] 交付实际命令、版本/身份、预期与结果、失败/未验证边界；主代理复核后才能关闭。

## Blocked by

- [单载具产品状态流接入UE5.5](https://github.com/unununnnn/wksim/issues/17)
- [四旋翼参数保存导入与真实运行](https://github.com/unununnnn/wksim/issues/24)

## Parallel boundary

本票建议归属：模型/机型。每个阶段只分配一个写入者；共享消息、调度或生命周期的修改由主代理分配，不能与另一子代理覆盖同一区域。真实SITL/UE测试通过主代理预约隔离资源。模型与推理强度显式gpt-6-astra/low，未经允许不再嵌套委派。
