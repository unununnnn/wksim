# 2026-09-07 失联恢复双侧通过、倍率合同修订与 1× 宿主机重测报告

承接 `572c7bb`，分支 `codex/independent-rgb-integration`。本轮全部由主代理完成（本会话无 gpt-6-astra 可核验配置）。用户对两个未决问题答复「全按照推荐进行」：Q1(a) 授权宿主机措施后重测 1×；Q2(a) 修订倍率合同把显式 start-recovery-task 列为分段重锚点（数值不变）。Goal active；未关闭任何 G2/Full 门槛。

## 结果总览

| 项 | 结果 | 证据 |
| --- | --- | --- |
| AP 失联恢复回归（修订前合同，0.5× 监督） | **通过**（风暴段最大累计 51.14ms<100ms） | `validation/product-joint-flow-etsaqmso/` |
| PX4 失联恢复回归（修订前合同，0.5× 监督） | **通过**（94.18ms<100ms） | `validation/product-joint-flow-nasz1u3f/` |
| 双侧原始审计 | 各两次字节一致 + 篡改负例通过 | `validation/recovery-regression-audit-20260907/`（etsaqmso `a3c5565c…`×2、nasz1u3f `58265803…`×2） |
| 会话矩阵 | 404 通过（38 跳过） | `validation/session-product-checks-DaCUBTh8/` |
| 旧预检 | 11 通过 | 同目录 |
| 安装候选矩阵（PvcpVG 仍有效） | 79 通过 | `validation/joint-control-checks-HwSk02lw/` |
| Windows 控制台 + RGB | 96 + 4 通过 | `validation/windows-product-checks-20260907c/tests.log` |
| 合同修订实现（Q2(a)） | 已实现 + 单测 11/11 | `Simulator/wksim_runtime/joint_runtime.py`、`validation/test_joint_rate.py`、[修订附录](2026-09-07-rate-contract-amendment-start-recovery-task.md) |
| 修订后真实恢复回归 | **4 次尝试全部如实失败**（见下节） | q2qexeye / w1wi0gpj / dtcollzf / 523cme9k |
| 1× 重测三 epoch（vmmemWSL=High） | **47.1 / 41.1 / 23.7s，均未达 60s** | `validation/joint-rate-flow-{bwd4iwsc,wy1_f8pu,h7b729ld}/`、`validation/rate-1x-retest-20260907/audit.json` |

## 实际命令（可复现）

```
python3 validation/product-joint-entry-20260906/run_product_flow.py arducopter   # etsaqmso 通过；修订后 4 次失败样本
python3 validation/product-joint-entry-20260906/run_product_flow.py px4          # nasz1u3f 通过
source /opt/ros/humble/setup.bash && source /root/wksim-dds-VxM6Ni/ros-install/setup.bash && \
source /root/wksim-ap-dds-yaw-state-4Wr27s/ros-install/local_setup.bash && source /root/wksim-ros2-MUlZd0/install/local_setup.bash
python3 tools/audit_joint_product_lifecycle.py <evidence> --output <out.json>     # 每侧两次
python3 tools/check_joint_product_lifecycle_audit.py <evidence> --output <neg.json>
bash tools/check-session-product.sh
bash tools/check-joint-control.sh /root/wksim-joint-control-PvcpVG/build.json 9d3fb44ae20b71f706283e29764776c38c09ba176033ad7e34d928d8d2bbad4e
D:/date/miniconda/python.exe -X utf8 -B -m unittest discover -s validation -p "test_wksim_console_*.py" -v
D:/date/miniconda/python.exe -X utf8 -B -m unittest validation.test_rgb_consumer validation.test_rgb_geometry -v
python3 validation/rate-wrapper-20260907/wrapper.py 0.5 steady-one-after-ready    # ×3 epoch
python3 tools/audit_joint_rate.py validation/joint-rate-flow-bwd4iwsc validation/joint-rate-flow-wy1_f8pu validation/joint-rate-flow-h7b729ld --output validation/rate-1x-retest-20260907/audit.json
```

注：首次审计尝试因缺少 `source /opt/ros/humble/setup.bash`（rclpy 在系统 ROS）如实失败；改正环境后重跑通过，失败中间产物已覆盖。

## 修订后恢复回归四次如实失败（全部保留）

