# #100 合同来源审查结果

2026-09-09，工作分支 codex/independent-rgb-integration；开始 HEAD 37a351b3491a0d35a8c4d8ed726683da0764928f。

交付 docs/plan/39-planner-contract.md：选定 Prometheus EGO 单机 B-spline 规划，冻结停止优先、递增命令ID、代次隔离、确定地图/profile与到达/净空/碰撞/无路/取消/重规划指标。保留来源许可 TODO、ROS2接入、地图物理反馈、倍率与后继源码写权缺口。

实际命令（项目根 PowerShell）：

```powershell
python validation/lunar-100-contract-20260909-01/audit_source.py > validation/lunar-100-contract-20260909-01/source-audit.json
git diff --check
```

审查命令退出0：4个静态源码检查均true；15个文件SHA256已记录，其中11个上游文件经换行归一化与固定上游内容一致，4个迁移文件在上游不存在。6张票据读回均成功。暂存检查发现PowerShell输出CRLF被当前Git规则视作行尾空白；仅格式化JSON行尾为LF后，暂存diff检查退出0。source-audit.json 是原始命令结果（仅行尾归一化），非规划运行测试；再次运行应使用新输出文件，保留本快照。并行任务在审查时已推进HEAD至63e0fe10c4d6bc3ffa7888b8322705e7eb7f02ca，准确审查身份见JSON。

发现：局部新建 UAVCommand 后 ID 重复递增为1；stop赋值随后被旧轨迹覆盖；10ms定时器真实存在；plan_manage许可标记TODO。源码阅读还确认旧轨迹身份不足、未来时间可能发布零值、EMERGENCY_STOP可自动恢复。未修改上述源码。

图导航：使用指定 CBM_CACHE_DIR=C:/CBMData、CBM_RUNTIME_DIR=C:/CBMRuntime 的原生 index_status，返回ready（50865节点/165157边）；search_graph --query traj_server --limit 5 可用。实际结论来自源文件直接阅读与固定上游比较，图计数不作为覆盖率。

#100 独立合同完成；#29/#33仍OPEN，#102不可据此试飞。依据本票“无额外开放依赖”及父容器合同先行规则，关闭范围仅#100。未启动FC、model、ROS、UE；无本票运行进程。已有AGENTS.md和推进指南改动保持工作树原状，不纳入本票提交。

设置：用户指定 gpt-6-astra/low，当前接口无法独立核验实际具体模型/推理档位，故实际值未验证。无子代理。
