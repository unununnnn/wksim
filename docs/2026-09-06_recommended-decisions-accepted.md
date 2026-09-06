# 2026-09-06 已提出推荐的用户批准记录

状态：下列已提出推荐获用户批准；实现及运行验收另行记录。两份 Issue 正文保存在 `validation/decision-acceptance-20260906/`，发布结果以该目录的 `publication.json` 为准。

## 批准依据与适用范围

用户以“全按照推荐”批准此前已经提出的推荐。本记录将其映射到下列已有 #5 与 #8 推荐，依据为本次会话授权；旧 Issue 评论仅证明推荐曾经提出。

- [#5 已提出的 MATLAB 范围](https://github.com/unununnnn/wksim/issues/5#issuecomment-5550336972)：此前已批准基础 `tcpclient` + JSON 可选桥，本次补齐首期操作范围的批准。
- [#8 已提出的联合调度推荐](https://github.com/unununnnn/wksim/issues/8#issuecomment-5555121154)：本次采纳下列物理 tick、输入 barrier、异常与生命周期原则。

## #8：已批准的联合场景原则

1. 同一联合场景使用唯一权威物理时间，以 **1ms tick** 推进；**4ms 输入 barrier** 用于输入同步边界。它不保证任一飞控、更不保证两者每 4ms 都完成一次新控制计算。AP next-frame/下一请求序号不能作为新控制计算完成 ACK。
2. 任一参与飞控超时、掉队或掉线时，冻结整个联合场景的物理推进。不能让其余载具继续自己的独立物理时间线。冻结物理不等于冻结所有通信、日志或墙钟监督线程。
3. 恢复必须显式执行；不得自动重放、补发历史控制动作。连接恢复本身不等于恢复任务控制。
4. cold reset 创建新 epoch，并重新进入就绪流程；旧代次任务、控制和确认不能成为新运行的有效输入。
5. stop 不能为促使飞控退出而额外推进已经暂停的物理时间。已有“恢复传感器流后多走两步退出”的诊断结果不能作为符合该原则的停止实现。

这里的掉线指联合场景参与飞控的相关失联，不把可选 MATLAB 连接或 UE 显示断流新增为整场景冻结条件；两者原有可选/异步边界保持适用。

## #5：已批准的 MATLAB 首期范围

MATLAB 首期可以读取状态和日志、配置实验参数、发送 Prometheus 高层命令。MATLAB 不参与物理 step、不承担飞控 keepalive，也不是必选启动组件；没有 MATLAB 或断开 MATLAB 连接时，主 SITL 仍应能够运行。

继续采用此前已确认的基础 `tcpclient` + JSON 可选桥，不要求 ROS Toolbox 或 Instrument Control Toolbox 参与此路径。原生 ROS2 直连仍需另行联测。此次范围批准不等于批准任意文件、shell、DLL 执行入口，也不把完整模型联调、故障注入扩展或全部协议草案细节算作本次新批准事项。

## 尚需实现、细化与验证

- #8 / #19 / #20 / G2：实现生产调度与唯一时间发布、任务虚拟时间和墙钟监督的分工，明确迟到输入处置、具体超时数值、重连就绪条件及复位动作；验证共同代次/步编号、暂停、单步、恢复、倍速、掉队/掉线冻结和 cold reset 的旧数据隔离。
- AP 时钟与停止：由主线继续实现和验证独立可重建候选的整数微秒时钟及可中断等待，保留固定构建负对照；重新取得准入、正常飞行、暂停和零额外物理步停止证据后，才可判断生产接入是否成立。本记录不证明修复已完成。
- #5 / MATLAB 实施票 / G5：按批准范围落实桥与客户端，明确配置白名单、支持命令、字段、单位、时间/运行/请求身份及错误语义；完成协议边界、断开/重连不重放和无 MATLAB 主仿真验证，并以真实本机 MATLAB 记录版本、许可和联测结果。

以上为后续工作要求，不是本轮测试通过清单。1ms/4ms 是已批准调度参数，不是墙钟超时数值或动力学误差预算。

## 未被此次批准覆盖的事项

[#6](https://github.com/unununnnn/wksim/issues/6) 中未曾提出供本次选择的数值阈值、正式数值预算和最终验收细目，不能由“全按照推荐”推导为已审批。已有任务门槛、诊断测量误差与重复性结果均不能替代动力学等价预算。

[#9](https://github.com/unununnnn/wksim/issues/9) 的插件 ABI、DLL 生命周期及场景/地形/碰撞/视觉反馈合同，不在本次列明推荐中，仍须分别落实其决策；不得声称已获此次批准。Full 范围没有缩减，相关实施票与 G2/G5/完整目标也不因本记录而验收完成。

## 与现有文档和计划的关系

已读取 `AGENTS.md`、`CONTEXT.md`、[运行边界](sitl-runtime-proposal.md)、[MATLAB 草案](matlab-interface-proposal.md)、[计划](plan/README.md)、[规格](plan/full-migration-spec.md)、[Goal](plan/goal-objective.md)，以及 [联合时钟](plan/tickets/09-joint-clock.md)、[暂停与冷重置](plan/tickets/10-joint-step-reset.md)、[MATLAB 桥](plan/tickets/31-matlab-bridge.md) 票据。本地票据序号不是 GitHub Issue 编号。

这些文件中关于上述具体推荐“尚待用户答复”的文字是本次批准前的历史状态，由本记录补充更新其含义；其他待决策项和未完成验收继续有效。兄弟 AeroTwinSim 的 ADR 不自动适用于本迁移。

前置证据见[原生时钟与停止报告](2026-09-06_native-clock-and-stop-report.md)。该报告记录此前诊断及其限制，新实现和验证另行报告，不能由决策批准推断测试已通过。

发布正文：[issue-5-acceptance.md](../validation/decision-acceptance-20260906/issue-5-acceptance.md)、[issue-8-acceptance.md](../validation/decision-acceptance-20260906/issue-8-acceptance.md)。
