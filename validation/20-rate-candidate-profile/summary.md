# #61 / 20-rate-engineering 交付

完成本票的实测归因、host候选冻结及可执行运行/审计入口。未运行1×新实飞，未声明性能通过；#20/#33/G2/Full原结论保持。

- 合同：`docs/plan/20-rate-candidate-contract.md`。
- 证据：`validation/20-rate-candidate-profile/`，提交`analysis-02`、`checks-01`及入口/清单；早期`analysis-01`本地保留，不作最终结论。
- 实测：4份真实1×失败日志离线重放逐纳秒匹配。p9的tick76833 health/model阶段5.128973ms，其中监督线程CPU0.293791ms；4.835182ms为非本线程CPU时间。该组下一次相位增量4.652309ms。不能从此区分模型执行、IPC/I/O、Linux或Windows抢占。
- 候选：`rate61-linux-cpuset8-v1`，仅以`taskset -c 0-7`改变自有进程树允许CPU集；8-vCPU选择是事先固定的可证伪候选，尚无改善证明，不声称P核/独占CPU。产品源码零改动，无需源码实现子票。
- 冻结58项源码/配置哈希；AP/PX4/model/control/messages/Agent完整资源身份在`checks-01/preflight.json`。100ms、1ms/4tick、10s±2%、60s±1%、3独立epoch等原预算不变。
- 检查：资源准入exit0、ok=true、children_created=0；12项timer检查与2项运行器失败边界通过、0跳过；错误CPU集/开启采样/源码变化3项负例拒绝。旧日志重放exit1为预期真实失败。已实际source正式审计环境并运行旧失败样本，原始审计仍exit1/status=failed，记录`audit-cli-command.json`。
- 回退微基准：从原before/after事件重新算出1000组、8ms最小间距及1.161983/1.928489ms最坏迟到，确认无收益；没有重复timer改动或覆盖旧结果。
- 入口：`wsl -d Ubuntu-22.04 -u root -- taskset -c 0-7 /usr/bin/python3 -B validation/20-rate-candidate-profile/run-one.py 1`。完整脚本、3份配置、后续单场/三场审计命令和输出schema已在合同冻结。仅`--check`和只读准入已执行，实飞由#62–#64按各自范围执行，一次失败不得自动重试。
- 历史`steady-one-after-ready`不满足当前正式审计的mode门；新候选从1×配置执行`steady`，不改旧flow。
- 无FC/model/ROS节点创建，无本票仿真进程需要清理。测试自有临时模拟文件已清理；其余任务工作区改动保留。
- 实际会话设置：`gpt-6-astra` / `high`，从匹配本任务ID的session turn_context核验，必要元数据在`execution-context.json`；无子代理。

完成条件核对：具体host候选与实测时间依据、精确命令、实际资源准入、哈希/原始结果/失败边界均已交付。仅关闭#61；后继实飞或宿主候选改善仍未验证。
