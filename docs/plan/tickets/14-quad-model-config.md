# 14 · 四旋翼参数保存导入与真实运行

状态：2026-09-05用户“确认开始”批准；ready-for-agent。阻塞未清除前不进入执行前沿。

## Parent

[规格：Prometheus 到 wksim 完整仿真工具链移植](https://github.com/unununnnn/wksim/issues/10)；来源：[Wayfinder：Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS）](https://github.com/unununnnn/wksim/issues/1)。不改写或关闭父图。

## What to build

用户修改四旋翼模型参数、保存导出并重新导入后，运行得到对应模型和可观察动力学变化。

## Acceptance criteria

- [ ] 对齐该构型的参数单位、默认值、组件及电机映射，拒绝非法或不完整配置。
- [ ] 保存/重载和导出/导入保持关键参数、模型身份与构建来源一致。
- [ ] 质量或动力参数的受控变化反映在预先声明的静态/飞行观测量上。
- [ ] 保留Full组件库、性能计算与其他构型的后续行，本票不冒称全部内置模型工具完成。
- [ ] 交付实际命令、版本/身份、预期与结果、失败/未验证边界；主代理复核后才能关闭。

## Blocked by

- [正式入口启动与停止一次双栈可选实验](https://github.com/unununnnn/wksim/issues/12)
- [四旋翼固定工况数值对照](https://github.com/unununnnn/wksim/issues/23)

## Parallel boundary

本票建议归属：模型/参数工具。每个阶段只分配一个写入者；共享消息、调度或生命周期的修改由主代理分配，不能与另一子代理覆盖同一区域。真实SITL/UE测试通过主代理预约隔离资源。模型与推理强度显式gpt-6-astra/low，未经允许不再嵌套委派。
