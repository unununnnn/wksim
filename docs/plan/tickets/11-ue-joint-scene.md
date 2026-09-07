# 11 · 联合场景双载具显示与切换观察

状态：2026-09-05用户“确认开始”批准；ready-for-agent。阻塞未清除前不进入执行前沿。

2026-09-07 证据轮：基础双机显示/相机选择/暂停/单步/降落正式通过（`joint-visual-20260907-run8`，Actor 回读与权威真值逐机一致）；UE 整进程空中重开物理独立推进 1768 tick（run9）；冷重置代次隔离真实通过（run10，新增 `--reset-scene` 驱动）。验收 3 前半句「一机断流仅该机标陈」与单一权威屏障架构冲突，已提交用户（[报告](../../2026-09-07-joint-ue-visual-evidence-report.md)），未代为决定，本票继续 OPEN。

## Parent

[规格：Prometheus 到 wksim 完整仿真工具链移植](https://github.com/unununnnn/wksim/issues/10)；来源：[Wayfinder：Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS）](https://github.com/unununnnn/wksim/issues/1)。不改写或关闭父图。

## What to build

UE在同一场景中同时显示PX4与ArduCopter载具，并支持切换观察目标。

## Acceptance criteria

- [ ] 按载具身份创建和更新独立Actor，不再使用一个硬编码单载具接收槽。
- [ ] 同一画面显示同一场景时间的两机状态，位置、姿态、旋翼和标签不串机。
- [ ] 一个载具断流时仅该载具标为陈旧；场景重置后旧代次状态不能重新出现。
- [ ] 用真实联合场景和Actor回读验证，不用多个窗口或分别运行替代。
- [ ] 交付实际命令、版本/身份、预期与结果、失败/未验证边界；主代理复核后才能关闭。

## Blocked by

- [单载具产品状态流接入UE5.5](https://github.com/unununnnn/wksim/issues/17)
- [双飞控联合场景最小权威时间闭环](https://github.com/unununnnn/wksim/issues/19)

## Parallel boundary

本票建议归属：UE/状态分发。每个阶段只分配一个写入者；共享消息、调度或生命周期的修改由主代理分配，不能与另一子代理覆盖同一区域。真实SITL/UE测试通过主代理预约隔离资源。模型与推理强度显式gpt-6-astra/low，未经允许不再嵌套委派。
