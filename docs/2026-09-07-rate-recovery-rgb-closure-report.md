# 2026-09-07 倍率优化、RGB 收口与恢复风暴报告

承接 `d14bcd0`，分支 `codex/independent-rgb-integration`。本轮全部由主代理完成：子代理模型配置要求 gpt-6-astra/low，本会话实际可用模型集合不含该项，按既有规则「不支持则主代理完成」执行，没有降级到未核验配置。Goal active；未关闭 Goal 或 G2/Full 任何门槛。

## 结果总览

| 项 | 结果 | 证据 |
| --- | --- | --- |
| WSL 默认矩阵 | 403 通过（38 跳过） | `validation/session-product-checks-J19auvfW/session-tests.log` |
| 旧预检 | 11 通过 | 同目录 `legacy-preflight-tests.log` |
| 安装候选矩阵（新控制候选 PvcpVG） | 79 通过 | `validation/joint-control-checks-d5SpyUI4/tests.log` |
| Windows 产品 | 96 控制台 + 4 RGB 通过 | `validation/windows-product-checks-20260907b/tests-final.log` |
| RGB 生产者停启/重连/冷重置旧 epoch 隔离 | 通过（真实双飞控+UE） | `validation/joint-rgb-lifecycle-20260907-run2/` |
| RGB 空中公共任务实时采集 | 通过（603 消费帧、409 次双机空中观测） | `validation/joint-rgb-airborne-20260907-run2/` |
| 0.5× 生命周期回归（批量收发+2ms 分发+优先级+编码/健康优化，探针已清理） | 通过 | `validation/joint-rate-flow-ox8h58cv/` |
| 持续 1× 倍率 | **仍失败**：最佳连续 31.3 秒（验收 60 秒） | `validation/joint-rate-flow-p9koy63e/` |
| AP 失联恢复（0.5× 倍率监督下） | **失败**：恢复后任务启动风暴超 100ms 预算 | `validation/product-joint-flow-zzr3v4ed/` |

## 实际命令（可复现）

```
bash tools/check-session-product.sh
bash tools/build-joint-control.sh    # 产出 /root/wksim-joint-control-PvcpVG（d14bcd0 控制源码）
bash tools/check-joint-control.sh /root/wksim-joint-control-PvcpVG/build.json 9d3fb44ae20b71f706283e29764776c38c09ba176033ad7e34d928d8d2bbad4e
D:/date/miniconda/python.exe -X utf8 -B -m unittest discover -s validation -p "test_wksim_console_*.py" -v
D:/date/miniconda/python.exe -X utf8 -B -m unittest validation.test_rgb_consumer validation.test_rgb_geometry -v
powershell tools/build-ue55.ps1 -Stage E:/ue5.5/build/wksim-native-rgb-life-20260907-a   # 清单 validation/ue55-build-a61e1371900245b6b2a0ffab531d5ee4/candidate-manifest.json
python tools/validate_joint_rgb.py --manifest validation/ue55-build-a61e1371900245b6b2a0ffab531d5ee4/candidate-manifest.json --lifecycle --output validation/joint-rgb-lifecycle-20260907-run2
python tools/audit_joint_rgb.py validation/joint-rgb-lifecycle-20260907-run2 --output validation/joint-rgb-lifecycle-20260907-run2/audit-physical.json
python tools/validate_joint_rgb.py --manifest validation/ue55-build-a61e1371900245b6b2a0ffab531d5ee4/candidate-manifest.json --airborne --output validation/joint-rgb-airborne-20260907-run2
python tools/audit_joint_rgb.py validation/joint-rgb-airborne-20260907-run2 --output validation/joint-rgb-airborne-20260907-run2/audit-physical.json
python3 validation/rate-wrapper-20260907/wrapper.py 0.5 lifecycle
WKSIM_JOINT_CPU_TIMING=1 python3 validation/rate-wrapper-20260907/wrapper.py 0.5 steady-one-after-ready
python3 validation/product-joint-entry-20260906/run_product_flow.py arducopter
```

`rate-wrapper-20260907/wrapper.py` 与已验收 0.5× cohort（7tcgrb6o/ynhheu8i/iz01zhz7）三份的 wrapper 字节一致（md5 `e9d017bd…` 四处相同），只按 `validation/<dir>/wrapper.py` 层级要求另存。

## RGB 收口（#30）

- UE 构建失败-闭环：首次 `--lifecycle` 因清单与当前 `WksimVisualGameMode.cpp` 哈希不符被拒（`joint-rgb-lifecycle-20260907-run1`，证据保留）；按当前源码重编译（37.74s 增量）后以清单 `a61e137…` 运行。
- `joint-rgb-lifecycle-20260907-run2`：消费者重连首帧 step 3216、3 条旧通知拒绝；生产者禁用 3.03s 内物理推进 1508 步且零新帧；重启生成新 stream_id（fbad3aa3…→d7f8c093…），旧生产者通知被拒绝 1 条；冷重置产生新物理 epoch（0a167ca9…→88ed87a0…），旧 epoch 通知被拒绝 175 条；审计通过（396 原生 PNG、25 消费解码）。
- `joint-rgb-airborne-20260907-run2`：公共任务起飞/保持/航点/降落全程实时 RGB，603 张消费解码、409 次双机空中观测（tick 49592→71020）；审计通过（707 原生 PNG，消费者断开期间物理推进 1504 步）。`run1` 因主代理在飞行中编辑源码触发源身份拒绝（fail-closed 按设计工作），失败样本保留未改判。
- 几何/遮挡四例 60 帧结论沿用 `validation/rgb-geometry-20260907/summary.json`（本轮未变更相关代码路径）。
- 优先级改动在本轮真实栈中记录生效：manager nice -10 + SCHED_FIFO 50；模型/FC nice -10 + FIFO 40；agent/control/task nice -5；全部 `applied` 无 error（见任一 epoch `result.json` 的 `manager_priority`/`manager_scheduler`/`children[*].priority`）。

