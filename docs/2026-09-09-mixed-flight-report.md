# #33 真正 XY 速度 / Z 位置候选实飞

2026-09-09。独立 AP mixed 固件和控制候选完成双栈公开任务：世界系阶跃/反向、单轴回中、双轴回中、重新进入、实际机体系一次旋转、绝对停止和正常降落。`joint-public-flight-zk5_nukn` 的逐包、逐 1ms 物理及连续倍率审计通过。**这是有界候选实验；正式 profile 尚未提升，原生停流等异常边界及 #33 其余工作继续开放。** 完整 XYZ P+V 轨迹另见[前一切片报告](2026-09-09-pv-flight-report.md)。

## 身份与真实路径

| 项目 | 本次实际值 |
| --- | --- |
| AP mixed manifest | `/root/wksim-ap-mixed-fhuf05l9/mixed-build.json`，SHA256 `1e6250eff8873d6b2e52017b613c223ac29f8260fdf92aac2cf0c7cdcc6ce94c` |
| AP 实际二进制 | `509c60163b3fceb261d17ceb2d0814c10ec65846e5d8d6689375e3ee05ab731f` |
| PX4 实际二进制 | 固定 state 候选 `93b4ebe0d83a5897131ec24ee58d732c8999972bb7730f429fc396bc8d10602a` |
| 控制候选 | `/root/wksim-joint-control-OEvS3W/build.json`，SHA256 `d9fdfc74f4f241440dd1186ef38d0bde56026cd28e4b55897f38a11e7311909e` |
| run / scene epoch | `joint-public-flight-zk5_nukn` / `263d8f37f21e4ef5b27a7a2f6ab5cb0d` |
| 原始证据 | `validation/joint-public-flight-zk5_nukn/`；原 live 根 `/root/wksim-joint-flight-srs4w1in` |
| 执行源码 | commit `973fcba`；运行内保留 33 份源、9 份实际安装控制源、8 份原生源码及完整 prebuild 源清单 |

实际命令为 `bash tools/run-joint-flight.sh --task-profile xy_velocity_z_position_yaw_v1`，同时显式传入上表的 `--ap-mixed-manifest/--ap-mixed-sha256` 与 `--control-manifest/--control-sha256`。独立 net/ipc/mnt 中先全量核验 24,593 个原生源文件、22 个源仓库、mixed→PV→fixed 构建链及模型/消息/Agent，再创建孩子进程。运行与停止时的 FC/模型加载映射、二进制 SHA 和 PID/PGID/start_ticks 均一致。

七文件原生补丁 `patches/arducopter/0005-dds-mixed-xy-velocity-z-position.patch` 追加 `VelNEPosD=7`，原 position/P+V/velocity 分支保留。AP 接受严格 map/frame6/mask0x9E3：Vxy 与 Pz/yaw 有效，Pxy/Vz/A 失活，NE 速度和 D 位置分别执行。home→origin 转换与实际 Location/Fence 检查在保存目标之前；有限值及平方范数余量检查限制新增输入。水平避障保留，未声称垂向速度避障。首次构建因局部 `ahrs` 遮蔽基类成员而失败并保留；改名后在全新目录构建、封存，不改旧 PV 或 fixed 源。

控制候选的 `arducopter_mixed_profile` 默认关闭且只读。BODY 在 CommandProcessor 首次解析时一次捕获实际位置/四元数，新增只读事件保留解析参考；独立审计从真实公共四元数重算旋转，不能使用稍后姿态替代。AP yaw-rate 组合在公开受理前拒绝；范围/非有限和 BODY 解析范围仍由原流程在本地受理后、原生发布前检查，不混称同一拒绝时点。

PX4 的 Pxy 保持 NaN，Pz/Vxy 有效，Vz=0 是既有零前馈；AP 明确 IGNORE_VZ。两 XY 回中后转完整 P，AP mask0x9F8。world_zero 的 X 延续此次 one-axis 保持锚点、Y 新捕获；BODY 回中按此次实际位置重新捕获，不复用第一段位置。

## 原始结果

共同物理推进 135,328 tick；两机同时高于 1m 共 83.110s。AP 11 个、PX4 10 个连续窗口，以及起飞/位置基线、保持前连续 1.5s 稳定段和落地均逐 1ms 检查。每个 3s/4s 主窗口分别保留 3,001/4,001 个含端点样本，没有丢弃开头或超界样本。

| 指标（主窗口最大值） | AP | PX4 | 原门槛 |
| --- | --- | --- | --- |
| 混合高度误差 | 0.04083m | 0.09797m | ≤0.5m |
| 混合 XY 逐轴速度误差（含单轴回中） | 0.11531m/s | 0.17107m/s | ≤0.3m/s |
| 单轴回中 X 漂移 | 0.07109m | 0.11824m | ≤1m |
| 回中/绝对停止速度 | 0.02189m/s | 0.09175m/s | ≤0.25m/s |
| 回中/绝对停止漂移 | 0.07767m | 0.12921m | ≤1m |
| 所有窗口 yaw 误差（含定点转向） | 0.04486rad | 0.01208rad | ≤0.15rad |

