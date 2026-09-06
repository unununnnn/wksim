# 16 · 生成模型构建导入与无MATLAB运行

状态：2026-09-05用户“确认开始”批准；ready-for-agent。阻塞未清除前不进入执行前沿。

## Parent

[规格：Prometheus 到 wksim 完整仿真工具链移植](https://github.com/unununnnn/wksim/issues/10)；来源：[Wayfinder：Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS）](https://github.com/unununnnn/wksim/issues/1)。不改写或关闭父图。

## What to build

模型开发者从现有可编辑模板或明确来源生成产物构建模型，导入后运行与重置。

## Acceptance criteria

- [ ] 完整记录可编辑材料、生成产物、编译工具、导入模型和运行证据的来源链。
- [ ] 复用本机MATLAB/Simulink构建工具时实际检查可用性，不把文件存在当作许可检出成功。
- [ ] 生成后关闭MATLAB，核心仍独立加载、运行、重置和终止该模型。
- [ ] 厂商材料留在受控本地来源，不提交授权不明生成源码；不把旧ZIP直接编译称为已验证完整生成流程。
- [ ] 交付实际命令、版本/身份、预期与结果、失败/未验证边界；主代理复核后才能关闭。

## Blocked by

- [四旋翼参数保存导入与真实运行](https://github.com/unununnnn/wksim/issues/24)
- [可选模型插件与场景反馈接口决策](https://github.com/unununnnn/wksim/issues/9)

## Parallel boundary

本票建议归属：模型/生成。每个阶段只分配一个写入者；共享消息、调度或生命周期的修改由主代理分配，不能与另一子代理覆盖同一区域。真实SITL/UE测试通过主代理预约隔离资源。模型与推理强度显式gpt-6-astra/low，未经允许不再嵌套委派。
