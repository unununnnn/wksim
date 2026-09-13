# DeepSeek 组审计 CLI 独立评审（claude-ds-audit-review-20260913-01)

对象：`validation/ds-group-audit-20260913-01/`（更正副本 `validation/coordination/ds-group-audit-20260913-01` 评审时不存在；下列 SHA 仅针对原始交付，作者后续改动不在其内）。

## 钉扎的输入 SHA-256（评审起点）

- `ds_group_audit.py` `e3e01d1a6512640d288d96410518b830fa0a4a5a76db357c780d00ee35697e83`
- `test_ds_group_audit.py` `6bba306f703b22ced265ae84a0fc5ca61d23418abf120a6900c3dca4bef43071`
- 作者证据 `evidence/joint-public-flight-rfw9nmbb-audit.json` `13f6c0d3…f83d5`;`FINDINGS.md` `3fdea073…b398`
- 真实数据：`cb-evidence-pack-20260913-01/pack`（manifest 七文件 SHA 全部 MATCH;rate.jsonl.gz `19584804…362e`)

## 基线核对（非重复作者测试）

- 作者套件实跑：67 项方法，66 过 1 跳过（真实存档集成默认跳过）——"67 tests"声明属实。
- 真实 CLI 跑真实包（rate.jsonl.gz 解压至本目录 work/)：verdict=pass,0 错误，与作者证据结论一致。
- 数学声明核验：`waits_with_cpu_over_wall`=72/80（比率 0.9）与文档字符串逐字一致；16/18 留存覆盖属实，被丢弃两组 tick 80652/98044 如实命名、measured=false;period 经 Fraction 精确截断。均无虚报。

## 阻断项（均可用本目录 work/ 内字节级复现）

以下变体全部由**真实 CLI**（非 mock）判定 pass，而流本身的结构缺陷在原始数据内可见：

1. **上限定律未校验（最严重）**：审计自述"发出的报告恰是流序前 report_limit 个"（文档字符串第 4 条），但代码只查 `len(seen) <= report_limit`(ds_group_audit.py:769-772,1067-1069）与"前导一致"(1070-1079)，从未校验 `emitted == min(over_budget, limit)`。复现：真实报告流截到前 10 份 + result 计数改 emitted=10/dropped=8(`rate-report.jsonl`→`reports-e5a.jsonl`,`result-e5a.json`)→ **pass**；更极端：空报告流 + emitted=0/dropped=18(`reports-e5b.jsonl`,`result-e5b.json`)→ **pass**。真实记录器在 reports_enabled=true 下 18 个超额必然发出 16 份，零发出/欠发不可能诚实产生。
2. **尾部未闭合组不报警**：删去最后一条 rate_group_end(98684 组 98680）后，流内 starts=24661 > ends=24660 直接可见，且保留的 rate_unmet@98684 只有在该组闭合后才可能产生（joint_rate.begin_group 要求组已闭合）；诚实记录器会报 valid=false+unfinished_group。只需把 result 的 groups_complete 改为 24660 即 **pass**(`rate-e1.jsonl`,`result-e1.json`,`audit-e1.json`：自身报告 group_starts 24661 vs group_ends 24660 仍判 pass)。缺"orphan-start/首尾数相等"检查（配对只查 orphan end,322-325 行）。
3. **重复 rate_group_end 不查**：重复 start 键有检查（260-261),end 键没有；重放把重复 end 双计入 groups_in_order(327-328)。复现：复制末条 end 并把 declared 改为 replay 的语义（complete 24661/incomplete 1)→ **pass**(`rate-e2.jsonl`,`result-e2.json`,`audit-e2.json`)。诚实记录器对该流必报 orphan end 错误、valid=false。
4. **rate 流无全局顺序/tick 单调校验**：把全部 end 行整体移到文件尾（相对序不变）→ **pass**(`rate-e4.jsonl`)。审计称这些行"实际调度了飞行"，但不验证流序。
5. **行 tick 与组边界 tick 不核对**：消费者的真实规则要求 start 行 tick==start_tick、end 行 tick==end_tick(group_work_timing.py:278、351-352)；审计的 start/end 校验从不引用 row tick。微型单组存档 start tick=77/end tick=88（边界字段全对）→ **pass，零 finding**(`rate-e3.jsonl` 等）。"重放消费者记账规则"的注释（197-199 行）言过其实。

## 非阻断确认

报告内容校验本身严密：边界等式、分解恒等式、阶段包含、前导序、计数器比较均为 fail-closed；孤儿 end、篡改字段均有正面拒绝；`emit()` 写盘失败正确升级为 fail;findings 截断计数诚实；`result.json` 的 valid/unfinished/分类门槛合理。

## 覆盖限制

- 内部一致性审计本质上无法识别**完全自洽的伪造**；上述阻断项的共同点是缺陷在原始流内结构可见、无需信任何声明计数即可发现，修复成本低（加：emitted==min(over,limit)、starts==ends+悬空 start、重复 end、行 tick==边界 tick、可选流序单调检查）。
- 记录器级诊断行拒绝在 rate 流中不可见（作者已于 1102-1108 行如实声明），不在本次发现之列。
- 本评审未分析任何 native 成因，未做泛组排名重复工作；未把该诊断标为 pass。

## 复现方式

```
python validation/ds-group-audit-20260913-01/ds_group_audit.py \
  --rate <work>/rate-<e1|e2|e3|e4>.jsonl --group-work-timing <work>/<rate-report|reports-e3>.jsonl \
  --result <work>/result[-<variant>].json
```

变体输入与本报告的 SHA-256 见随附 `shas.json`。
