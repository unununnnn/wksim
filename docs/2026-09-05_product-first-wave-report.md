# 首批产品闭环交付报告

2026-09-05：能力预检、正式实验入口、离线回看、单载具UE产品状态流四个切片已实现并经主代理复核。PX4与ArduCopter分别通过真实飞控、原生DDS、Prometheus公开任务和UE5.5显示的完整运行；80项自动化测试通过，无跳过。所有源码与证据仍保存在本机，没有提交或推送混合工作区。**这不是完整CopterSim复刻完成，也不是双机共享时钟验收。**

范围及授权依据：[已批准规格](plan/full-migration-spec.md)、[G0–G6 Goal](plan/goal-objective.md)、[Full扩展账本](plan/full-scope-expansion.md)。本轮没有替用户决定MATLAB操作范围、联合场景掉队/空中失联策略、模型ABI、数值预算或硬件操作。原Wayfinder #1保持未修改；规格#10及38张实施票#11–#48已发布，87条原生阻塞关系逐条读回。四个首批工单已于12:38:59 UTC按completed关闭并读回，见[状态与评论链接](plan/completions/status.json)。

## 本机复现

前提是保留本机已验证的WSL Ubuntu22.04、Humble、飞控和模型构建产物，以及Windows UE5.5.4/VS/Python。未知或已删除的资源会被预检拒绝，不自动替换、下载或重新认定兼容。实际路径和SHA256见[预检文档](wksim-preflight.md)。UE资产复用仅在本机，不表示已经解决发布许可。

PowerShell从仓库根执行以下两条命令，**顺序运行**，不要与其他占用UDP19060的UE实验并行。每次会创建新运行身份和独立证据目录；约束和阈值由版本化验证器固定。

```powershell
Set-Location -LiteralPath 'C:/Users/PC/Documents/odid编译/wksim'
& 'D:/date/miniconda/python.exe' -X utf8 tools/validate_product_visual.py --stack arducopter
& 'D:/date/miniconda/python.exe' -X utf8 tools/validate_product_visual.py --stack px4
```

这里的验证器启动的是正式入口`bash tools/run-wksim.sh CONFIG --output-root DIR`。任务发布者只发送Prometheus公开setup/command；验证器不代发飞控控制。Windows桥从核心Unix数据报取得状态，JSONL仅作为输出证据，不是画面输入。独立运行命令、就绪/停止和错误契约见[正式运行](wksim-runtime.md)；显示协议和手动启动见[状态流](wksim-state-stream.md)。

已保存证据的只读核验与回看：

```powershell
& 'D:/date/miniconda/python.exe' -X utf8 tools/validate_product_evidence.py validation/product-visual-arducopter-dfd_mah6/result.json validation/product-visual-px4-hzennaf8/result.json
& 'D:/date/miniconda/python.exe' -X utf8 -m Simulator.wksim_runtime.replay validation/arducopter-dds-urq9hofr --record prometheus:100
& 'D:/date/miniconda/python.exe' -X utf8 -m Simulator.wksim_runtime.replay validation/px4-dds-epf9gukj --clock fc_boot --from-time 40 --to-time 45
```

核验器会比较当前源码与运行时哈希；后续实现改变源码后拒绝当前源码匹配是正常的，不应改写历史证据使其通过。回看器本身不导入ROS、不创建进程或网络连接，只读输入；新JSON导出必须在输入目录之外且不能覆盖现有文件。

## 四项验收结果

