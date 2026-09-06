# 31 · MATLAB TCP/JSON可选桥闭环

状态：2026-09-05用户“确认开始”批准；ready-for-agent。阻塞未清除前不进入执行前沿。

## Parent

[规格：Prometheus 到 wksim 完整仿真工具链移植](https://github.com/unununnnn/wksim/issues/10)；来源：[Wayfinder：Prometheus 双飞控 SITL 移植（UE5.5 / ROS2 / DDS）](https://github.com/unununnnn/wksim/issues/1)。不改写或关闭父图。

## What to build

MATLAB用户通过基础tcpclient执行已获确认的操作，并在断开后不影响主仿真。

## Acceptance criteria

- [ ] 按[已批准首期范围](../../2026-09-06_recommended-decisions-accepted.md)冻结状态/日志、实验参数配置和 Prometheus 高层命令接口；MATLAB 不参与物理 step、飞控 keepalive 或必选启动。范围答复已取得，具体接口与实测仍待完成。
- [ ] UTF-8 JSON边界具有版本、运行/请求身份和有界输入，非法JSON、碎片/粘包、非有限值和未知方法可检验。
- [ ] 不提供任意文件/shell/DLL执行，写操作复用公开任务与白名单契约，重连不重放旧命令。
- [ ] 用本机真实MATLAB完成批准流程并记录版本/许可实际结果；没有MATLAB时主SITL照常运行，其他客户端不能代替MATLAB联测。
- [ ] 交付实际命令、版本/身份、预期与结果、失败/未验证边界；主代理复核后才能关闭。

## Blocked by

- [控制节点重启后的旧命令隔离](https://github.com/unununnnn/wksim/issues/14)
- [单机多航点任务与取消闭环](https://github.com/unununnnn/wksim/issues/15)
- [已有任务记录的离线回看](https://github.com/unununnnn/wksim/issues/16)
- [MATLAB 最小接口边界决策](https://github.com/unununnnn/wksim/issues/5)

## Parallel boundary

本票建议归属：MATLAB。每个阶段只分配一个写入者；共享消息、调度或生命周期的修改由主代理分配，不能与另一子代理覆盖同一区域。真实SITL/UE测试通过主代理预约隔离资源。模型与推理强度显式gpt-6-astra/low，未经允许不再嵌套委派。
