# 控制包提升与受控 GCS 双栈闭环（2026-09-08）

本轮落实用户明确答复“批准 A：显式提升飞行机制（推荐）”。完成显式提升、真实双栈公共任务、原始审计、两层证据换绑和默认预检恢复。#32 的完整速度任务收尾与 #42 的用户界面控制交接仍开放，Full 不完成。

## 真实 GCS 与正式独立飞行

受控 WksimGCS 5.1.4.0，Qt6.11.1，本机自建 exe SHA256 `134b9b6db4dec56d00707e406e5f8ff20ded25cfba8f5579e2447f1acbd6ace7`。私有 INI 六种 AutoConnect 均关闭，仅保存 UDP14560→127.0.0.1:14570；启动前探测两个端口独占并拒绝现有 QGC。未修改厂商安装、未触碰既有 MissionPlanner/硬件。QGC 日志真实识别 PX4 `22/1/12/2`、ArduCopter `241/1/3/2`。

| 场景 | 正向原始包 | 反向成功包 | 停桥时/最终物理时间(s) | 结果 |
| --- | --- | --- | --- | --- |
| live-px4-run4 | 4248 | 17 | 12.86 → 42.04 | 正式三航点、正常落地、退场通过 |
| live-arducopter-run2 | 3974 | 136 | 45.32 → 75.04 | 正式三航点、正常落地、退场通过 |

正向每包SHA256与 Observer 真实发送成功时记录的原包摘要匹配；摘要集合有8192上限，达到上限不伪称完整审计。反向仅按 relay 真正成功提交的报文计数，以 `4字节大端长度+原始数据` 累积SHA256，与 Observer 真正发到已钉 FC 对端的计数和摘要完全一致：PX4 `c2efd0f29d9e136fa48f6fa93be7471acf079e24f0288d19641b6e75c16c24b9`，AP `bf4cca3017c6fefbe31587d72c281a4c7f8e85d91b1d5aef8c41339082a7ce7a`。没有构造心跳/原生命令替代QGC。

两场均在真实空中停止桥，随后物理与公共任务继续运行约29秒；QGC退出不清理其他应用。桥/WSL wrapper/validator/relay 按实际 PID/start_ticks 检查无残留，正式运行自有进程组也清空。QGC由自有Popen退场（Windows exit1是本驱动终止GUI句柄的结果，不冒称GUI自然正常退出）。未执行用户专属的QGC切模式点击，不关闭#42。

## 桥修复与失败样本

接续本轮开始时未提交的桥草稿；原稿和diff保存在 validation/gcs-bridge-20260908/。修复写管道的无尽循环、仅留末包丢失异类MAVLink消息、退出归属、身份污染和停顿后旧UDP包重新打时间戳等缺陷。每次只有一个请求在途，最多64包批次、8192字节/包；返回通道 connect 到本次 Observer 的UNIX套接字实例，路径移除/替换即退出，不连接新运行。混合身份/CRC/尾部垃圾不钉定或转发；长于0.5秒的Windows桥事务终止整桥并关闭UDP队列。WSL侧以同一进程 monotonic 的上一响应租期约束下一次返回，不将Windows/WSL的UTC偏差当作共同时间。此0.5秒是可选GCS传输边界，不是物理或G6数值预算。

6次驱动尝试全部保留：

1. PX4 run1：临时目录未含 run_id，正式配置校验拒绝，未伪装启动成功。
2. PX4 run2：正式飞行/停桥后物理继续通过；独立诊断接收器丢包导致旧正向审计不完整，整体fail。
3. PX4 run3：旧跨UTC年龄判定未交付返回包，飞行已落地而桥仍等待；返回改用本地monotonic租期，严格拒绝/无重放策略保留。完整机体任务结果与驱动中断分别记录，不只挑pass字段。
4. PX4 run4：完整联测pass。
5. AP run1：共享文件短暂PermissionError导致驱动失败并中断当场任务，保留failed/无安全落地结果。驱动对原子替换/读取增加有界重试，并新增完整traceback留存。
6. AP run2：完整联测pass。

工具只显式 `--promotion-flight` 才生成提升配置；默认后续GCS验证使用已准入正式配置。历史真实config和结果中的提升标志保留审计，未伪造为默认准入飞行。两场实际执行的驱动源码已按 preflight.driver_sha256 重建并核验封存为 validate_contained_gcs.executed.py；没有用后续修正的驱动冒充旧执行版本。