| 工单 | 实现与证据 | 本轮边界 |
| --- | --- | --- |
| [#11 实验能力预检与候选身份核验](https://github.com/unununnnn/wksim/issues/11) | 严格配置、实际固件/模型/消息覆盖层哈希、公开JSON结论；双栈正例及混用AP覆盖层、未飞候选、未知能力等拒绝验证；8项预检测试 | 能力索引87行保留Full义务，仅准入已验证的native_position_mission，不把“已构建”当“已飞” |
| [#12 正式入口启动与停止一次双栈可选实验](https://github.com/unununnnn/wksim/issues/12) | 两栈相同六条公开输入，完成普通解锁、起飞、持续保持、ENU航点、降落；真实就绪门、失败结果、按自有进程组清理；11项运行测试 | 单次独立实验；空中异常退出明确记为失败清理，不冒称安全降落，不擅定失联策略 |
| [#16 已有任务记录的离线回看](https://github.com/unununnnn/wksim/issues/16) | AP20,144条、PX4 21,537条，共41,681条原始样本的字节、逐流顺序和输入哈希一致；2项专属测试 | 跨物理/FC启动/ROS/记录器时钟的映射未知，旧run_id/epoch保留未知；不是确定性重新仿真或GUI |
| [#17 单载具产品状态流接入UE5.5](https://github.com/unununnnn/wksim/issues/17) | 核心非阻塞Unix数据报→WSL只读relay→Windows桥→UE实际Actor回读与截图；双栈真实断流/恢复、非法包拒绝 | 显示独立于物理；几何体为Quad-X接入模型，城市建筑尚不参与碰撞；不宣称联合场景 |

产品任务的六条输入为AUTO.LOITER、普通ARM、COMMAND_CONTROL、ENU `[2,3,3]` yaw0、LAND、落地后AUTO.LOITER。审计核验两栈去除消息header后逐项相同，8个共同运行源文件哈希相同。PX4只读原生VehicleStatus等待当前模式健康就绪；这不是旁路控制或关闭解锁检查。

## 双栈实测与构建身份

| 指标 | ArduCopter | PX4 |
| --- | --- | --- |
| 运行ID | visual-arducopter-70a4c2998a | visual-px4-741c75d702 |
| 结果目录 | [product-visual-arducopter-dfd_mah6](../validation/product-visual-arducopter-dfd_mah6/result.json) | [product-visual-px4-hzennaf8](../validation/product-visual-px4-hzennaf8/result.json) |
| 实际Actor关联回读 | 874 | 369 |
| 最大高度 / 最近航点误差 | 3.002970m / 0.021579m | 3.176730m / 0.061660m |
| 最大Actor位置误差 | 8.3184e-10cm | 3.3321e-5cm |
| 最大四元数L2误差 | 8.2316e-10 | 9.2236e-7 |
| 显示断开墙钟时长 | 3.0142s | 3.0110s |
| 断开期间物理推进 | 46.48→55.60s，增加9.12s | 11.36→20.40s，增加9.04s |
| 非法探针 / 被错误接受ACK | 10 / 0 | 10 / 0 |
| 正常落地、任务退出、子进程回收 | 全部通过 | 全部通过 |

上述航点最近误差只是摘要；通过条件还包括原有驻留/速度/姿态门槛。UE坐标阈值仍为位置2e-4cm、四元数L2 2e-6、时间1e-8s、至少30次回读；断流至少3墙钟秒且物理增加至少1仿真秒。它们不是动力学等价预算，没有因为结果调整数值阈值。

每栈拒绝计数器最后为11，不应说11个都是故意注入的探针：10个定向探针均无接受ACK，累计计数还可能包含自然重复/过期包。检查依据是零错误接受、计数覆盖探针，以及合法当前流可恢复。

最终UE工程为`E:/ue5.5/build/wksim-native-state-v2-clockbound-20260905/WksimVisual.uproject`。DLL SHA256为`8ff466fbd1eb6489b7e8ac29209bbb7885cf7c876ee97dbcc314ebf41dc00b4a`；8个仓库/暂存输入哈希一致，构建exit0，33.60s。MSVC14.51非推荐版本与现有引擎弃用警告未阻止构建。见[构建清单](../Simulator/ue55/state-build-manifest.json)及[原始构建日志](../validation/ue55-build-03234a38/build.log)。

主代理实际查看了两栈LIVE、STALE及恢复截图，而不只核对PNG存在。例：[PX4飞行LIVE](../validation/product-visual-px4-hzennaf8/frames/frame-0004.png)、[断流STALE](../validation/product-visual-px4-hzennaf8/frames/frame-0005.png)、[恢复当前状态](../validation/product-visual-px4-hzennaf8/frames/frame-0006.png)。机体、旋翼及场景可见，但材质/照明与高保真机型资产仍属于后续工作。

## 测试与失败保留

最终测试在WSL仓库根执行：

```bash
source /root/wksim-dds-VxM6Ni/ros-install/setup.bash
source /root/wksim-ap-dds-yaw-state-4Wr27s/ros-install/local_setup.bash
source /root/wksim-ros2-0viK3f/install/local_setup.bash
export WKSIM_PREFLIGHT_LIVE_RESOURCES=1
unshare --net bash -c 'ip link set lo up; ROS_LOCALHOST_ONLY=1 ROS_DOMAIN_ID=78 python3 -m unittest discover -s validation -p test_\*.py'
```

结果为80项通过，无跳过；日志中的注入失败结果和拒绝覆盖输出属于负例预期。Windows另执行2项时钟边界测试。测试日志SHA256为`4639f0418f208b3e6e62bd6283714203edb578e4cc9e139b8c7e78aedc333de1`。

本轮发现并修正，原始失败没有删除：

1. [首次PX4正式任务](../validation/product-runs-20260905/example-px4-001/result.json)：定位有效不等于当前模式允许解锁，飞控返回临时拒绝。修正为只读当前PX4健康状态后发送普通公开解锁，不强制解锁、不固定延时、不重试抢控。
2. [首次Windows产品桥](../validation/product-visual-arducopter-ygso1ykd/result.json)：未bind就recv触发WinError10022。桥绑定自有回环临时端口后接收；UE退出的UDP重置不传播成物理失败。
3. [拒绝计数误判](../validation/product-visual-arducopter-6miil83_/result.json)：10探针零ACK但累计拒绝11。校验改为符合计数器语义，不是放宽物理或坐标门槛。
4. [WSL/Windows墙钟误判](../validation/product-visual-px4-hdzag2_h/result.json)：实际墙钟偏差约1.4s导致新鲜包被旧算法全部判过期。源时间仍保留；WSL先在同一时钟检查源年龄，Windows再加完整单请求往返耗时形成保守年龄上界，UE在Windows同一时钟判断。0.75s新鲜度阈值未放宽，也未修改操作系统时钟或模型时间。
5. 离线回看首次测试夹具将LF转换CRLF；修正为按实际输入字节比较，读取器本就保留原始字节。早期导出保留，最终导出身份见[回看清单](../validation/offline-replay-20260905/result.json)。

两个最终运行都记录`flight=0`、已落地、自有进程全部回收、relay socket删除。UE和桥的退出码1来自验证器有意终止其自有进程，不是飞行失败。最终残留检查没有本轮runtime/relay/control/UE进程；原有ArduCopter PID828保持存活。本轮未改厂商安装、未全局杀进程、未操作真实飞控硬件。

## Evidence → Finding → Path

此处采用普通工程报告模板（flavor=null），不是安全事件报告。Scope见首节已批准规格；不适用IOC、ATT&CK、攻击路径和二进制导入表。

| Evidence | observed_at / source_type | source_ref / artifact_path | content_hash | repro_command / raw_excerpt / linked_workitem / supersedes |
| --- | --- | --- | --- | --- |
| E-001 最终AP产品显示 | 2026-09-05 / file+log | `validation/product-visual-arducopter-dfd_mah6/result.json`（仓库相对） | `e605864feac9d6794dfc80e299f4cf444fe977f9cb7bd00fed7c72f2e8d1105d` | 首节双栈审计命令；`status=pass, readbacks=874`；#12/#17；替代本节列出的早期AP接入失败结论，不删除历史 |
| E-002 最终PX4产品显示 | 2026-09-05 / file+log | `validation/product-visual-px4-hzennaf8/result.json`（仓库相对） | `9dae1a320ba08b625234c1bddb657bd3c6213e2d3b61256ab747a6fa7193dd66` | 首节双栈审计命令；`status=pass, readbacks=369`；#12/#17；替代早期时钟误判结论，不删除历史 |
| E-003 自动化回归 | 2026-09-05 / log | `validation/product-checks-xqOpGdMO/unit-tests.log`（仓库相对） | `4639f0418f208b3e6e62bd6283714203edb578e4cc9e139b8c7e78aedc333de1` | 上节WSL测试命令；`Ran 80 tests / OK`；#11/#12/#16/#17；supersedes=none |
| E-004 AP离线输出 | 2026-09-05 / file | `work/offline-ap-20260905-final.json`（仓库相对） | `0f05abc805f3ea81e2c1ac73a46bd252d2bf24570acdbfcec566d7be743af668` | 实际命令`python -m Simulator.wksim_runtime.replay validation/arducopter-dds-urq9hofr --output work/offline-ap-20260905-final.json`；20,144条原始行；#16；supersedes=none |
| E-005 PX4离线输出 | 2026-09-05 / file | `work/offline-px4-20260905-final.json`（仓库相对） | `d0f443e4416ebf659b4fb544c9128b67217766bd6a647518be305d9bccb62b42` | 实际命令`python -m Simulator.wksim_runtime.replay validation/px4-dds-epf9gukj --output work/offline-px4-20260905-final.json`；21,537条原始行；#16；supersedes=none |

E-004/E-005导出已经存在，重跑上述命令会按设计拒绝覆盖；复现导出时选一个新输出文件名，或用首节不带output的只读查看命令。`--record`只查看单条样本，不与导出选项混用。

F-001：独立产品任务和异步显示闭环成立。severity=info，category=other，status=validated，evidence_ids=[E-001,E-002,E-003]，confidence=high。location为上述真实运行及其源码哈希清单；impact限定为单载具双栈分别运行。复现按首节真实运行后审计；后续行动是#13独立并发隔离和#14控制重启旧命令隔离。optional_attack不适用。

F-002：旧记录可只读保真回看。severity=info，category=other，status=validated，evidence_ids=[E-003,E-004,E-005]，confidence=high。location为回看器及双栈输出；impact是保持已有样本/顺序和显式未知时基，不证明未记录内容。复现按首节回看；确定性重新仿真另见#46。optional_attack不适用。

P-001，path_type=callflow：从已验证配置到独立任务、异步画面和离线证据。步骤为预检/正式启动（E-001/E-002/E-003，F-001）→公开任务/真实飞控/自主物理（E-001/E-002，F-001）→核心数据报/只读桥/UEActor（E-001/E-002，F-001）→落地清理及已有记录回看（E-003/E-004/E-005，F-002）。残余风险是临时构建路径、单机单时基实验范围、画面资产/碰撞未完成，以及下面的未决Full义务。

## 继续执行的位置

下一可执行前沿为[#13 两个独立实验同时运行且互不干扰](https://github.com/unununnnn/wksim/issues/13)与[#14 控制节点重启后的旧命令隔离](https://github.com/unununnnn/wksim/issues/14)。两者不会偷换为共享场景；#19联合权威时间还受#8决策约束。MATLAB#5、首期/数值#6、联合调度#8、插件/环境#9继续保持开放。

本轮三个实施子代理均由主代理显式选择并从实际turn_context核验为gpt-6-astra/low，写入范围互斥；主代理承担回看、集成修复、实飞及证据复核。明细见[机器清单](../validation/product-first-wave-20260905/manifest.json)。Codebase Memory已刷新并定位新入口，最新52,918节点/156,535边；metadata_changed提示仍如实保留，详见[索引记录](codebase-memory.md)，图规模不等于迁移覆盖率。

文档自检：结论/命令/身份/负例/截图/下一步均有来源；没有用成功演示替代Full验收。to-spec/to-tickets使批准粒度和原生阻塞关系保持可执行；ponytail使回看和本地显示桥沿用标准库及现有构建，不新增大型框架；docs-generator按分层结构组织证据。其ce:writer和包内tool-index.md在本机缺失，本报告不需要额外工具，使用已实际运行的路径与命令完成，不因此中断工程。
