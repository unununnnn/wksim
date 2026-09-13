# CB 独立评审：group_work_timing 记录器（2026-09-13,cb-recorder-review-20260913-01)

范围：只读评审 `tools/group_work_timing.py`(SHA `a14d5e9c…0752db`）与 `validation/test_group_work_timing.py`(SHA `2febaa41…d490b0`)，使用真实生产者夹具 `group-work-timing-integration-20260913` 与证据包 `cb-evidence-pack-20260913-01/pack`（真实飞行 joint-public-flight-rfw9nmbb,tick 98684 终止 failed)。新增独立对抗回归测试 15 项（本目录），未改任何被审源。**本评审不把该诊断标为 pass。**

## 1. 真实运行：结果 summary 计数器 vs 报告流（独立重算）

从 `rate.jsonl.gz`（与报告流独立的业务率流）重算，不碰报告内容：

| 指标 | result summary | 独立重算 | 一致 |
|---|---|---|---|
| rate_group_start/end | 24661 complete / 0 incomplete | 各 24661 行 | ✓ |
| over_budget_groups | 18 | 逐行 work=actual_end−actual_start>8ms 重算得 18 | ✓ |
| reports_emitted | 16 | 报告流 16 行，（segment,start_tick,work,excess）与流内前 16 个超额组逐一相同 | ✓ |
| reports_dropped | 2 | 流内末两个超额组 tick 80652/98044 恰被上限丢弃 | ✓ |
| diagnostic_errors | 0 | 16 份报告分解全 closes=true、边界字段与对应 rate 行逐字节相等 | ✓ |
| epoch | 9b18d3d1… | 报告流与 rate 流同一 epoch | ✓ |

包完整性：manifest 7 个文件 SHA 全部 MATCH。运行使用的 joint.py 为 `3d6056b8…`(census 生产者，**与当前仓库 f5433c2e 不同**——包内快照即为实际飞行字节）;joint_rate.py `0b53a16a…` 与当前仓库一致。

关键事实：终止该飞行的 rate_unmet(tick 98684,lateness 100,019,970ns）发生在**下一组 begin_group 的初始检查**（未产生 rate_group_start 行）；最后一组 work=4,416,316ns ≤ 8ms,**正确未触发**超额报告。诊断 valid=true 仅说明 work 口径自洽，不代表飞行健康；失败由业务 LATE_LIMIT 判定，两者语义分层正确。

## 2. 阻断项

无阻断项。计数、封存、上限、寿命语义在真实数据与对抗测试下均一致。

## 3. 残余注意事项（按源行）

1. `group_work_timing.py:117` + runner-candidate-v2 `record()`(885-886/891 行）:emit 回调异常原样传播进业务 record 路径；诊断输出文件写盘失败可使飞行失败。记账保持诚实（383 行 over_budget 先计，118 行仅成功才计 emitted)；属集成注意项，是否容忍由协调者定。
2. `group_work_timing.py:295-304`：不完整组之后的首个同 segment 组跳过 contiguity/earliest 等式（303-304 行已注明）；此时整份诊断已 valid=false(483-484 行），不会静默通过。
3. `group_work_timing.py:338`：sampled 模式无同 tick CPU 行的 native wait 以 `stage_verified=false` 如实标注，不假装已验证。
4. `group_work_timing.py:162-177`:step 行仅按 tick 序校验（生产者 schema 本无 wall 字段），步进耗时的真实性依赖 cpu 行留存采样。
5. 状态有界性经洪水测试实证：`_reasons` 上限 8(121-123 行）、当前组 cpu/native/steps 各 ≤4(190-198、170-177 行）、`_previous` 单组（392-393 行）;300 组+100 垃圾行+200 乱步后无增长，计数仍诚实。

## 4. 新增对抗回归测试（本目录 `test_cb_recorder_adversarial.py`,15/15 通过）

状态洪水有界、重复组 start/end 拒绝、零 work 组、忽略类不绑 epoch、跨 epoch 拒绝、同 tick 重锚与 earliest 等式、不完整后续行跳过校验但整体 invalid、int rate/非 4 倍起始 tick/缺 epoch 拒绝、census 无 native 行合法、census native 无同 tick CPU 拒绝（336-337 行）、CPU 窗口超 actual_end 上界拒绝、emit 失败后记账诚实且记录器可用、finish 永不 emit 且幂等（对应 runner 文件寿命：ExitStack 于 868 行关闭文件，1201 行才 finish)、畸形行不污染组、真实夹具 census/sampled 双流直送记录器（sampled 冒充 census 被拒）。既有套件 27/27 亦通过。
