# 20 · 带时间与标定的真实RGB相机

状态：2026-09-05用户“确认开始”批准；ready-for-agent。阻塞未清除前不进入执行前沿。

## Parent

[规格：Prometheus 到 wksim 完整仿真工具链移植](https://github.com/unununnnn/wksim/issues/10)；来源：[Wayfinder：Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS）](https://github.com/unununnnn/wksim/issues/1)。不改写或关闭父图。

## What to build

用户给指定载具配置RGB相机，在UE场景中采集并消费关联真实位姿的图像。

## Acceptance criteria

- [ ] 输出载具/传感器身份、采样时间、内外参和图像，不以屏幕截图替代。
- [ ] 固定目标场景下改变位姿与遮挡，输出和标定关系符合已声明测试条件。
- [ ] 相机断流、重连和旧代次数据可识别，主物理不等待图像消费。
- [ ] 保存实际传感器输出及消费者结果，不能仅凭Actor ACK算通过。
- [ ] 交付实际命令、版本/身份、预期与结果、失败/未验证边界；主代理复核后才能关闭。

## Blocked by

- [单载具产品状态流接入UE5.5](https://github.com/unununnnn/wksim/issues/17)
- [可选模型插件与场景反馈接口决策](https://github.com/unununnnn/wksim/issues/9)

## Parallel boundary

本票建议归属：视觉传感器。每个阶段只分配一个写入者；共享消息、调度或生命周期的修改由主代理分配，不能与另一子代理覆盖同一区域。真实SITL/UE测试通过主代理预约隔离资源。模型与推理强度显式gpt-6-astra/low，未经允许不再嵌套委派。