## 倍率工作与 1× 真实状态

代码改动（均有测试与实飞证据，未放宽任何数值）：

1. `joint_rate.py` 临时 timing_probe 按基准 `validation/rate-timing-diagnosis-20260907/before_timing_probe.py` 精确清理（对 HEAD -14/+1 行），批准的等待环/1ms 保护区不动；产品证据接口为 `joint.py` 的 `WKSIM_JOINT_CPU_TIMING=1` 可选诊断（默认关闭）。
2. AP 传感器包单次序列化（`ap_json.sensor_fields` 共用映射；包字节与原「编码→解析→更新→再编码」完全一致）。
3. `physics_health` 子进程存活性轮询限频 1ms：health 每 1ms tick 至少执行一次，退出检测仍 ≤1ms，远低于批准的 100ms/500ms/2s/3s/5s 监督预算；许可/期限/操作员请求检查保持每次调用。
4. 自有进程调度：manager FIFO 50、模型/FC FIFO 40、agent/control/task nice -5，全部逐进程记录实测值。

实测结论（三组独立真实飞行，逐组迟到分析）：

- 0.5× 系统性漂移约 4.2–4.9µs/组（中位释放粒度仅 0.38–0.41µs）；1× 段漂移 12.7µs/组。**迟到的均值几乎全部由尾部贡献**：每 4ms 组约 1–2% 概率出现 1.4–5ms 停顿。
- nice/SCHED_FIFO 对漂移**无可测改善**（A/B：seg1 4.21→4.85µs/组、seg5 4.62→4.27µs/组，p99 均 ~170–195µs），说明停顿来自 WSL2/Windows 宿主机层（vCPU/中断），Linux 调度类无法消除。RT 配置保留并已记录，不声称收益。
- 编码+健康优化使 1× 连续存活从 23.6s 提升到 **31.3s**（`p9koy63e` seg2：7801 组、98.87ms 冻结）；组内工作中位数降至 health_and_models 327µs/encode 90µs/native_inputs 222µs。验收要求 60 连续秒 ×3 epoch，**当前不满足**，系统按合同如实 `rate_unmet/resource_insufficient` 在最后完整屏障冻结（该行为本身已验证）。
- 0.5× 生命周期回归通过（`ox8h58cv`：含 1×/0.5× 切换、4s 暂停、4 tick 单步、显式继续、全程 151.5s 恢复后段 76.68ms<100ms）。同一 wrapper 的前一轮（`140r0vqz`）曾在恢复后段末遇 20.28ms 单点停顿失败，失败样本保留。

## 新发现：恢复任务启动风暴（0.5× 监督下 AP 失联回归失败）

`product-joint-flow-zzr3v4ed`：Agent 真实终止后物理在 tick 51545 冻结；显式 recover 干净（重锚后 439 组 3.5s 零迟到）；`start-recovery-task` 后两个任务进程启动引发 DDS 发现风暴，PX4 锁步执行器响应在 tick 53608 停顿 **69.57ms**、AP 53609 停顿 15.31ms、PX4 53612 停顿 6.85ms（wire.jsonl 逐记录间隔实测），叠加段内漂移后达 110.01ms>100ms，系统如实 rate_unmet 冻结。物理 1ms 步、4ms 屏障、5s 恢复窗与任务语义均正确；旧恢复验收（61t52y3j/32s6alit）无 rate.jsonl，早于正式入口倍率监督，不能作为对比。PX4 侧同类回归未重跑（机制相同，待决策后一并验证）。

这是「操作员显式 start-recovery-task 是否应像 recover/resume 一样作为分段重锚点」的合同问题，**未替用户决定**；也不排除工程压制（分期 spawn/延迟 DDS 加入）的可能。

## 失败与边界样本（全部保留）

- `joint-rgb-lifecycle-20260907-run1`（UE 清单哈希不符，fail-closed）
- `joint-rgb-airborne-20260907-run1`（飞行中源身份变更拒绝）
- `joint-rate-lifecycle-20260907-run1`（行为通过但布局不被标准审计消费，改用 cohort 同字节 wrapper 重飞）
- `joint-rate-flow-140r0vqz`（0.5× 恢复后段 20.28ms 单点停顿失败）
- `joint-rate-flow-p9koy63e`（1× 31.3s 失败，含 CPU 阶段采样）
- `product-joint-flow-zzr3v4ed`（恢复风暴失败）
- 早前 `default-final-matrix.log` 的环境错误失败亦仍保留。

## 残留与卫生

全部 exec/后台句柄均已到终态；WSL 无 arducopter/px4/Agent/ROS 残留进程；Windows 无 Unreal/RflySim/CopterSim/QGC 残留（matlab-mcp-server 属既有 MCP 服务，非本轮创建，未触碰）。几何审计工具对非 fixture 目录按预期 FileNotFoundError（不适用，非回归）。

## 未决（提交用户）

1. 持续 1×：授权宿主机措施（提高 VmmemWSL Windows 优先级、验收窗口降低桌面负载）后重测 / 继续工程优化 / 如实记录资源限制先推进其他切片。
2. 恢复风暴：修订倍率合同把 start-recovery-task 列为显式分段重锚点（数值不变）/ 工程压制 / 保持开放。

#30 的验收项（身份/时间/内外参/图像、几何与遮挡、断流重连旧代次识别且物理不等待、实际输出与消费者结果留存）已有当前源码真实运行+审计证据；按票据「主代理复核后关闭」流程处理。#19/#20/#21/#22、G2 及 Full 保持 open；未放宽任何阈值，未修改 Wayfinder 父图，未推送远端。
