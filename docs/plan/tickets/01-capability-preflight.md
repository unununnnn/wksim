# 01 · 实验能力预检与候选身份核验

状态：2026-09-05主代理已验收本机实现；对应工单[ #11 ](https://github.com/unununnnn/wksim/issues/11)，具体证据与剩余边界见完成评论。

## Parent

[规格：Prometheus 到 wksim 完整仿真工具链移植](https://github.com/unununnnn/wksim/issues/10)；来源：[Wayfinder：Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS）](https://github.com/unununnnn/wksim/issues/1)。不改写或关闭父图。

## What to build

使用者选择模型、飞控与通信配置后，在启动前得到可运行结论或可定位的拒绝原因。

## Acceptance criteria

- [x] 记录模型、固件、消息层和可选补丁身份，区分已实现、已构建和已实测能力。
- [x] 使用现有通过候选完成有效配置预检；故意混用AP消息覆盖层或未实现模式时拒绝且不创建飞控进程。
- [x] 公开CLI输出机器可读结果及用户可读原因；未知资源不被自动认定为兼容。
- [x] 以已冻结Full功能范围建立可增量扩展的能力索引，明确本票不实现索引中全部能力。
- [x] 交付实际命令、版本/身份、预期与结果、失败/未验证边界；主代理复核后才能关闭。

## Blocked by

None（可立即开始）

## Parallel boundary

本票建议归属：配置/能力。每个阶段只分配一个写入者；共享消息、调度或生命周期的修改由主代理分配，不能与另一子代理覆盖同一区域。真实SITL/UE测试通过主代理预约隔离资源。模型与推理强度显式gpt-6-astra/low，未经允许不再嵌套委派。
