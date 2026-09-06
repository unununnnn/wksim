# 需求到票据的覆盖核对

2026-09-05。核对对象是当前待审阅规格与38张票据，不是产品验收。48项用户故事均有实施票据、Full扩展项或永久执行规则归属；38张票都被故事引用。**这些是规划归属检查，不表示功能已经实现，也不表示38张票足以完成整个Full目标。**

[规格](full-migration-spec.md)保留完整故事正文，下表按其编号映射。票据数字只属于本地草案，不是GitHub编号。

## 逐项归属

| 故事 | 当前票据归属 | 尚须保留的范围/条件 | 能证明完成的外部行为或证据 |
| --- | --- | --- | --- |
| 1 | [实验能力预检与候选身份核验](tickets/01-capability-preflight.md)、[Prometheus PID控制器选择与闭环](tickets/25-pid-controller.md)、[Prometheus UDE控制器闭环](tickets/26-ude-controller.md)、[Prometheus NE控制器闭环](tickets/27-ne-controller.md)、[单机规划绕障到真实飞行](tickets/29-planner-flight.md)、[真实相机驱动ArUco目标跟踪](tickets/30-visual-tracking.md) | 全部迁移与来源不变量 | 固定Prometheus来源、差异记录与实际运行组件身份；代表算法不能代验全部迁移。 |
| 2 | [正式入口启动与停止一次双栈可选实验](tickets/02-single-run-launch.md)、[单机多航点任务与取消闭环](tickets/05-mission-waypoints.md)、[首期SITL产品流程集成验收](tickets/38-sitl-product-acceptance.md) | 此故事范围由所列票据承担；仍未实施 | 同一任务配置分别执行真实PX4与ArduCopter。 |
| 3 | [实验能力预检与候选身份核验](tickets/01-capability-preflight.md)、[两个独立实验同时运行且互不干扰](tickets/03-isolated-runs.md) | 完整网络/配置组合 | 混用固件/schema、冲突端口和缺资源在启动前拒绝。 |
| 4 | [正式入口启动与停止一次双栈可选实验](tickets/02-single-run-launch.md)、[控制节点重启后的旧命令隔离](tickets/04-run-epoch.md)、[wksim界面配置到任务结果的完整流程](tickets/08-wksim-run-workflow.md) | 此故事范围由所列票据承担；仍未实施 | 用户可分辨模型、FC、Agent、定位与接管就绪阶段。 |
| 5 | [正式入口启动与停止一次双栈可选实验](tickets/02-single-run-launch.md)、[单机多航点任务与取消闭环](tickets/05-mission-waypoints.md)、[首期SITL产品流程集成验收](tickets/38-sitl-product-acceptance.md) | 其他任务/模式 | 公开入口到真值完成；不能靠观察器代发。 |
| 6 | [实验能力预检与候选身份核验](tickets/01-capability-preflight.md)、[双栈速度与偏航控制能力](tickets/22-velocity-yaw.md)、[双栈混合轴与轨迹跟随](tickets/23-mixed-trajectory.md)、[双栈姿态与推力出口](tickets/24-attitude-thrust.md)、[Prometheus PID控制器选择与闭环](tickets/25-pid-controller.md)、[Prometheus UDE控制器闭环](tickets/26-ude-controller.md)、[Prometheus NE控制器闭环](tickets/27-ne-controller.md)、[RC位置控制与任务显式交接](tickets/28-rc-handoff.md)、[双栈全球航点与home基准](tickets/37-global-waypoints.md) | 全控制与协议能力矩阵 | 不支持组合拒绝且无控制副作用，不能由字段存在推断能力。 |
| 7 | [控制节点重启后的旧命令隔离](tickets/04-run-epoch.md)、[单机多航点任务与取消闭环](tickets/05-mission-waypoints.md)、[首期SITL产品流程集成验收](tickets/38-sitl-product-acceptance.md) | 此故事范围由所列票据承担；仍未实施 | 受理、原生ACK、接管、驻留完成各有独立事件和证据。 |
| 8 | [实验能力预检与候选身份核验](tickets/01-capability-preflight.md)、[控制节点重启后的旧命令隔离](tickets/04-run-epoch.md)、[MATLAB TCP/JSON可选桥闭环](tickets/31-matlab-bridge.md) | 跨入口命令身份 | 旧运行、旧序号、过期及错载具报文拒绝；桥同样遵守。 |
| 9 | [联合场景暂停单步与冷重置](tickets/10-joint-step-reset.md)、[固定输入实验的确定性重新运行](tickets/36-deterministic-reexecution.md) | 其他仿真模式时间语义 | 真实物理暂停/单步/继续/倍速，不依赖渲染时钟。 |
| 10 | [双飞控联合场景最小权威时间闭环](tickets/09-joint-clock.md)、[联合场景暂停单步与冷重置](tickets/10-joint-step-reset.md)、[联合场景双载具显示与切换观察](tickets/11-ue-joint-scene.md) | SIL集群与分布式 | 同一权威时间、代次和物理环境；首批仅双机。 |
| 11 | [两个独立实验同时运行且互不干扰](tickets/03-isolated-runs.md)、[首期SITL产品流程集成验收](tickets/38-sitl-product-acceptance.md) | 此故事范围由所列票据承担；仍未实施 | 界面/日志明确区分独立实验与联合场景。 |
| 12 | [实验能力预检与候选身份核验](tickets/01-capability-preflight.md)、[两个独立实验同时运行且互不干扰](tickets/03-isolated-runs.md)、[双飞控联合场景最小权威时间闭环](tickets/09-joint-clock.md) | 分布式和更大规模 | 资源冲突与身份隔离；现有双实例不是任意规模承诺。 |
| 13 | [悬停期间DDS断连与显式恢复](tickets/12-airborne-dds-loss.md) | 其他断链/退出故障 | 悬停Agent断流按批准策略真实验证；地面重连不足以证明。 |
| 14 | [控制节点重启后的旧命令隔离](tickets/04-run-epoch.md)、[悬停期间DDS断连与显式恢复](tickets/12-airborne-dds-loss.md)、[RC位置控制与任务显式交接](tickets/28-rc-handoff.md)、[地面站查看与显式控制权交接](tickets/32-qgc-handoff.md)、[仿真参数操作与飞控重启恢复](tickets/33-parameters-reboot.md) | 其他控制权入口 | 外部切模式、失联、重置后不自动重获控制。 |
| 15 | [正式入口启动与停止一次双栈可选实验](tickets/02-single-run-launch.md)、[两个独立实验同时运行且互不干扰](tickets/03-isolated-runs.md)、[首期SITL产品流程集成验收](tickets/38-sitl-product-acceptance.md) | 硬件模式停止契约 | 失败和正常停止仅收尾本次创建资源；空中动作另经批准。 |
| 16 | [单载具产品状态流接入UE5.5](tickets/07-ue-product-stream.md)、[联合场景双载具显示与切换观察](tickets/11-ue-joint-scene.md)、[六旋翼从参数配置到双栈运行](tickets/15-hex-model-workflow.md) | 全部机型与资产 | 真实来源到Actor回读与正确旋翼表达，不能仅看截图。 |
| 17 | [单载具产品状态流接入UE5.5](tickets/07-ue-product-stream.md)、[联合场景双载具显示与切换观察](tickets/11-ue-joint-scene.md) | 此故事范围由所列票据承担；仍未实施 | 逐载具陈旧/恢复与旧代次拒绝。 |
| 18 | [正式入口启动与停止一次双栈可选实验](tickets/02-single-run-launch.md)、[单载具产品状态流接入UE5.5](tickets/07-ue-product-stream.md)、[首期SITL产品流程集成验收](tickets/38-sitl-product-acceptance.md) | 环境反馈异常契约 | UE退出不终止物理；环境反馈按独立契约处理，不偷删耦合。 |
| 19 | [单载具产品状态流接入UE5.5](tickets/07-ue-product-stream.md)、[四旋翼参数保存导入与真实运行](tickets/14-quad-model-config.md)、[六旋翼从参数配置到双栈运行](tickets/15-hex-model-workflow.md)、[坡面与障碍场景的物理反馈](tickets/19-terrain-collision.md)、[双栈全球航点与home基准](tickets/37-global-waypoints.md) | XML/ClassID与资产导入 | 坐标、尺度、home/原点和构型能通过数值与场景检查。 |
| 20 | [坡面与障碍场景的物理反馈](tickets/19-terrain-collision.md) | 动态环境与其他场景 | 接触/地形反馈有效时间和过期行为可观察。 |
| 21 | [带时间与标定的真实RGB相机](tickets/20-rgb-sensor.md)、[深度相机与由深度生成的点云](tickets/21-depth-cloud.md)、[单机规划绕障到真实飞行](tickets/29-planner-flight.md)、[真实相机驱动ArUco目标跟踪](tickets/30-visual-tracking.md) | 其余传感器及规划感知 | 真实采样身份、时间和内外参与消费者闭环；深度点云不等于全部LiDAR。 |
| 22 | [wksim界面配置到任务结果的完整流程](tickets/08-wksim-run-workflow.md)、[四旋翼参数保存导入与真实运行](tickets/14-quad-model-config.md)、[首期SITL产品流程集成验收](tickets/38-sitl-product-acceptance.md) | 完整GUI/数据库/模式操作 | 首期操作链只是Full子集，剩余16参数及模型工具另行闭合。 |
| 23 | [正式入口启动与停止一次双栈可选实验](tickets/02-single-run-launch.md)、[两个独立实验同时运行且互不干扰](tickets/03-isolated-runs.md)、[首期SITL产品流程集成验收](tickets/38-sitl-product-acceptance.md) | 完整CLI/NoUI参数映射 | 同一配置可无界面执行；其余参数组合仍需独立测试。 |
| 24 | [实验能力预检与候选身份核验](tickets/01-capability-preflight.md)、[四旋翼固定工况数值对照](tickets/13-quad-numerical-baseline.md)、[四旋翼参数保存导入与真实运行](tickets/14-quad-model-config.md)、[生成模型构建导入与无MATLAB运行](tickets/16-generated-model-import.md) | 资源自主交付 | 构建来源与模型I/O核验；厂商ZIP可本机编译不等于可分发。 |
| 25 | [四旋翼固定工况数值对照](tickets/13-quad-numerical-baseline.md)、[四旋翼参数保存导入与真实运行](tickets/14-quad-model-config.md)、[六旋翼从参数配置到双栈运行](tickets/15-hex-model-workflow.md) | 全部参数/组件库 | 保存/导入后参数一致且真实动力学响应符合固定预算。 |
| 26 | [四旋翼参数保存导入与真实运行](tickets/14-quad-model-config.md)、[六旋翼从参数配置到双栈运行](tickets/15-hex-model-workflow.md) | 其余多旋翼/固定翼/复合翼/车辆/模型模板 | 每种构型单独映射，不将六旋翼票提升为全机型。 |
| 27 | [可选旧ABI模型DLL生命周期闭环](tickets/17-legacy-dll-host.md)、[可选新ABI模型DLL与扩展输出](tickets/18-modern-dll-host.md) | 其他DLL样本与扩展ABI | 旧/新ABI分别以真实生命周期和输入输出对照验证。 |
| 28 | [联合场景暂停单步与冷重置](tickets/10-joint-step-reset.md)、[生成模型构建导入与无MATLAB运行](tickets/16-generated-model-import.md)、[可选旧ABI模型DLL生命周期闭环](tickets/17-legacy-dll-host.md)、[可选新ABI模型DLL与扩展输出](tickets/18-modern-dll-host.md)、[单电机效率故障的可复现实验](tickets/34-motor-fault.md) | 全部模型I/O与故障 | 初始化、重置、步进、终止、故障均有可观测结果。 |
| 29 | [可选旧ABI模型DLL生命周期闭环](tickets/17-legacy-dll-host.md)、[可选新ABI模型DLL与扩展输出](tickets/18-modern-dll-host.md) | 其他宿主故障路径 | 宿主失败只影响所属可选运行，不破坏原厂或其他实验。 |
| 30 | [生成模型构建导入与无MATLAB运行](tickets/16-generated-model-import.md) | 最小/最大模板及其他生成路径 | 真实生成来源链及关闭MATLAB后的独立运行。 |
| 31 | [MATLAB TCP/JSON可选桥闭环](tickets/31-matlab-bridge.md) | 此故事范围由所列票据承担；仍未实施 | 实际MATLAB基础TCP/JSON联测，不由其他客户端替代。 |
| 32 | [MATLAB TCP/JSON可选桥闭环](tickets/31-matlab-bridge.md) | 既有MATLAB功能范围决策 | 操作白名单和错误行为须等待明确答复；传输确认不是操作批准。 |
| 33 | [控制节点重启后的旧命令隔离](tickets/04-run-epoch.md)、[MATLAB TCP/JSON可选桥闭环](tickets/31-matlab-bridge.md) | 此故事范围由所列票据承担；仍未实施 | 断开不影响主系统，写请求经能力/身份/时效校验，不自动重放。 |
| 34 | [地面站查看与显式控制权交接](tickets/32-qgc-handoff.md)、[仿真参数操作与飞控重启恢复](tickets/33-parameters-reboot.md) | Mavlink_Full等完整地面站/SDK模式 | 真实查看、参数确认、重启与显式交接；禁止争抢控制。 |
| 35 | [实验能力预检与候选身份核验](tickets/01-capability-preflight.md) | 七种公开通信模式与完整SDK操作 | 字段/报文/错误/时间与参考逐项对照；当前只具备盘点归属，未有全部实现票。 |
| 36 | [悬停期间DDS断连与显式恢复](tickets/12-airborne-dds-loss.md)、[单电机效率故障的可复现实验](tickets/34-motor-fault.md)、[GNSS中断与状态有效性恢复](tickets/35-gnss-fault.md) | 其余执行器/传感器/环境故障 | 固定事件作用于真实模型链；效率/GNSS两例不能覆盖全部故障。 |
| 37 | [实验能力预检与候选身份核验](tickets/01-capability-preflight.md)、[正式入口启动与停止一次双栈可选实验](tickets/02-single-run-launch.md)、[已有任务记录的离线回看](tickets/06-offline-evidence.md)、[四旋翼固定工况数值对照](tickets/13-quad-numerical-baseline.md)、[生成模型构建导入与无MATLAB运行](tickets/16-generated-model-import.md)、[可选旧ABI模型DLL生命周期闭环](tickets/17-legacy-dll-host.md)、[可选新ABI模型DLL与扩展输出](tickets/18-modern-dll-host.md)、[固定输入实验的确定性重新运行](tickets/36-deterministic-reexecution.md)、[首期SITL产品流程集成验收](tickets/38-sitl-product-acceptance.md) | 完整生产记录与资源来源 | 精确版本/哈希、配置与运行身份可核验；缺失字段不能补造。 |
| 38 | [已有任务记录的离线回看](tickets/06-offline-evidence.md)、[固定输入实验的确定性重新运行](tickets/36-deterministic-reexecution.md)、[首期SITL产品流程集成验收](tickets/38-sitl-product-acceptance.md) | 完整记录、容量与缺段策略 | 离线回看不等于物理重演；新实验记录生产仍需逐项验证。 |
| 39 | [四旋翼固定工况数值对照](tickets/13-quad-numerical-baseline.md)、[坡面与障碍场景的物理反馈](tickets/19-terrain-collision.md)、[深度相机与由深度生成的点云](tickets/21-depth-cloud.md)、[Prometheus PID控制器选择与闭环](tickets/25-pid-controller.md)、[Prometheus UDE控制器闭环](tickets/26-ude-controller.md)、[Prometheus NE控制器闭环](tickets/27-ne-controller.md)、[固定输入实验的确定性重新运行](tickets/36-deterministic-reexecution.md) | 全模型数值预算 | 阈值、输入、初态、种子先于运行；首期控制门槛不能替代物理预算。 |
| 40 | [单机多航点任务与取消闭环](tickets/05-mission-waypoints.md)、[四旋翼固定工况数值对照](tickets/13-quad-numerical-baseline.md)、[双栈速度与偏航控制能力](tickets/22-velocity-yaw.md)、[双栈混合轴与轨迹跟随](tickets/23-mixed-trajectory.md)、[双栈姿态与推力出口](tickets/24-attitude-thrust.md)、[Prometheus PID控制器选择与闭环](tickets/25-pid-controller.md)、[Prometheus UDE控制器闭环](tickets/26-ude-controller.md)、[Prometheus NE控制器闭环](tickets/27-ne-controller.md)、[单机规划绕障到真实飞行](tickets/29-planner-flight.md)、[真实相机驱动ArUco目标跟踪](tickets/30-visual-tracking.md)、[双栈全球航点与home基准](tickets/37-global-waypoints.md)、[首期SITL产品流程集成验收](tickets/38-sitl-product-acceptance.md) | 此故事范围由所列票据承担；仍未实施 | 持续驻留与物理真值证明完成，瞬间过门槛或ACK不足。 |
| 41 | [实验能力预检与候选身份核验](tickets/01-capability-preflight.md)、[首期SITL产品流程集成验收](tickets/38-sitl-product-acceptance.md) | 完整Full账本及Goal G6 | 每行参考→实现→构建→运行→验收；有归属不等于有实现。 |
| 42 | [实验能力预检与候选身份核验](tickets/01-capability-preflight.md)、[首期SITL产品流程集成验收](tickets/38-sitl-product-acceptance.md) | 12仿真模式与7通信模式 | 仅对适用组合逐项验证，不用DDS或一个端口替代全兼容。 |
| 43 | 执行不变量／后续扩展 | Full硬件模式与Goal授权不变量 | 具体硬件、固件、接口、安全条件及授权就绪才运行，缺设备保持阻塞。 |
| 44 | [实验能力预检与候选身份核验](tickets/01-capability-preflight.md)、[正式入口启动与停止一次双栈可选实验](tickets/02-single-run-launch.md)、[单载具产品状态流接入UE5.5](tickets/07-ue-product-stream.md)、[生成模型构建导入与无MATLAB运行](tickets/16-generated-model-import.md) | 全部票据的复用约束 | 先核实现有环境/工具并复用；需要新增依赖时留下理由与证据。 |
| 45 | [实验能力预检与候选身份核验](tickets/01-capability-preflight.md)、[生成模型构建导入与无MATLAB运行](tickets/16-generated-model-import.md)、[可选旧ABI模型DLL生命周期闭环](tickets/17-legacy-dll-host.md)、[可选新ABI模型DLL与扩展输出](tickets/18-modern-dll-host.md) | 资源自主交付与发布边界 | 本地可用/可分发分别记录；未经确认不发布厂商资源。 |
| 46 | 执行不变量／后续扩展 | Goal多代理/Codebase Memory执行规则 | 依赖新结构的查询前核对索引，读真实源，注明未覆盖项；不单开无收益索引票。 |
| 47 | 执行不变量／后续扩展 | 已生成票据DAG与Goal集成规则 | 真实阻塞、独占写入与实际会话模型设置核验，主代理合入验收。 |
| 48 | [首期SITL产品流程集成验收](tickets/38-sitl-product-acceptance.md) | Goal G0–G6与整个Full扩展账本 | 首期通过不关闭Full目标，所有必需行完成才允许Goal complete。 |

