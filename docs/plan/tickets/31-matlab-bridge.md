# 31 · MATLAB TCP/JSON可选桥闭环

状态：2026-09-05用户“确认开始”批准；ready-for-agent。阻塞未清除前不进入执行前沿。

2026-09-07 主代理复核：本切片验收完成。已批准的操作通过真实基础 MATLAB R2022b/公开 HTTP/真实双栈任务及原始审计验证；正常 MATLAB cancel 另有 PX4 实飞通过。#5 决策已关闭。协议、命令、版本/哈希、全部失败（含首次用户 startup 的外部副作用）和证据限制见[桥说明](../../matlab-bridge.md)及[整合报告](../../2026-09-07_accelerated-integration-report.md)。本票只关闭可选桥切片；单机 PX4 旧参考固件的 Gazebo 链接、联合 MATLAB 操作、原生 MATLAB ROS2 和 G5/Full 完整验收继续各自保留。代码当前在本地工作区，尚未新增提交/推送。

## Parent

[规格：Prometheus 到 wksim 完整仿真工具链移植](https://github.com/unununnnn/wksim/issues/10)；来源：[Wayfinder：Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS）](https://github.com/unununnnn/wksim/issues/1)。不改写或关闭父图。

## What to build

MATLAB用户通过基础tcpclient执行已获确认的操作，并在断开后不影响主仿真。

## Acceptance criteria

- [x] 按[已批准首期范围](../../2026-09-06_recommended-decisions-accepted.md)冻结状态/日志、实验参数配置和 Prometheus 高层命令接口；MATLAB 不参与物理 step、飞控 keepalive 或必选启动。已交付协议 v1 和真实客户端流程。
- [x] UTF-8 JSON边界具有版本、运行/请求身份和有界输入，非法JSON、碎片/粘包、非有限值和未知方法可检验。
- [x] 不提供任意文件/shell/DLL执行，写操作复用公开任务与白名单契约，重连不重放旧命令。
- [x] 用本机真实MATLAB完成批准流程并记录版本/许可实际结果；没有MATLAB时主SITL照常运行，其他客户端不能代替MATLAB联测。
- [x] 交付实际命令、版本/身份、预期与结果、失败/未验证边界；主代理复核后才能关闭。

## Blocked by

- [控制节点重启后的旧命令隔离](https://github.com/unununnnn/wksim/issues/14)
- [单机多航点任务与取消闭环](https://github.com/unununnnn/wksim/issues/15)
- [已有任务记录的离线回看](https://github.com/unununnnn/wksim/issues/16)
- [MATLAB 最小接口边界决策](https://github.com/unununnnn/wksim/issues/5)

## Parallel boundary

本票建议归属：MATLAB。每个阶段只分配一个写入者；共享消息、调度或生命周期的修改由主代理分配，不能与另一子代理覆盖同一区域。真实SITL/UE测试通过主代理预约隔离资源。模型与推理强度显式gpt-6-astra/low，未经允许不再嵌套委派。