修订实现经单测验证（新锚点归零、transition 标记、100ms 帽在新段内仍锁存、transition 确认不丢弃旧段迟到），但四次真实双飞控尝试均未到达 start-recovery-task（修订锚点未触发，失败点全部在锚点之前）：

1. `q2qexeye`：起飞后 AP EKF origin 复位（`native_clock_or_origin_reset`），按既有边界正确撤销控制；PX4 未起飞，验证器 180s 超时。与修订无关（任务启动路径无行为变化）。
2. `w1wi0gpj` / `dtcollzf` / `523cme9k`：三次同一签名——recover 重连窗口（Agent 重启+DDS 客户端重启的发现风暴）末端单次 >100ms 停顿，在 tick 53304/53820/53208 如实 rate_unmet；恢复窗口内 418–517 组 paced 物理最坏迟到仅 0–0.5ms，recover_confirmed 未及记录。`recover_requested` 过渡锚点在 frozen tick 非 4 对齐时按现合同不触发（三次 frozen tick 51533/51749/51533 均 ≡1 mod 4）。

当晚宿主明显更噪：三场 seg1（注入前 0.5× 段）最坏迟到 74.96–95.40ms，早晨两场通过样本为 48.57/81.93ms。vmmemWSL=High（第 3、4 次尝试生效）未能阻止 recover 窗口末端停顿。**这是 recover 窗口自身的风暴与 100ms 帽的合同问题，已批准的修订不覆盖该窗口**（失败在修订锚点之前）；未替用户决定，见「未决」。

会话中断遗留：`2smbyc4_`（PX4 首试仅 launch.json，上一 Claude 进程退出致后台任务终止，非产品失败；WSL 侧核验无残留进程/端口后已重跑为 nasz1u3f）。

## 1× 宿主机重测（Q1(a) 已授权措施）

措施：经 UAC 提权将 vmmemWSL 进程优先级设为 High，并以 `Get-CimInstance Win32_Process` 核验 priority=13（WSL VM 空闲退出后设置随进程消失，每次运行前重新施加并核验）。三 epoch（cohort 同字节 wrapper、steady-one-after-ready、阈值不变）：

| epoch | 证据 | 1× 连续段 | 冻结迟到 |
| --- | --- | --- | --- |
| 1 | `joint-rate-flow-bwd4iwsc` | **47.1s**（11741 组） | 100.10ms |
| 2 | `joint-rate-flow-wy1_f8pu` | 41.1s（10252 组） | 100.08ms |
| 3 | `joint-rate-flow-h7b729ld` | 23.7s（5863 组） | 252.97ms |

结论：宿主机措施将最佳连续 1× 从 31.3s 提升到 **47.1s**（+50%），但 60s×3 仍不满足；epoch 间方差大（23.7–47.1s），停顿仍源自宿主层。倍率审计对三场正式拒绝计为通过（`rate-1x-retest-20260907/audit.json`）。rate_unmet 诚实冻结行为本身再次验证。

## 残留与卫生

全部后台句柄到终态；WSL 无 arducopter/px4/Agent/ROS/驱动残留，无仿真端口监听；Windows 无 Unreal/RflySim/CopterSim/QGC 残留。失败样本与中断样本全部保留。

## 未决（提交用户）

1. **recover 窗口风暴（新合同问题）**：修订后 3 次尝试均在 recover 重连窗口末端被单次 >100ms 停顿如实冻结（修订锚点之前，修订不覆盖）。选项：(a) 再次修订合同，为 recover 的重连窗口定义显式速率记帐（数值阈值不变，例如使 recover_requested 过渡锚点在恢复受理时即生效而非等待 4 对齐）；(b) 工程压制恢复窗口的 DDS 发现风暴（分期重启/延迟加入）后重测；(c) 保持开放，先以修订前双侧通过证据推进其他切片。
2. **持续 1×**：措施后最佳 47.1s/需 60s×3。选项：(a) 继续工程优化；(b) 更强宿主措施（需用户配合降低桌面负载如 dronecan_gui_tool/codebase-memory 索引等，或指定核）；(c) 如实记录宿主资源限制，G2 的 1× 保持开放，先推进其他切片。

#20/#22/G2/Full 保持 open；未放宽任何阈值，未修改 Wayfinder 父图，未推送远端。
