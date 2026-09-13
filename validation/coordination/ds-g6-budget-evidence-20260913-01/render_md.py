"""Render audit.md from audit.json (read-only over retained originals)."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
audit = json.loads((HERE / 'audit.json').read_text(encoding='utf-8'))
q = audit['quantities']
by_slot = {row['slot']: row for row in q}


def group(title, slots):
    lines = ['### ' + title, '',
             '| 槽位 | 观测量 | 单位 | 权威来源（历史11.0 / 当前11.8） | frame | datum | 相位 | 首步13态覆盖 | 同源C0整时序 | R1失败值 |',
             '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for slot in slots:
        row = by_slot[slot]
        hist = row['text_fields']['source_mapping_historical_r1']
        cur = row['current_line_ranges']
        cur_text = ('当前11.8行 %s' % (cur[0][0] if cur and len(cur) == 1 and cur[0][0] == cur[0][1]
                                      else cur)) if cur else '当前11.8行 未绑定'
        first = ('是' if row['text_fields']['sample_phase'] and
                 row['comparison_coverage']['first_step_alignment'].startswith('mapped') else '否')
        c0 = row['comparison_coverage']['same_source_full_series_c0']
        c0_diff = c0.split('different_values=')[1].split(';')[0].strip()
        c0_text = '501/501比，差异%s' % c0_diff
        fail = row['r1_failure']
        fail_text = ('%d（%s）' % (fail['failed_values'],
                                  ','.join('%s %d' % kv for kv in sorted(fail['by_case'].items())))
                     if fail['failed_values'] else '0')
        lines.append('| `%s` | %s | %s | `%s` / %s | %s | %s | %s | %s | %s | %s |' % (
            slot, row['observable'], row['unit'], hist, cur_text,
            row['frame'] or '**null**', row['datum'] or '**null**',
            'major_root_output', first, c0_text, fail_text))
    lines.append('')
    return lines


vehicle_slots = ['Vehicle60[%d]' % i for i in range(2, 33)]
sensor_slots = ['Sensor30[%d]' % i for i in range(0, 14)]
gps_slots = ['GPS30[%d]' % i for i in range(0, 11)]

out = []
out.append('# G6 当前逐量误差预算证据链（只读审计）')
out.append('')
out.append('- `audit_id`: `ds-g6-budget-evidence-20260913-01`')
out.append('- 日期：2026-09-13')
out.append('- 工作类别：new-development / 只读证据审计（不构建、不运行 native/MATLAB/ROS/飞控/模型/UE）')
out.append('- 实际 cwd：`C:/Users/PC/Documents/odid编译/wksim`，分支 `main`，HEAD `%s`'
           % audit['checkout']['head'])
out.append('- 架构祖先 `f333316e6efa6b299b4288a9d91fb2bccedfb9d6` 检查退出码 **%d**'
           % audit['checkout']['architecture_ancestor_exit_code'])
out.append('- 冻结 R1 合同 SHA256 `%s`' % audit['identity']['r1_contract']['sha256'])
out.append('')
out.append('> 本审计**不发明、不放宽、不批准**任何 epsilon。所有预算字段保持原状（R1 全 0；'
           '同源新合同不存在）。')
out.append('> `tools/run_e0_same_source_conformance.py`（同源入口）**已存在且已实现**；'
           '缺失的是有依据、已 approved 的逐量预算与执行身份，不是入口。')
out.append('')
out.append('## 1. 结论摘要')
out.append('')
s = audit['summary']
out.append('| 项 | 值 |')
out.append('| --- | --- |')
out.append('| 输出槽总数 | %d |' % s['quantities_total'])
out.append('| 计入本审计的 dynamic/物理量槽 | %d |' % s['quantities_audited_dynamic'])
out.append('| 保留槽/接口元数据槽 | %d |' % s['quantities_metadata_or_reserved'])
out.append('| **有 approved epsilon 的槽** | **%d** |' % s['slots_with_any_approved_epsilon'])
out.append('| slot manifest 已绑定 frame 的槽 | %d |' % s['slots_with_frame_binding'])
out.append('| slot manifest 已绑定 datum 的槽 | %d |' % s['slots_with_datum_binding'])
out.append('| slot manifest 仍未解析（56/56） | %d |' % s['slots_unresolved_in_slot_manifest'])
out.append('| 当前 11.8 RHS 解析为 `terminal` 的槽 | %d |' % s['slots_with_current_11_8_rhs_resolved'])
out.append('| R1 跨版本失败值 / case-轴 / 比较数 | %d / %d / %d |' % (
    s['r1_cross_version_failed_values'], s['r1_cross_version_failed_case_scalars'],
    s['r1_cross_version_comparisons']))
out.append('| 同源 C0 整时序离线比较 | %d 值，%d 处不同 |' % (
    s['same_source_c0_compared_values'], s['same_source_c0_different_values']))
out.append('| 首步映射态 / 总状态 | %d / %d |' % (
    s['first_step_mapped_states'], s['first_step_total_states']))
out.append('| 首步 stage+末态差异条目 | %d |' % s['first_step_stage_and_final_differences'])
out.append('| 同源入口状态 | %s |' % s['same_source_entry_status'])
out.append('| `physical_accuracy` / `g6_acceptance` | `%s` / `%s` |' % (
    s['physical_acceptance'], s['g6_acceptance']))
out.append('')
out.append('## 2. 三个必须区分的层次')
out.append('')
for key, label in (('structural_alignment', '结构 aligned（结构对齐）'),
                   ('first_step_alignment', '首步对齐'),
                   ('full_time_series_numerical_acceptance', '完整时序数值验收')):
    out.append('**%s** — %s' % (label, audit['three_distinct_levels'][key]))
    out.append('')
out.append('结论：现有全部"aligned"字样只到第一、第二层。**第三层从未到达**：没有任何槽拥有已批准的 '
           '`abs_budget`/`rel_budget`/`rms_budget`，也没有带 `execution` 块的同源合同文件存在。')
out.append('')
out.append('## 3. 权威来源与约定')
out.append('')
for key, value in audit['authoritative_sources'].items():
    out.append('- `%s`：%s' % (key, value))
out.append('')
c = audit['conventions']
out.append('| 约定 | 值 |')
out.append('| --- | --- |')
out.append('| 时间网格 | %s |' % c['time_grid'])
out.append('| 采样相位 | %s |' % c['sample_phase'])
out.append('| native 时间字段 | %s |' % c['native_time_fields'])
out.append('| 数组 | %s |' % c['arrays'])
out.append('| 输出端口 | %s |' % c['output_ports'])
out.append('| 冻结 metric 标识 | `%s` |' % c['frozen_metric'])
out.append('| frame 状态 | %s |' % c['frame_state'])
out.append('| datum 状态 | %s |' % c['datum_state'])
out.append('')
out.append('## 4. 逐量证据表')
out.append('')
out.append('单位来自冻结 R1 `observables[].native_unit`；历史来源是 11.0 ZIP 已绑定行号；当前 11.8 '
           '行号来自 `e0-current-source-mapping-20260912.json`（生成源 SHA `2c25b3fa…`，与本次 C0 '
           'native 记录 `original_cpp_sha256` 相同）。`frame`/`datum` 在 slot manifest 中 56/56 全为 `null`。')
out.append('')
out += group('4.1 状态量（`Vehicle60`）', vehicle_slots)
out += group('4.2 传感器量（`Sensor30`）', sensor_slots)
out += group('4.3 GPS 量（`GPS30`）', gps_slots)
out.append('### 4.4 导数量（显式分组）')
out.append('')
out.append('| 槽位 | 观测量 | 单位 | 语义 | 当前11.8行 | 当前11.8 RHS解析 | R1失败值 |')
out.append('| --- | --- | --- | --- | --- | --- | --- |')
for row in q:
    if row['kind'] != 'derivative':
        continue
    cur = row['current_line_ranges']
    out.append('| `%s` | %s | %s | %s | %s | `%s`%s | %d |' % (
        row['slot'], row['observable'], row['unit'], row['semantic_status'],
        (cur[0][0] if cur and len(cur) == 1 and cur[0][0] == cur[0][1] else cur),
        row['rhs_resolution'].get('status'),
        ('/' + str(row['rhs_resolution'].get('reason'))
         if row['rhs_resolution'].get('reason') else ''),
        row['r1_failure']['failed_values']))
out.append('')
out.append('导数量补充事实：')
out.append('')
out.append('- `Vehicle60[24:26]` 是**机体系速度导数**，按 `Simulator/wksim_core/README.md:52` '
           '**不是**加速度计比力；`Sensor30[1:3]` 才是 IMU 比力通道。两者不可跨量比较。')
out.append('- 首步分歧被定位到 `p,q,r` 导数 index 1（stage 2, t=0.0005），参考 '
           '`bc56d4db33a987b8` vs 目标 `bc56d4db33a987b9`，**1 ULP**；上游'
           '（`rtb_IntegratorSecondOrderLimi_d`、`Selector2`、`M1/Fd/Sum1_a/TT0gLR/Sum4_f`）'
           '**尚未**双引擎逐位捕获，根因未证明。')
out.append('- 对角快路径候选在 13 个映射态与 5 次 mrdivide 结果上与参考一致，但 guard review 证明该'
           '分支在其中一个分量上比正确舍入除法**低 1 ULP 精度**；参考求解器是否为"乘以倒数"仍未定。')
out.append('- `L5`：通用求解体在 `d = 5e-324` 且分子非零时算得 `0 - 0*inf = NaN`，快速路径守卫会'
           '正确落回，但通用体本身不是修复；对保留惯量不可达。')
out.append('')
out.append('### 4.5 时间字段')
out.append('')
tf = audit['time_fields']
out.append('- 权威：`%s`' % tf['authority'])
out.append('- 三参考文件时间首列：product 形式匹配 **%d/501**，division 形式匹配 **%d/501**。'
           % (tf['reference_row_time_product_matches'], tf['reference_row_time_division_matches']))
out.append('- 与"先除法再缩放"的差异行数：Vehicle60 **%d**，Sensor30 **%d**，GPS30 **%d**。'
           % (tf['differs_from_division_then_gain']['Vehicle60'],
              tf['differs_from_division_then_gain']['Sensor30'],
              tf['differs_from_division_then_gain']['GPS30']))
out.append('- `budget_approved=%s`，`g6_acceptance=%s`。' % (tf['budget_approved'], tf['g6_acceptance']))
out.append('- 四条时间/相位前置记录**全部** `acceptance=false`：')
for key, value in tf['prospective_rules'].items():
    out.append('  - `%s`：status `%s`，acceptance `%s`%s' % (
        key, value['status'], value['acceptance'],
        ('，budget_approved `%s`' % value['budget_approved']) if 'budget_approved' in value else ''))
out.append('- 结论：%s' % tf['status'])
out.append('')
out.append('## 5. 现有比较覆盖与失败数量')
out.append('')
out.append('| 层次 | 覆盖 | 差异/失败 | 是否数值验收 |')
out.append('| --- | --- | --- | --- |')
out.append('| 结构 aligned | 120/120 槽解析、501 行、1 ms 网格、120 值/样本、终态记录、内嵌 source identity | 0（结构） | 否 |')
out.append('| 首步对齐 | %d/%d 状态 + 5 次 mrdivide 操作数/结果，单一工况 C3G，k=0→1 | stage+末态 %d 条；最早 1 ULP | 否 |'
           % (s['first_step_mapped_states'], s['first_step_total_states'],
              s['first_step_stage_and_final_differences']))
out.append('| 同源 C0 整时序（离线诊断） | %d 值 = 501×120 | %d 处不同（`Sensor30[10]` k=153/k=181），'
           '零 approved 预算 | 否（`g6_acceptance=false`） |'
           % (s['same_source_c0_compared_values'], s['same_source_c0_different_values']))
out.append('| R1 跨版本三工况 | %d 值 | **%d** 失败值，**%d** 个 case/轴，C0/C2G/C3G = 2/1943/3739 | '
           '否（`numerical_failed`，`physical_accuracy=unverified`） |'
           % (s['r1_cross_version_comparisons'], s['r1_cross_version_failed_values'],
              s['r1_cross_version_failed_case_scalars']))
out.append('| 完整时序数值验收 | **0 槽** | — | **从未到达** |')
out.append('')
out.append('### 5.1 R1 失败按观测量聚合')
out.append('')
out.append('| 观测量 | 槽 | 失败值 | C0 | C2G | C3G | 最大绝对误差 |')
out.append('| --- | --- | --- | --- | --- | --- | --- |')
agg = audit['failure_aggregate_by_observable']
for name in sorted(agg, key=lambda n: -agg[n]['failed_values']):
    e = agg[name]
    out.append('| %s | %d | %d | %d | %d | %d | %s |' % (
        name, len(e['slots']), e['failed_values'],
        e['by_case'].get('C0', 0), e['by_case'].get('C2G', 0), e['by_case'].get('C3G', 0),
        ('%.6g' % e['max_abs_error']) if e['failed_values'] else '—'))
out.append('')
out.append('R1 聚合：最大 ULP 距离 **%d**，最大相对误差 **%.6g**，符号翻转 **%d**，'
           '比值落在 [0.5,2] 之外 **%d**，参考恰为 0 的失败 **%d**。'
           % (audit['r1_cross_version']['aggregate']['max_ulp_distance'],
              audit['r1_cross_version']['aggregate']['max_relative_error'],
              audit['r1_cross_version']['aggregate']['sign_flip_count'],
              audit['r1_cross_version']['aggregate']['ratio_outside_half_to_two_count'],
              audit['r1_cross_version']['aggregate']['reference_exact_zero_count']))
out.append('')
out.append('### 5.2 同源 C0 与 R1 的关系（不得混用）')
out.append('')
out.append('- 同源 C0 使用**保留的 11.8 生成源** native 记录（`2c25b3fa…`）+ normal 参考，'
           '零预算、诊断标签；它证明"同源入口可离线重跑并复现 2 处差异"，**不**证明 G6。')
out.append('- R1 是 **ZIP 11.0 native vs SLX 11.8 normal** 的跨版本零容差保留规则，'
           '是比 Full 更强的特定条件，其 5684 失败值**原样保留**，不得用同源 C0 结果覆盖或改判。')
out.append('')
out.append('## 6. 缺失的批准依据')
out.append('')
out.append('| 缺口 | 现状 | 谁能解除 |')
out.append('| --- | --- | --- |')
for b in audit['blockers']:
    out.append('| `%s` %s | %s | %s |' % (
        b['id'], b['statement'],
        '；'.join('需要：' + x for x in b['evidence_needed']),
        b['discharge_authority']))
out.append('')
out.append('逐槽的共同缺项（56/56）：`abs_budget` / `rel_budget` / `rms_budget` 无任何有依据的数值；'
           '`frame=null`；`datum=null`；slot manifest 的 `version`/`hash` 未绑定当前 11.8 生成源；'
           '没有指明 metric、语义、datum 与适用域的 owner-approval record。')
out.append('')
out.append('已存在的、**不能**当作预算的东西（`docs/plan/59-e0-dynamic-budget-source-map.md` 明确禁止反推）：'
           'R1 差值、候选/探针差值、RK4 阶数或网格收敛、模型噪声幅值/种子/增益、传感器教学资料、'
           'SITL 航点门槛、`double` epsilon。')
out.append('')
out.append('## 7. 同源入口的实际行为（已实跑，非推断）')
out.append('')
ep = audit['entry_probe']
out.append('- 工具：`%s`（SHA256 `%s`）' % (ep['tool'], ep['tool_sha256']))
out.append('- 对冻结 R1 合同的真实调用：`%s`' % ' '.join(ep['real_invocation_on_r1']['argv']))
out.append('  - 观测结果：`status=%s`，退出码 **%d**，`matlab_launched=%s`，`native_launched=%s`'
           % (ep['real_invocation_on_r1']['observed_status'],
              ep['real_invocation_on_r1']['observed_exit_code'],
              ep['real_invocation_on_r1']['matlab_launched'],
              ep['real_invocation_on_r1']['native_launched']))
out.append('  - 阻塞原因：`%s`' % ep['r1_refusal'])
out.append('- 次序探针：%s' % ep['ordering_probe']['method'])
out.append('  - `validate_contract` 阻塞原因：`%s`' % (ep['ordering_probe']['validate_contract_reasons'] or '空'))
out.append('  - `validate_execution`：`%s`' % ep['ordering_probe']['validate_execution_result'])
out.append('- 结论：%s' % ep['conclusion'])
out.append('')
out.append('## 8. 稳定 SHA 与可执行的下一次重核')
out.append('')
out.append('交付物（本目录独占写入，交付后停止写入）：')
out.append('')
out.append('| 文件 | 角色 |')
out.append('| --- | --- |')
out.append('| `audit.md` | 本报告 |')
out.append('| `audit.json` | 机器可读逐量台账与阻断项 |')
out.append('| `build_audit.py` | 只读生成器（重跑即重建 audit.json） |')
out.append('| `verify_inputs.py` | 只读重核脚本（身份 + 失败数 + 同源 C0 复算） |')
out.append('| `.gitattributes` | 固定本目录文本行尾，避免 CRLF 混入哈希 |')
out.append('| `write_manifest.py` | 生成 `manifest.json` 与 `SHA256SUMS` |')
out.append('| `manifest.json` | 交付范围、checkout 身份与非声明 |')
out.append('| `SHA256SUMS` | **交付物自身的权威 SHA256 清单（内容寻址终点，不反向被引用）** |')
out.append('')
out.append('交付物自身的稳定 SHA256 记录在 `SHA256SUMS`（由 `write_manifest.py` 最后生成，'
           '该文件不再引用任何清单，因此不存在自引用）。')
out.append('')
out.append('被本审计引用的全部原件身份（生成时刻实测，`verify_inputs.py` 可复现）：')
out.append('')
out.append('| 原件 | SHA256 |')
out.append('| --- | --- |')
for item in audit['identity']['materials']:
    out.append('| `%s` | `%s` |' % (item['path'], item['sha256'] or '（不存在）'))
out.append('')
out.append('重核命令：')
out.append('')
for i, step in enumerate(audit['next_recheck_commands'], 1):
    out.append('%d. %s' % (i, step['purpose']))
    out.append('')
    out.append('   ```')
    for line in step['command'].splitlines():
        out.append('   ' + line)
    out.append('   ```')
    out.append('')
    out.append('   期望：%s' % step['expected'])
    out.append('')
out.append('## 9. 非声明与阻断项')
out.append('')
for item in audit['non_claims']:
    out.append('- %s' % item)
out.append('')
out.append('只有表 6 中列出的授权方能解除对应阻断项；本审计不自批准、不代批准、不放宽任何门槛。')
out.append('')

(HERE / 'audit.md').write_text('\n'.join(out), encoding='utf-8', newline='\n')
print('wrote', HERE / 'audit.md')
