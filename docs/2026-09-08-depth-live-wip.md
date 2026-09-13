# 正式 View 深度接入 WIP（2026-09-08）

本切片只接入一个可选 160×120 深度相机，不表示 #31 完整验收。复用正式 View 和公共双飞控任务驱动；没有修改 UE C++、runtime、控制源码或既有验证工具。

- `Simulator/wksim_console/visual.py`：新增可选 `depth_config`，验证真实联合权威 instance，独立 `depth_stream_id`、输出目录和通知端口，写入配置并传给原生 `-WksimDepthConfig=`。默认/RGB 参数不变，同时配置两者时拒绝共用通知端口。
- `tools/validate_joint_depth.py`：复用 RGB 验证的准备/正式公共任务/有主进程停机/WSL 证据保留流程，使用生产 Depth Reader。相机固定 vehicle 2、front_depth、160×120、90°、安装 [30,0,50] cm、100m 截断、19073 UDP、每 100 个权威 step 采样。绑定状态中的 epoch/generation，重连绑定当前 minimum_step。双机真实离地 2.5m 后断开消费者 3 秒，要求物理前进至少 1000 tick，再接收至少 5 个新帧，完成公共任务、落地解除武装后正常 stop。
- 完成后自动生成 `depth-audit.json`：逐帧重新解析原始 f32/metadata，匹配原始两侧 truth 和已提交 clock，验证实际相机安装姿态、单位、时间、单调身份和 ENU 米点云/uint8 掩码保存一致性；要求至少 15 帧及 5 帧双机同时离地。位置误差 ≤2e-4 cm、四元数 L2 ≤2e-6、模型时间误差 ≤1e-8 秒沿用 UE 传输预算，不是动力学预算。原始深度距离精度仍由已执行的独立光学固定件证明。

## 主代理串行执行

前提：当前无真实运行占用 UE/双飞控资源；Ubuntu-22.04 项目运行依赖已准备；19060 与 19073 空闲；下列候选 manifest 的 DLL/源码哈希仍吻合。Python View/工具修改不需要重建 UE。必须选一个不存在的新输出目录。

在 `C:/Users/PC/Documents/odid编译/wksim`：

```powershell
python tools/validate_joint_depth.py --manifest validation/ue55-build-d47f784219a9490b8e413363dc95bbbd/candidate-manifest.json --output validation/depth-live-20260908-run1
```

退出码 0 要求真实任务和深度审计均通过；原始运行结果保留在 `report.json`，独立审计状态在 `depth-audit.json`。审计失败不会改写原始运行报告。可不启动任何真实资源重做审计：

```powershell
python tools/validate_joint_depth.py --output validation/depth-live-20260908-run1 --audit-only
```

## 本次实际验证

本子代理没有执行真实 UE、飞控或构建。已通过 Python 编译检查、CLI `--help`，以及 `python -m unittest discover -s wksim/validation -p test_depth_slice.py -v` 的 2 项既有离线测试。额外无 socket/无进程的 View 构造检查通过：默认深度关闭、深度独立身份/目录、配置深拷贝、缺联合权威拒绝、RGB/深度同端口拒绝。

模型核验：`C:/Users/PC/.codex/sessions/2026/09/08/rollout-2026-09-08T14-24-58-01a07f7a-072a-7782-bca1-ba01c933374e.jsonl` 的 turn_context ordinal 7：model=gpt-6-astra，effort=low；没有嵌套委派。

尚未覆盖深度生产者关闭/重启、冷重启代次、多传感器、required 失败策略或全部 #31 条件。View 仍保留现有仅回收创建的 Popen handle、UE wrapper 后代/WSL relay 回收未验证的显式限制，不升级其所有权声明。真实运行结果由主代理补证。

主代理 2026-09-08 实跑调整（下一次运行之前记录）：run1 在启动物理前因子 PowerShell 的 Get-FileHash 不可用拒绝，已由实际模块枚举路径 + Python SHA256 替换等价核验；run2 已消费386帧但真实权威时钟在51904步触发既定 rate_unmet/resource_insufficient，按失败留存并正常清理。首期单相机保持160×120，采样间隔由100步收窄为500步（物理2Hz，0.5×墙钟约1Hz），减轻GPU读回/点云写盘负载；所有字段记录该配置。1ms权威步、4ms输入边界、0.5×监督和100ms门槛、光学误差预算均未改变；不是降低G6数值要求。后续高频率和更多传感器仍属Full范围。

下一次运行前追加：500步采样的run3在80144步因同一100ms倍率监督失败，消费130帧且保留故障/清理。验证驻留由hold12/waypoint8缩为hold8/waypoint4，仍完成同一六条公共输入、空中断开3墙钟秒及重连至少5新帧/正常降落。此项减少验证负载持续时间，不改变产品默认、控制误差预算或倍率门槛；完整长时间运行义务保留。

最终进展：run5正式公共飞行/降落、123帧（19真实双离地帧）、消费者断开1508tick物理前进、重连新帧及重复原始审计通过。完整失败和边界见[最终报告](2026-09-08-depth-live-report.md)，#31仍待生产者重启/冷重置/完整故障策略。
