# CodeBuddy module-review 三候选 P3 处置独立复审（2026-09-14-02）

只读复审；唯一写入本目录（`review.md` / `review.json` / `SHA256SUMS`）。未修改任何候选文件或既有文件（独立审查 -01 目录经 SHA256 复验原样保留）；未运行 native/构建/MATLAB/ROS/DDS/SITL/飞控/UE/模型/飞行；未重跑 #83；未提交 Git；未联网；未触碰受保护文件（`docs/Prometheus.gitmodules.reference`、`validation/coordination/short-cycle-dispatches.json`——本复审前后 SHA256 逐字节一致，见 §5）。

权威 HEAD `31e5b65f5448c5558450d16d0f46da0ef0f0a03c`（现场 `git rev-parse` 验证）；架构祖先 `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` 经 `git merge-base --is-ancestor` 复验为当前 HEAD 祖先（exit 0）。

## 1. 字节绑定（现场重算，含修订版新哈希）

| 候选 | 期望 SHA256 / 大小 | 实测 | 判定 |
| --- | --- | --- | --- |
| `docs/coordination/codebuddy-module-review-20260912.md` | `7fd97029…f2e2db` / 7544 B | 同左 / 7544 B | 一致（未改动） |
| `docs/coordination/codebuddy-module-review-ingest-note-20260914.md` | `0841c96a…e27703` / 8221 B | 同左 / 8221 B | 一致（修订版） |
| `validation/test_codebuddy_module_review_context.py` | `bc56db56…fa0fd2fd` / 12778 B | 同左 / 12778 B | 一致（修订版） |

被绑定文件 `codebuddy-module-review-20260912.md` 哈希与 -01 复审记录完全相同（7fd97029…/7544 B），确认 review -01 对应的源快照未被本次修订触碰。三候选均为 untracked（`??`）；全部锚文件（ds-rate-budget-20260912.json、plan 33、claude-native-input-timing、ds-26-host-recheck-20260912.json、test_build_generated_e0.py、joint_profile.py、joint_rate_probe.py、joint.py、两个受保护文件）经 `git ls-files --error-unmatch` 确认 tracked，其中七个锚文件 `git status --porcelain` 干净。

## 2. 五项 P3 处置独立验证（不经由候选自述，全部现场重证）

**P3-1（219-220 现在时引用）——处置成立。** 现场实测 `Simulator/wksim_runtime/joint_profile.py`：marker 循环 `for marker in ('rate_timing_probe', 'group_work_timing', 'perf_switch_capture'):` 位于 **:274**，`raise ValueError('Formal mixed/PV evidence cannot include '+marker)` 位于 **:276**；:219-220 现为无关代码（`_raw_proof` 的 return 与空行）。note §2.2（:25）现以内容锚表述当前门（marker 循环 raise 文本，"当前树位于 :274-276，2026-09-14 于 HEAD `31e5b65f` 现场复核"），并显式登记 tracked JSON 内保留的 `joint_profile.py:219-220` 引用**系历史读数**（2026-09-12 复核时点成立）；本登记不以行号为字节身份缝。与实测一致。

**P3-2（diagnostic_constraint 误归属）——处置成立。** 现场枚举 `ds-rate-budget-20260912.json` 全部 19 个顶层键：**无** `diagnostic_constraint`；该键仅嵌套于 `next_minimal_diagnosis.diagnostic_constraint`（现场递归定位确认）。全部 D1/D2 更正文本（12 条内容锚，`structural_reason` 1057 字符）实测在 `parser_coverage.structural_reason`。note §2.2 现仅归属 `parser_coverage.structural_reason`，并在 §5 处置表注明 "JSON 中 `diagnostic_constraint` 仅嵌套于 `next_minimal_diagnosis`，非更正载体"。修订测试 `test_d2_correction_folded_into_structural_reason_only` 新增 `assertNotIn("diagnostic_constraint", document)` 顶层断言，与实测一致。

**P3-3（测试注释过期引用）——处置成立。** 修订测试 :151 注释与模块 docstring（:7-10）现表述为：JSON 内 `joint_profile.py:219-220` 系 2026-09-12 历史读数；当前门为 marker-loop raise、现处 :274-276、以内容锚现场断言。全文件无残留的现在时 219-220 当前门主张；新增 `test_live_promotion_gate_content_anchor` 以两条内容串锚定 :274-276 机制（实测通过）。

**P3-4（同义反复 mutation 负例）——处置成立。** 逐行核verified：原 `test_missing_d2_gate_text_is_detected` 与平凡 `assertNotEqual` 行数负例**已删除**（grep 复验 0 处）。现存负例全部经由与正例相同的生产式 helper 重跑断言：`test_d1_text_drift_detected_by_production_assertion` / `test_d2_text_drift_detected_by_production_assertion` 在内存变异体上重跑 `d1_folding_ok` / `d2_folding_ok`（先 assertTrue 正例、再 assertFalse 变异体）；D2 负例同时删除历史 219-220 引用串与门槛文本，证明折叠断言不被历史文本单独满足；行数负例改用 `assertEqual(count_lines(drifted), E0_TEST_LINES + 1)`（生产计数器，非平凡恒真）；哈希负例用 `sha256_of_bytes` 证明哈希敏感。全部变异仅内存进行，不触碰仓库文件。各负例覆盖不同漂移类别（哈希/行数/D1 文本/D2 文本/重复键/非有限值），不冗余。

**P3-5（重复键 mutant 脆弱构造）——处置成立。** 原"替换首个 `{`"构造已删除；`test_strict_loader_rejects_duplicate_keys_deterministically` 改为确定性最小字面量 `'{"schema": "a", "schema": "b"}'`，经与正例同一的 `strict_load` 生产式加载器断言拒绝。`strict_load` 的 `object_pairs` 钩子对第二个重复键确定性 raise `ValueError("duplicate key: …")`，无随机性、不依赖文档其余内容；测试实测通过。

