# 19 · 坡面与障碍场景的物理反馈

状态：2026-09-05用户“确认开始”批准；ready-for-agent。阻塞未清除前不进入执行前沿。

## Parent

[规格：Prometheus 到 wksim 完整仿真工具链移植](https://github.com/unununnnn/wksim/issues/10)；来源：[Wayfinder：Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS）](https://github.com/unununnnn/wksim/issues/1)。不改写或关闭父图。

## What to build

载具在可见坡面或障碍场景中运行，地形/碰撞反馈与权威状态及画面一致。

## Acceptance criteria

- [ ] 冻结一个可核验场景的物理表示、视觉表示、坐标和反馈有效时间。
- [ ] 在坡面/接触工况中检查高度、接触位置与模型反应，重置后按批准预算可复核。
- [ ] 显示断开及反馈过期按批准契约处理，不能永久复用旧反馈或依赖渲染帧推进物理。
- [ ] 保留动态地形/对象变化等额外能力行，不把视觉地面偏移当作碰撞实现。
- [ ] 交付实际命令、版本/身份、预期与结果、失败/未验证边界；主代理复核后才能关闭。

## Blocked by

- [单载具产品状态流接入UE5.5](https://github.com/unununnnn/wksim/issues/17)
- [四旋翼固定工况数值对照](https://github.com/unununnnn/wksim/issues/23)
- [可选模型插件与场景反馈接口决策](https://github.com/unununnnn/wksim/issues/9)

## Parallel boundary

本票建议归属：环境/UE。每个阶段只分配一个写入者；共享消息、调度或生命周期的修改由主代理分配，不能与另一子代理覆盖同一区域。真实SITL/UE测试通过主代理预约隔离资源。模型与推理强度显式gpt-6-astra/low，未经允许不再嵌套委派。