AP 原始 GUIP 日志含 1,948 次 type7 受理，五个真实 mixed 运动窗口全部覆盖；其失活 pX/pY/vZ/A 为零。GUIP 的 pZ 是 origin NED，报告不将其直接等同于 home 高度。公开请求、原生目标发布、setup ACK、GUIP 子模式受理及物理完成分层核对；该目标通道没有目标 ACK，不能把 publish 当 ACK。实际停止 Bool 四次 true/false/true/false 与绝对控制/显式退出匹配，AP 无效 yaw-rate 的 2s 无副作用窗口通过。

0.5× 只有一段连续倍率监督，最大迟到 68,521,667ns＜100ms。全部 32,322 个完整 10s 窗口最大相对误差 0.450560%＜2%；26,072 个完整 60s 窗口最大 0.089433%＜1%。最后先检查倍率并明确停止权威时钟，再读取终态映射；没有把映射耗时计作物理运行，也没有删除活动段尾部。持续 1×/#20/G2 未由此完成。

## 失败与审计修正

[冻结合同](2026-09-09-mixed-flight-plan.md) 保留每次准备段变更及原始失败，物理/倍率门槛和持续测量时长未放宽。

| 轮次 / 目录后缀 | 保留结果 |
| --- | --- |
| 01 / kjbim9c6 | PX4 world_zero 固定 2s 准备后速度约 0.26667m/s＞0.25；失败。随后对回中/绝对保持增加最多 12 墙钟秒、连续 1.5 仿真秒的同条件稳定准备。 |
| 02 / 3frp8j8q | AP 定点 yaw 首次到界后超调，0.151063rad＞0.15；失败。定点转向也增加相同稳定准备。 |
| 03 / _vbxk1vr | 起飞时 AP 实际 yaw reset，控制门正确撤销；失败。没有绕过 reset 保护。 |
| 04 / 4q1lfex8 | 运行时通过并落地，原始审计失败：PX4 三个 moving 窗口开头 1/35/24 tick 高度超界，最大 0.500133/0.519041/0.514306m。后续在首次 ready 后固定准备 2s，再进入原 3s 窗口。 |
| 05 / zk5_nukn | 运行、全部原始物理与倍率审计通过。 |

第四轮审计先发现三项观察器假设：setup 完成不等同输入接收时刻；PX4 相同 SourceStamp/完整载荷的重复 status 被正确拒绝，不等同任务失败；下一命令在上一窗口结束后受理，其最新 native SourceStamp 可略早于旧窗口末端。审计分别按实际 Task 超时、两份完全相同原始包、明确新受理和已完成窗口判定，并有相反边界测试。没有容许内容冲突、源时间回退、任务撤销或提前切换。第五轮明确计数 AP 6 / PX4 11 条窗口末端源时间交叠，以及 1 条 PX4 跨话题观察交叠；这些包不充作旧窗口目标证据。之后第四轮仍在真实物理门槛处失败。

成功审计 `validation/ap-mixed-20260909/audit-05-01.json` 与 `audit-05-02.json` 两次字节一致，SHA256 为 `4e1f37fb34dfd567458e708ea90d59ebbd04ac5c0a6e570e272bee19d057c1f4`；原始 result SHA256 为 `57360eb85e08a606bc9b54067765216a897e192c38613e06c6e1b5d0081fb998`。审计源码 SHA256 `b36de45e6538db384cc94ef5da185acf9c05cf7a38be6a9e6f08cff74345177a`，复用审计器与 evidence 格式器 SHA 也在输出中。

五轮 50 条原生子进程记录全部收回，当前完整 argv/cwd 无匹配，见 `validation/ap-mixed-20260909/cleanup.json`。原生边界 C++ 切片另有 264,169 断言及全部 131,072 mask/frame 组合检查，实际 DDS/helper 函数体绑定封存源码；AHRS/Location/Guided 依赖为脚本化替身，不代表真实 fence/reset/timeout 已执行。

本切片最终完整矩阵 512 项（483 通过、29 条件跳过），旧预检 11 通过，日志为 `validation/session-product-checks-1ehk17AQ/`。候选任务与审计针对性 18 项已先通过；矩阵包括当前物理准备与审计分类修正，尚未包含仍在实施的原生 timeout runner。

下一步是[原生停流与新接管接缝](2026-09-09-ap-native-timeout-seam.md)，并继续正式候选提升和其他原生边界。当前结果没有修改固定生产 pins，也没有将 #33 或 Full 改为完成。