note §5 处置表五项映射与两份修订版实际内容逐项核对相符。

## 3. D1/D2/D3 折叠与 D5 活性复验（tracked 锚 + 现场代码双重复核）

- **D1 折叠成立**：`ds-rate-budget-20260912.json` `parser_coverage.structural_reason` 载明 "Correction to the first edition"、"tools/audit_pv_trajectory.py contains zero rate_timing_probe/timing_probe checks" 及五个旗标名；plan 33 载明 "0 处** `rate_timing_probe`/`timing_probe`" 等匹配更正文。
- **D2 折叠成立**：同 `structural_reason` 载明全部六条机制断言串（"does not reject probe rows wholesale"、"fails closed only when the sealed identity block is missing or differs"、"silently ignored by schedule()"、"no rate_timing_probe branch and no else"、"Formal mixed/PV evidence cannot include rate_timing_probe" 等）；219-220 历史引用保留于 JSON；当前门 :274-276 实测在场。
- **D3 折叠成立**：plan 33 两门值域更正串逐字在场；`claude-native-input-timing.md` 载明 `WKSIM_JOINT_CPU_TIMING == '1'` 与"默认关闭"；`joint_rate_probe.py` 三态 raise 文本与 `joint.py:54` `=='1'` 谓词实测在场。
- **D5 活性确认（未折叠，未修复）**：`ds-26-host-recheck-20260912.json` `plan_package.key_discovery.why_it_matters` 仍写"已带 **782** 行测试"（现场定位在场），全 JSON 无 "886" 字样；现场 `wc -l validation/test_build_generated_e0.py` = **886**（文件 tracked、工作树干净）。782-vs-886 活性差异在当前树确凿存在；候选批次只登记、未修改 D5 源——与 note §2.4 声明一致。

## 4. 边界复验

- **historical-only / 非权威**：note §0/§1 明示 "historical context only"、"非权威"，绑定仅及 2026-09-12 观察时刻——原文在场。
- **非批准/非收口**：note 明示"不构成任何验收、批准、收口或复核记录"、"不声称：D5 已修复"、"不修改 tracked D5 源"；D5 源实测仍为 782，一致。
- **#83 边界**：note §3/§4 明示"未重跑 #83"；无任何验收/收口声称。
- **折叠≠失效**：note 明示"折叠只表示正确语义已进入 tracked 锚"、"源文件按字节保留原样"；被绑定文件字节绑定测试通过，一致。
- **P3 处置不升格**：note §5 明示"不声称 P3 '清零'仅陈述修正完成，最终判定归独立审查/当前权威"——本复审即为该判定来源。

## 5. 测试执行与索引完整性

1. **常规运行**：`python -B validation/test_codebuddy_module_review_context.py -v` → **25 tests, OK**（-01 时为 23；两个同义反复/脆弱测试撤除，新增 live 内容锚与生产式 helper 负例）。
2. **暂存运行**：`GIT_INDEX_FILE` 指向 `%TEMP%` 中 `.git/index` 副本；`git add --force` 恰好 3 个候选（`git diff --cached --name-only` = 3，状态 `A`）；同套件重跑 → **25 tests, OK**。
3. **真实索引完整性**：`.git/index` SHA256 运行前后均为 `7cf4a1989043e82954f59bd4aa704cbee88703cce2aba095428dd3a329ca26b1`（与 -01 复审记录值相同），逐字节一致；真实索引 staged 条目 = 0；三候选仍为 untracked（`??`）；对三候选路径 `git diff --check` 干净；临时索引已删除。
4. **受保护文件**：`docs/Prometheus.gitmodules.reference`（`5aa70302…0223855`）与 `validation/coordination/short-cycle-dispatches.json`（`06e65cc1…62838`）本复审前后 SHA256 逐字节一致。**范围注记**：两文件在本次复审开始前即呈工作树 ` M` 状态（前者为纯行尾差异、后者为过期时间戳字段），属既有工作树状态，与本次复审及候选批次无关，未作处置。

## 6. 发现（P1/P2/P3，不降级）

**无 P1、无 P2、无新增 P3。** -01 的五项 P3 全部处置成立（§2 逐项现场重证）；五项处置均不引入新缺陷。处置不改变任何绑定、D5 782-vs-886 活性事实或非验收/历史边界。

**范围限制**：2026-09-12 复核中模块 1/2/3 的历史 SHA 快照仍未逐一重验（沿用 -01 范围界定）；受保护文件的既有 ` M` 工作树状态未追溯成因。历史内容仅对其观察时刻有效。

## 7. 结论

**判定：PASS（0×P1 / 0×P2 / 0×新增 P3；-01 五项 P3 处置全部验证成立）。** 三候选字节匹配（含修订版新哈希；源快照 7fd97029… 与 -01 记录相同，确认未改动）；五项 P3 处置经现场代码、tracked 锚与修订测试三重独立验证成立；D1/D2/D3 折叠与 D5 活性（782 vs 886）复验一致；historical-only / 非批准 / 非收口 / #83 边界保持；架构祖先验证通过；测试 25/25 于常规与暂存两态通过，真实索引逐字节未动、候选路径 diff-check 干净。候选作为其声明用途（历史语境绑定、D1–D5 折叠/活性登记、P3 处置登记、离线语境测试）的证据工件可被采信。本复审不构成任何工单（含 #83/#26/#9/#29/#62/#102）的验收、批准或收口。

---

复核结果与机器可读明细见同目录 `review.json`；两个产物文件的 SHA256 见 `SHA256SUMS`。本文件不含自身哈希（自引用不可行）。
