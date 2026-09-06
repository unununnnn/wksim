# 17 · 可选旧ABI模型DLL生命周期闭环

状态：2026-09-05用户“确认开始”批准；ready-for-agent。阻塞未清除前不进入执行前沿。

## Parent

[规格：Prometheus 到 wksim 完整仿真工具链移植](https://github.com/unununnnn/wksim/issues/10)；来源：[Wayfinder：Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS）](https://github.com/unununnnn/wksim/issues/1)。不改写或关闭父图。

## What to build

用户选择一个合法可用的旧ABI DLL，在独立Windows宿主中加载、步进、重置和卸载。

## Acceptance criteria

- [ ] 按批准ABI核对导出、签名、数组布局和单位，以输入输出对照验证而非只查导出名。
- [ ] 同一固定工况下完成初始化、步进、重置、终止和卸载，错误有确定反馈。
- [ ] 宿主崩溃或不兼容DLL被隔离，不影响原厂安装或其他运行。
- [ ] 禁用/移除DLL后自主模型流程仍运行；本票不自动宣称新ABI兼容。
- [ ] 交付实际命令、版本/身份、预期与结果、失败/未验证边界；主代理复核后才能关闭。

## Blocked by

- [正式入口启动与停止一次双栈可选实验](https://github.com/unununnnn/wksim/issues/12)
- [四旋翼固定工况数值对照](https://github.com/unununnnn/wksim/issues/23)
- [可选模型插件与场景反馈接口决策](https://github.com/unununnnn/wksim/issues/9)

## Parallel boundary

本票建议归属：模型插件。每个阶段只分配一个写入者；共享消息、调度或生命周期的修改由主代理分配，不能与另一子代理覆盖同一区域。真实SITL/UE测试通过主代理预约隔离资源。模型与推理强度显式gpt-6-astra/low，未经允许不再嵌套委派。
