# 回调保留验证入口

`test_parent_callback_contract.py` 保留原始假时钟驱动类，供已钉扎的 `claude-last-callback-integration-20260913-01/capture_and_replay.py` 导入。其旧独立评审入口不是当前验收入口，早期“无阻断”结论已撤回。

当前依据为 `test_callback_retention_followup.py`、`sha-receipt-20260913-06.json` 及其指向的证据：同组成功睡眠后失败不会混配时间戳，健康回调本身耗时 3ms 的跨沿场景已被真实父类驱动复现。候选只用于诊断准备，不代表运行性能或 Full 通过。
