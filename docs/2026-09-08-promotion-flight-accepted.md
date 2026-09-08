# 显式提升飞行机制批准与实现（2026-09-08）

用户原话：**“批准 A：显式提升飞行机制（推荐）”**。

执行 [控制提升死锁提案](2026-09-08-control-promotion-deadlock-and-proposal.md) A。独立实验配置允许严格布尔值 `promotion_flight`；仅显式 `true` 且 `session_v1` 启用。省略或 `false` 保持历史实飞绑定，未知/字符串/数值不放行。联合场景不新增此配置键。

独立 profile 仍完整执行已钉资源、固件源码/产物、控制源码/安装/构建输入、模型、消息和 overlay 校验，只免除 independent catalog 的历史独立飞行绑定。旧 session 入口仍验证历史证据本身、固件/agent/模型/消息及环境；其当前控制源码改与已钉 joint 控制构建清单匹配，并先核验该构建和 session 控制安装包完整快照。提升候选报告 `candidate_status.flown=false`、`flight_provenance="promotion_flight"`，不把一次准入变成实飞证明。

本切片未更改正式示例、profile/能力索引的任何已钉哈希或历史证据。临时键仅用于 validation 候选配置。完成新实飞和审计后，由整体验收步骤审核并安装候选目录，删除可运行候选配置中的提升键，再验证默认预检；原始结果/封存源码保留真实提升标志供审计，不重写历史证据。

## 验证边界

Windows `python -B -m unittest validation.test_promotion_flight validation.test_independent_profile validation.test_wksim_control_profile -v`：24 项，15 通过、9 项因 Linux/实际安装资源条件跳过。五项提升专属测试全部通过，含两栈默认拒绝/提升不声称已飞、资源错误保持拒绝、严格布尔输入、当前构建和完整快照、候选目录不覆盖准入文件。日志：[unit-tests.log](../validation/promotion-flight-20260908/unit-tests.log)。模拟报告不构成构建或实飞证据。真实预检/实飞/集中矩阵由主代理继续执行。

本次模型核验来自 `C:/Users/PC/.codex/sessions/2026/09/08/rollout-2026-09-08T13-53-26-01a07f5d-25fe-7113-b3ba-c5dd77a217d0.jsonl` 的实际 `turn_context`：`gpt-6-astra`、`effort=low`，未委派嵌套任务。Codebase Memory 实读 `wksim-prometheus` ready（50,515 节点、163,780 边）；build_identity 的收窄图查询无结果，实际文件按已知路径读取，不据此断言无实现或覆盖完整。此次改动后无依赖新结构的图查询，也未重新索引。

## 运行与候选目录重建

以下命令在 WSL Ubuntu-22.04 仓库根目录执行。先冻结本轮运行源码；提升期间继续编辑同一源码会使封存审核如实失败。

仅从正式 `*-mission.json` 复制到新的候选目录，再添加临时键和唯一 run_id，不编辑正式示例：

```python
import json
from pathlib import Path
out = Path('validation/promotion-flight-20260908/configs')
out.mkdir(exist_ok=False)
for stack in ('px4', 'arducopter'):
    config = json.loads(Path(f'Simulator/wksim_runtime/examples/{stack}-mission.json').read_text())
    config.update(run_id=f'promotion-{stack}-20260908', promotion_flight=True)
    (out / f'{stack}.json').write_text(json.dumps(config, indent=2) + '\n')
```

按 `joint-profiles.json` 中 `setup_files` 的顺序 source overlay 后，运行正式独立提升：

```bash
python3 -B tools/validate_independent_profile.py validation/promotion-flight-20260908/configs/px4.json --output validation/promotion-independent-px4-20260908
python3 -B tools/validate_independent_profile.py validation/promotion-flight-20260908/configs/arducopter.json --output validation/promotion-independent-arducopter-20260908
python3 -B tools/rebuild_promotion_evidence.py --independent validation/promotion-independent-px4-20260908 validation/promotion-independent-arducopter-20260908 --output validation/promotion-flight-20260908/independent-candidate
```

重建工具重新审核真实三航点、请求、truth、进程映射和运行源码，封存源码，再以封存源码重跑审核，输出 `flight-audit.json`、`flown-source/manifest.json`、`independent-profile-evidence.candidate.json`。原目录必须已在仓库内；输出必须是新的 validation 子目录。

capability-index `session_v1` 消费既有六请求 diagnostic schema，不可把 formal independent result 改名填入。其对应实飞入口为：

```bash
WKSIM_CONTROL_PROTOCOL=session_v1 bash tools/run-prometheus-validation.sh px4 /root/wksim-dds-VxM6Ni /root/wksim-ros2-MUlZd0
WKSIM_CONTROL_PROTOCOL=session_v1 bash tools/run-prometheus-validation.sh arducopter /root/wksim-dds-VxM6Ni /root/wksim-ros2-MUlZd0 /root/wksim-ap-dds-yaw-state-4Wr27s
```

该旧 diagnostic 会调用既有 `build_model()`；本切片未执行它。入口使用独立 net/ipc/mnt 空间，并在输出中给出新 `validation/px4-dds-*/result.json`、`validation/arducopter-dds-*/result.json` 路径。用实际返回的两个新路径作为 `--session PX4_RESULT AP_RESULT`，例如：

```bash
python3 -B tools/rebuild_promotion_evidence.py --session "$px4_result" "$ap_result" --output validation/promotion-flight-20260908/session-candidate
```

工具验证当前控制构建/完整安装快照及原 `control_profile` 六请求、双栈一致、固定固件/模型/agent 等条件，仅输出 `capability-index.candidate.json`。它既不修改默认 INDEX，也不修改任何 baseline、profile 或正式配置；无完整双栈新证据不能宣称此次提升完成。
