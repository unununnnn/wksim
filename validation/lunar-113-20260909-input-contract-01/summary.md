# #113 · 46-input-contract 完成摘要

2026-09-09。完成物理重新计算输入合同与旧源不足判定，仅完成本子票设计范围。

- 文件：`docs/plan/46-reexecution-contract.md`；本目录 `review.ps1`、`review.json`、`summary.md`。
- 冻结源时间、16路执行器/15路地形输入、冷启动完整内部状态身份、配置/模型/实际库身份、17个标量随机流、暂停/单步/重置/异常事件和缺段拒绝规则。同一受控库/平台输出120槽逐tick数值相等，atol=rtol=0；未改R1或倍率预算。
- 精确执行命令（Windows PowerShell，仓库根）：`& ./validation/lunar-113-20260909-input-contract-01/review.ps1`。退出0，7项只读核对通过，0跳过。原始结构化结果见 review.json；这7项是输入证据核对，不是物理重算测试。
- 旧源 `validation/quad-parameters-native-20260909-b/baseline.jsonl` 有501行（header+500连续tick），固定16路输入、每tick120槽；terminal数量0、event_policy缺失。结论 `insufficient_recording`，满足票据允许的 explicit insufficient-recording rejection，不回填旧证据。
- 当前14份源码/配置/记录的SHA256、原ZIP及生成cpp/h SHA256见 review.json。实际读取生成输入声明、1ms ODE4与随机初始化；厂商材料未提交。
- 合同中的配置 import/inspect 是现有入口；reexecute_physics.py 的 import/run/audit 是 #114 待实现的准确CLI合同，当前不存在，未冒称已执行。没有创建 imported-config.json。
- #113 AC1：完整合同及明确不足拒绝已交付。AC2：源/配置身份、准确命令、原始结果、失败边界已交付。本子票可关闭；#114/#115待实现/独立运行，#46及#20原依赖/验收继续有效。
- 未启动模型、FC、ROS、UE或飞行子进程，无本票进程需要清理。未执行真实重新积分或声称Full/G6通过。
- 模型设置：当前会话 `01a08599-0725-74a0-b6c3-0f75be2c3199` 的最新 turn_context 实读 model=`gpt-6-astra`、effort=`low`。早期上下文存在其他设置；本次只声明最新实际设置。没有子代理。
- 本票只暂存合同和本新目录；已有 AGENTS.md、推进指南改动排除。源检查起点HEAD `d8aaf60106abaf226344fbfbe8ad445c9c8d21c7`。