## 本轮识别的验收注意项

1. **MATLAB阻塞是条件性的。** 当前桥票按“状态/日志＋高层命令”候选集合列出任务和回看依赖；用户只批准更小操作集时，应删除不再真正阻塞的依赖。不能因本拆分获得批准，就认定全部读写操作获批。
2. **决策关闭不等于具体阈值已给出。** 四旋翼数值票需要明确的物理/传感器预算；悬停DDS故障票需要具体动作和恢复授权。验收时必须读决议内容，不能只检查相关Issue是closed，也不能把联合物理掉队策略自动当作任务DDS失联策略。
3. **回看与记录生产分开。** “已有任务记录的离线回看”是读取旧证据的独立切片。新运行完整记录、容量/缺段、全部输入重演依赖仍在相关票和Full账本内，不能由回看器能打开文件就全部销项。
4. **控制/感知代表例只覆盖自身。** 一个规划器、ArUco、RGB及深度点云都不是所有规划/感知/视觉传感器的替代。全部剩余算法/机型/模式继续按Full账本细化。
5. **资源自主性必须实证。** 能在本机编译厂商ZIP、读取SDK或显示已暂存城市资产，不证明另一台机器可获得相同资源或具备分发条件。核心运行独立性与资源可交付性分别验收。

这些注意项补充审阅说明，不改变38张票的题名、现有依赖图或已向用户提出的确认问题。正式发布前需结合用户答复收敛条件依赖。

## 发布前只读检查

- 当前GitHub仍只有既有Wayfinder图与决策/验证票，最新图评论仍为原生控制节点的阶段证据；没有发现本次规格或38张实施票已经发布。
- ready-for-agent尚未存在；批准后发布流程需创建这一约定标签，再用于规格和实施票。没有在等待确认期间修改标签或父图。
- 既有MATLAB、首期验收、联合时间和插件/环境决策继续开放。本轮没有替用户答复或新派发实施代理。
- 当前Goal为active，仍遵守to-spec/to-tickets的发布前确认门。上一目标回合属于实质进展；本回合补充覆盖证据，不把自动续跑当用户确认。

## 核对输入身份

- 规格SHA256：8b9cde336440f9b12fad7234c818db8f6d6241c13330015e1513542e25003fbe
- 票据计划SHA256：a36e89b85ec2ace83b088094eae7697cd8f77d00363e9d45e55b82faa631217d
- Full扩展账本SHA256：d8b76ddad2f7f707da80292387fd4254ffbce14e708d171bfeb23ffa47224f4e

后续修改这些输入时应重新核对映射；本报告不能作为更新后范围仍完整的自动证明。