## 提升的两层证据

- 独立正式实验：上述两场 `formal/` 通过 tools/audit_independent_profile.py 的原始公共请求、三航点实际窗口、物理真值、进程命名空间/映射和当前固件/模型检查，再封存实际源码并重复审计。独立当前核心映射无 libgz/libgazebo/libmatlab/CopterSim 运行依赖。目录在 validation/promotion-flight-20260908/independent-candidate/。
- 旧 session_v1 回归：PX4 `validation/px4-dds-hfn4vx09/result.json`、AP `validation/arducopter-dds-fnyy23wr/result.json` 均真实6个公开输入通过；旧固定参考分支仅作回归，不把其旧固件当成已去Gazebo的当前独立候选。重建时发现PX4路径已由 /opt/aerotwinsim 迁到 /root/wksim-dependencies（字节/提交相同）；准入仅复用已经批准的 resource_locations 映射，SHA256、提交、模型、Agent检查不变，不改历史baselines。目录在 session-candidate-v2/。
- 发现 MUlZd0 的已安装控制Python已为FVMjak，而其 src 仍旧；先逐文件核验当前仓库源、FVMjak清单与已安装字节相同，再备份并同步4个源文件，安装内容不变。备份 `/root/wksim-promotion-source-yp_p9e1y`，记录 source-sync.json。
- 两份默认catalog已换绑，capability-index只改变session证据链接和摘要，baselines/resource_locations逐对象确认未变。未使用的提升启动配置已移除标志，正式examples从未添加标志。双栈默认预检最终 ok=true，并明确当前准入代码自身不是历史实飞证明。

命令：

```powershell
# 两场真实运行发生在默认仍未准入时；当前驱动重现提升要显式加 --promotion-flight。
python -X utf8 -B tools/validate_contained_gcs.py --stack px4 --execute --promotion-flight --output <新证据目录>
python -X utf8 -B tools/validate_contained_gcs.py --stack arducopter --execute --promotion-flight --output <新证据目录>
```

```bash
WKSIM_CONTROL_PROTOCOL=session_v1 bash tools/run-prometheus-validation.sh px4 /root/wksim-dds-VxM6Ni /root/wksim-ros2-MUlZd0
WKSIM_CONTROL_PROTOCOL=session_v1 bash tools/run-prometheus-validation.sh arducopter /root/wksim-dds-VxM6Ni /root/wksim-ros2-MUlZd0 /root/wksim-ap-dds-yaw-state-4Wr27s
python3 -B tools/rebuild_promotion_evidence.py --independent validation/gcs-bridge-20260908/live-px4-run4/formal validation/gcs-bridge-20260908/live-arducopter-run2/formal --output <新validation目录>
python3 -B tools/rebuild_promotion_evidence.py --session validation/px4-dds-hfn4vx09/result.json validation/arducopter-dds-fnyy23wr/result.json --output <新validation目录>
bash tools/check-session-product.sh
```

## 回归与剩余边界

最终矩阵 validation/session-product-checks-ytrgHwwl：422项（393通过/29按既有条件跳过），旧预检11/11；Windows工作台96/96，视觉+深度+断流18/18。19项遥测、4项真实管道/套接字和5项提升专属检查全部通过（与总矩阵有重叠，不相加冒充功能数）。首轮矩阵3失败分别为旧测试固定引用历史独立目录、以及两栈源目录未同步；原日志 wfveX5AX 保留。测试仍检查当前目录的原始真值/包络/映射，并保留旧证据篡改反例。两次错误环境的默认读回分别被 ROS_DISTRO 和混合overlay拒绝，修正调用环境后 final读回双true，没有放宽准入。

7个子代理均显式选择并实读 turn_context 验证 gpt-6-astra/low，无嵌套；主代理维护写入/实跑资源并完成全部真实试飞、审计、修复和集成。Codebase Memory只用于已需结构导航的先前快照；之后按已知文件直读，不声称旧图覆盖新增源码。真实测试串行，没有改健康检查、RC、物理节拍或100ms/1×/G6门槛。#6和#21已按独立依据关闭；#20/#31/#32/#42/G2/G6/Full尚有义务。
