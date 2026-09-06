# 获批联合暂停、单步、继续与许可失效接缝

状态：独立候选已完成真实双飞控的健康暂停/单步/继续/降落闭环及许可失效负向验证。**#8/#19/#20/G2/Full 仍未完整验收**。许可失效测试不是 DDS 断连测试；故障后的显式物理恢复/新任务接管、倍率、完整冷重置隔离和正式联合产品入口仍需推进。

## 批准和当前实现

用户分别对暂停/恢复语义和墙钟监督数值给出明确批准，完整[批准记录](2026-09-06_joint-wall-supervision-accepted.md)已更新并通过 gh 发布至 #8。没有把一次数值回答推导为其他授权，没有改写或关闭 Wayfinder 父图。

结果已同步到[#20](https://github.com/unununnnn/wksim/issues/20#issuecomment-5557918572)和[#19](https://github.com/unununnnn/wksim/issues/19#issuecomment-5557921774)；批准记录、评论正文、OPEN状态及原生阻塞关系均已[读回核验](../validation/approved-scene-lifecycle-integration-20260906/publication.json)。

- 唯一权威时间继续采用既有1ms tick/4ms输入屏障。新增[场景许可](../ros2/src/prometheus_control/prometheus_control/scene.py)，通过原有标准ROS消息承载显式run/scene epoch、顺序、请求身份、phase、tick、time_ns和单调墙钟有效期；100ms发布、500ms失效。旧代次/旧顺序不更新许可，失效后新心跳不自动恢复控制。
- [ControlNode](../ros2/src/prometheus_control/prometheus_control/node.py)仅在显式scene_epoch/use_sim_time候选下接入许可。只有已经接管且无待完成原生操作、原生状态/健康有效、飞控模式和DDS连接可用时，才绑定冻结快照。保留原状态源时间，继续当前目标的必要原生保活；没有新解锁、起飞或模式请求。
- 暂停许可持续有效时，两个原生适配器区分“获准冻结的源状态”和真实不新鲜数据。原生状态/身份/健康/重置检查仍执行，Controller绑定实际原生状态DDS发布者GID并持续核对；观察器对命令话题的订阅不能单独证明FC连接。
- [Task](../Simulator/wksim_runtime/task.py)在暂停/单步/恢复阶段持续ROS接收和墙钟监督，阻止新的高层动作。任务使用原始共享ROS时间，没有补偿偏移或第二套任务时钟；单步四tick真实对应4ms。继续时要有冻结时刻之后的新原生状态，且原控制epoch/native generation不变。
- [候选运行器](../tools/joint_lifecycle.py)通过场景请求执行暂停、单步和继续；真正的飞行命令始终来自原有公共Task→安装Control链路。正式UI未因此验收，当前入口是显式候选CLI及已有实验配置/六条公共任务。

默认生产准入和旧安装保留；新候选须显式提供构建清单及SHA。没有改两飞控、消息overlay、健康参数、RC或原厂安装。

## 最终健康流程

最终候选 `eoKlcE`，实验 `joint-public-flight-jk0_zjq9`，[完整原始审计](../validation/joint-public-flight-jk0_zjq9/lifecycle-audit.json)：

| 动作 | 权威tick | 实测 |
|---|---:|---|
| 第一段空中物理暂停 | 51436 → 51436 | 4.00199墙钟秒，两个真实模型完整快照不变，双Control确认有效 |
| 一次单步 | 51436 → 51440 | 恰好四个1ms模型步，完成共同输入屏障后自动保持暂停 |
| 第二段空中物理暂停 | 51440 → 51440 | 4.00271墙钟秒，快照不变，保活/许可继续 |
| 显式继续并确认新原生状态 | 51440 → 51940 | 两控制节点分别确认源时间严格晚于冻结边界，再释放Task执行 |
| 完成原公共任务并停止 | 最终69072 | 两机各六条公共输入、正常降落、模型/FC/Task/Control全部退出0 |

同tick两机均高于1m共 **13.919仿真秒**。独立模型的AP/PX4航点驻留最大位置误差 **0.19051/0.46359m**，继续使用原0.5m任务门槛，不是G6动力学等价预算。暂停总计约8墙钟秒没有消耗对应物理时间；单步的4ms仍计入共享仿真时间。

唯一时钟共发布69153次，其中69073个逐tick时间（含0）和80次相同已提交暂停时间重发，分别审计计数。没有事后调整任何原始时间戳。Task日志均实际看到 `running → paused → stepping → paused → resuming → running`，悬停期间没有新高层请求；公共命令序列与未暂停任务相同。

两个Task实际导入的共享许可模块均为 `/root/wksim-joint-control-eoKlcE/install/prometheus_control/local/lib/python3.10/dist-packages/prometheus_control/scene.py`，SHA256 `aaf434709226e65cbcf349ca7a2bfbacfc976cb339e0baacbcb66f59b7d63840`；运行前核对、结果和离线审计三处记录。Control也由实际安装路径验证器启动。

## 许可失效负向场景

`joint-public-flight-8a572x9j` 使用同一eoKlcE控制候选；[许可失效原始审计](../validation/joint-public-flight-8a572x9j/permission-loss-audit.json)及[后续独立复核](../validation/approved-scene-lifecycle-integration-20260906/permission-loss-audit.json)均通过。

两架真实机在tick51756、真实高度2.961/2.799m，先正常冻结4秒并获得双控制确认，随后只停止场景许可发布1.2秒。FC、Agent、Control和模型仍是真实存活进程。AP/PX4分别在开始停止发布后0.466/0.471秒，以 `scene_permission_expired_no_automatic_recovery` 撤销控制；最后一次许可发出早于停止动作，不能把这两个接收延迟直接解释为许可配置值。

两Task自行报告许可失效并退出1，没有被测试器提前杀死来冒充故障响应。重新发布新许可并观察0.7秒后，两个控制节点仍拒绝自动恢复，未出现新高层任务请求。模型全状态和tick保持不变，停止也没有新增物理步；模型、FC和Control最终正常退出0。

这验证了许可期限和“不因心跳恢复就抢回控制”。它**没有**断开DDS Agent或网络，没有证明暂停中所有网络失联均能及时检出，也没有完成故障后的显式恢复/新任务流程。不能代替#22空中DDS失联或G2完整故障验收。

## 构建、失败与回归

最终控制候选 `/root/wksim-joint-control-eoKlcE`，构建清单SHA256 `2100e8bf66a4730335ecd84e0cf6bc7cdd0cef26f9de085b26e536c4749e833c`。AP仍用OXQqdR，清单 `f347ba252fbfc33bc92baffba08660f33c3a0e4462e90177ba84bdc11408660a`，固件 `083971caff8883188488b02ec18a8ef17141fe948b520b3c597a6109e8c2d7de`。PX4固定固件仍为 `987f8ca64958e031094178dabad9d6e52e92f8642caefa8e7db406ff528956bd`。

| 阶段 | 记录 | 结果及范围 |
|---|---|---|
| 首次候选An3uOD | `joint-public-flight-dhqng91b` | ROS不允许主题末段以数字开头，tick0拒绝，未启动FC；改为control/uav1/uav2并补真实构造测试 |
| 首次健康流程nfo6Jd | `joint-public-flight-vpwyxmkf` | 两次4s暂停、四tick、继续及完整飞行/审计通过；后续另加强原生发布者GID绑定 |
| 最终候选eoKlcE负向 | `joint-public-flight-8a572x9j` | 许可失效撤销/不自动恢复/零额外步停止通过；飞行明确未完成 |
| 最终候选eoKlcE健康 | `joint-public-flight-jk0_zjq9` | 健康生命周期及公共飞行、实际模块身份、当前源码/原始审计通过 |

- [源接缝矩阵](../validation/scene-lifecycle-checks-1XfrQquo/tests.log)42项，跳过6项，其余通过；包括真实ROS消费者/控制节点/许可、暂停Task、模型时间、身份及新鲜度边界。6项旧条件用例在下一显式候选矩阵中覆盖。
- [最终安装候选矩阵](../validation/joint-control-checks-CxT8hYeS/tests.log)73项全部通过，包含原生接口、Task默认兼容、无效时钟副作用门及真实ROS信号退出。
- [默认产品矩阵](../validation/session-product-checks-rujrn44u/session-tests.log)283项，跳过19项，其余通过；[旧版准入](../validation/session-product-checks-rujrn44u/legacy-preflight-tests.log)10项通过。默认旧安装不存在新scene模块，因此相关测试显式跳过，未计为通过；新模块的真实测试有上列独立证据。
- 保留测试基础设施失败：旧SimpleNamespace用例未提供新增可选scene字段；Humble unittest按名称加载不会处理模块导入期SkipTest；一次命令行环境拼接缺少正确overlay路径。分别修正夹具、改为类级条件跳过及使用固定环境脚本，未降低真实断言。
- [可重复审计](../validation/approved-scene-lifecycle-integration-20260906/final-audits.log)连续两次生成字节一致的最终审计，并重验旧控制候选的历史暂停证据。审计现在明确区分历史封存源码与可选当前工作区比对，派生审计文件不把自己纳入输入哈希。

[进程集成记录](../validation/approved-scene-lifecycle-integration-20260906/integration.json)核对本段30个实验进程组无残留；加上此前空中暂停诊断40组，共70组再次内核核对无残留。原AP PID828/PGID828/start_ticks19268不变。原UE/P450、硬件、厂商资源和混合工作区未被本次操作改写或推送。

## 复现

在WSL Ubuntu-22.04/root的wksim目录，使用封存最终候选：

```bash
bash tools/run-joint-flight.sh \
  --ap-manifest /root/wksim-ap-clock-stop-OXQqdR/wksim-build.json \
  --ap-sha256 f347ba252fbfc33bc92baffba08660f33c3a0e4462e90177ba84bdc11408660a \
  --control-manifest /root/wksim-joint-control-eoKlcE/build.json \
  --control-sha256 2100e8bf66a4730335ecd84e0cf6bc7cdd0cef26f9de085b26e536c4749e833c \
  --scene-lifecycle
```

再加 `--scene-lease-loss` 即为许可失效负向场景；它预期 `status=observed`，不能当完整飞行成功。重新构建用 `bash tools/build-joint-control.sh`，采用该次新清单，不覆盖封存候选。

```bash
bash tools/check-scene-lifecycle-source.sh
bash tools/check-joint-control.sh /root/wksim-joint-control-eoKlcE/build.json \
  2100e8bf66a4730335ecd84e0cf6bc7cdd0cef26f9de085b26e536c4749e833c
bash tools/check-session-product.sh
bash validation/approved-scene-lifecycle-integration-20260906/check-audits.sh
python3 -B validation/approved-scene-lifecycle-integration-20260906/integrate.py
```

每个运行目录包含自己的真实启动命令、预检、构建和版本哈希、原始传感器/执行器、模型请求/状态、公共Task消息、许可CDR、双Control确认、错误和退出状态。

## 保留门槛与协作

首期健康位置任务接缝和许可失效已形成候选证据；以下仍未完成：真实空中DDS断连/端点或网络故障、迟到输入与掉队恢复、故障后显式物理恢复及新任务接管、倍率和性能保证、全部冷重置旧队列隔离、正式联合配置/CLI/UI/UE、环境/出生点/碰撞以及其余Full功能和G6数值预算。场景许可不是远程认证协议，当前只在受保护的同机私有ROS图使用。所有必需项继续归属于原规格/票据/Full账本，Goal未完成。

Hooke子代理只写Task及其专用测试，配置为gpt-6-astra/low，并在编辑前从实际session_meta/turn_context核验；[配置证据](../validation/approved-scene-lifecycle-integration-20260906/agent-config.json)。未嵌套或恢复代理。主代理复核改动，修正单步/恢复源时间、启动发现、代次和旧许可边界，串行占用真实FC资源完成集成。

本段以已知源路径、实际构建与运行SHA为依据。Codebase Memory新scene模块/测试not_tracked，既有Node/适配器/Task为metadata_changed，工具按tools排除；[覆盖记录](../validation/approved-scene-lifecycle-integration-20260906/index-coverage.json)。未进行依赖新改动的结构查询，未为报告重复索引，也未宣称此前完整索引/持久化失败已解决。
