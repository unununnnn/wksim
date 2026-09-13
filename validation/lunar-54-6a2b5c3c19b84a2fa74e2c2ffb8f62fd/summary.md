# #54 `1-full-ledger` Full 覆盖台账摘要

## 票据与边界

- GitHub：#54 `[Luna] 逐项整理 Full 原规格覆盖台账（不判完成）`
- 稳定键：`1-full-ledger`
- 绑定时状态：`OPEN`，标签含 `ready-for-agent`。
- 执行分支：`codex/independent-rgb-integration`
- 执行前 HEAD：`dede070 feat: convert ArUco targets to bounded velocity intents`
- 仅新增 `docs/plan/full-remaining-ledger.json`、`docs/plan/full-remaining-ledger.md` 及本票证据目录；不关闭父票、不裁剪 Full 范围、不宣称项目完成。

## 覆盖内容

输入来源：

- `docs/plan/full-migration-spec.md`：48 条 User Story，源行 `L19–L66`。
- `docs/plan/full-scope-expansion.md`：48 行扩展范围，包含 12 个仿真模式、7 个通信模式、16 个模型材料行和 13 个操作/环境/实验行。
- `docs/plan/README.md:99-177` 与 `published-issues.json`：原始本地票据到 GitHub 父票映射。
- `docs/plan/goal-objective.md:23-29`：G0–G6 退出条件；真实硬件/HIL 边界来自 Full 规格及扩展账本。

台账总计 `96` 条，稳定 ID 命名空间为：

- `US-01..US-48`
- `SIM-01..SIM-12`
- `COMM-01..COMM-07`
- `MODEL-01..MODEL-16`
- `OPS-01..OPS-13`

每条保留原文/原表格行、源文件和行号、父票及实时状态、交叉来源、证据状态、gap 原因和 `gap=true`。父票 CLOSED 或存在报告只记录 `partial-evidence`，仍保留为 gap；开放父票、缺定义、缺资源或缺真实证据记录 `uncovered`。

G0–G6 与 `HARDWARE-HITL` 边界在 JSON 和 Markdown 中单独保留，状态均为“不判完成”。

## 机械验证

精确命令：

```text
python -c "import json; from pathlib import Path; x=json.loads(Path('docs/plan/full-remaining-ledger.json').read_text(encoding='utf-8')); assert x['scope']['entry_count']==96 and x['validation']['source_id_set_equals_ledger_id_set'] and not x['validation']['duplicate_source_ids'] and not x['validation']['duplicate_ledger_ids']; assert [v['count'] for v in x['source_sets'].values()]==[48,12,7,16,13]; assert all(e['gap'] for e in x['entries']); print('ledger validation passed: 96 entries; 48/12/7/16/13; IDs equal; no duplicates; all gaps explicit')"
```

实际结果：退出码 `0`，输出 `ledger validation passed: 96 entries; 48/12/7/16/13; IDs equal; no duplicates; all gaps explicit`；`git diff --check` 通过。

文件身份：

- `docs/plan/full-remaining-ledger.json`：SHA256 `61a58c9065d5f6b0f243aa49cbd476f38a17ce29c7bf12175c194ba582c51b54`，127048 字节。
- `docs/plan/full-remaining-ledger.md`：SHA256 `95d4439f4bec9f274b369f52f5760235a6ff2e6c82e8228a81317c752f3a47b5`，38392 字节。
- 原规格 SHA256：`384335c180e7f7fca6d87332318e5defe94caf3969ec93ffeda277d004350542`。
- 扩展账本 SHA256：`d8b76ddad2f7f707da80292387fd4254ffbce14e708d171bfeb23ffa47224f4e`。
- README 映射来源 SHA256：`0c93bd39e76dbb9885e77b1fdd2d925162949f6ed1722b71b214e7a722adb756`。

证据目录：`validation/lunar-54-6a2b5c3c19b84a2fa74e2c2ffb8f62fd`，保存票据选择、验证命令、验证 stdout、验证结果和哈希清单。

## 完成判定与未覆盖范围

本票完成条件满足：所有原 Full 用户故事/扩展行均显式保留，ID 集合机械相等且无重复/遗漏，已有父票/报告逐项链接，未确认范围均明确列为 gap，G0–G6 和硬件边界未被删除或误判完成。可以评论并关闭 #54。

本票只交付覆盖台账，不证明任何剩余 Full 行已完成；#55 Astra 票仍负责复核台账并把真实缺口转换为后续实施票。
