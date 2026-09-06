# 当前执行前沿与 QGC 隔离缺口

2026-09-06 JST。上一轮原生时钟与AP停机证据已改变后续决策依据；本轮完成剩余执行前沿的实时核对及有界QGC一手资料补充。**没有修改生产代码、运行新的SITL或完成新的产品验收；Full Goal仍未完成。自动Goal续跑不是用户对待决策问题的答复。**

## 实际依赖，不使用标签推断

2026-09-05 22:18:55 UTC，通过GitHub读取全部Issue状态，并逐一读取31张未关闭初始实施票的原生 `dependencies/blocked_by`。检查了依赖状态与完整Issue清单一致、无循环；原始结果与命令在 [dependencies.json](../validation/implementation-frontier-20260906/dependencies.json)。

初始38张实施票中#11–#17已关闭、31张仍开；依赖已全部关闭的只有#18与#42。沿未完成依赖递归到以下六项；这是**初始票据图**的计算结果，不是Full范围被压缩成38张。

| 未完成入口 | 当前实际门槛 | 受其影响的代表实施 |
| --- | --- | --- |
| #5 | MATLAB首期操作范围未获答复；TCP/JSON传输选择已确认 | #41 |
| #6 | 首期验收、固定工况及正式数值预算仍为HITL | #23/#24、#32/#33、#38/#43及后续构型/控制器 |
| #8 | 联合调度和异常策略尚未确认 | #19/#20/#21、#22及后续故障/复现 |
| #9 | 可选插件与环境反馈契约未确认 | #26–#31、规划/感知后续 |
| #18 | 实际浏览器交互验收未完成；此前管理策略限制未绕过 | #48 |
| #42 | 本机QGC来源/安全隔离启动及实际交接验收未完成 | #48 |

[Full扩展账本](plan/full-scope-expansion.md)中的12种仿真模式、7种通信、其余机型、硬件、组件数据库等义务仍在。未定义外部系统、硬件授权、未知数值预算及插件/场景契约没有被自动改成可执行任务；没有为了绕过现有依赖而另建重复实施票。

## 本轮QGC补充了什么

[完整研究](2026-09-06_qgc-isolation-research.md)继承[已有本机核对](qgc-local-launch.md)，避免把较新的源码直接当作现有厂商程序。当前文件仍为 `E:/rflysimtools/QGroundControl/QGroundControl.exe`，33,909,760字节，版本资源0.0.0.0，SHA256 `61f3c559fbb6401368981cc41030a23312d584f64a206d5d9b922c3813da7bc9`；Qt5Core版本5.15.2.0。旁边的 `configData/Config.json` 是VisionSensors配置，不是QGC连接配置。

研究代理核对了官方v3.5.0、4.0.0、4.1.0、4.2.0、4.3.0、4.4.0固定提交，未在所查启动路径中找到 `--settings-file`。这不是所有版本或厂商二进制的穷尽证明。主代理复读了关键v4.4启动/参数解析、LinkManager及Qt5.15.2代码：

- 选项未知未必被该解析器拒绝；正常打开窗口不证明隔离参数生效。清空/版本迁移可能抹掉预填的禁止自动连接设置。[启动代码](https://github.com/mavlink/qgroundcontrol/blob/15bdfd5f16562a09ccb1a57808ed0405049645a7/src/QGCApplication.cc#L228-L301)
- 关闭设备自动连接项不阻止串口枚举，也不替代已保存链接的自动启动检查；ZeroConf另有UDP/TCP路径。[LinkManager](https://github.com/mavlink/qgroundcontrol/blob/15bdfd5f16562a09ccb1a57808ed0405049645a7/src/comm/LinkManager.cc#L462-L608)
- Windows默认INI目录来自Known Folder API；只改子进程APPDATA等变量没有建立独立配置的证明。[Qt实现](https://github.com/qt/qtbase/blob/40143c189b7c1bf3c2058b77d00ea5c4e3be8b28/src/corelib/io/qsettings.cpp#L905-L1020)

因此未启动QGC（含不尝试未知的help/version参数），未创建一个把这些假设当作事实的启动器/主机遥测出口。当前证据未提供受支持的隔离路径，**不等于宣称QGC永远不能隔离**。独立QGC重建或操作系统隔离属于需要另行确定范围的方案；没有修改厂商安装、用户设置、注册表、防火墙或设备。

既有只读原生MAVLink观察器源码已复读；它的Unix出口没有命令返回路径，但不能因此证明独立QGC进程不会连接其他端口/设备。原有双栈遥测/任务交接证据保持其原始适用范围，不冒充新QGC显示证据。

## 协作、记忆与停止边界

research技能将补充调研限定为一手来源和单份报告。Boole `01a073a2-2078-7042-95e8-0b0f0969c3e3` 的实际turn_context为gpt-6-astra/low，已核验、已完成并关闭、无嵌套。主代理负责实时依赖核对、关键原文复读及集成说明；[coordination.json](../validation/implementation-frontier-20260906/coordination.json)记录实际配置、文件哈希和只读进程检查。

末次检查没有QGC进程；原AP PID828/start_ticks19268和UE PID35256/原创建时间及命令行不变。本轮未创建SITL/UE进程，不虚报新飞行/清理验收。Codebase Memory实读ready、92,892节点/202,270边；两个读取的遥测源文件仍提示metadata_changed，已直接读源，报告按docs祖先排除。没有产品源变化或依赖新结构的查询，因此未为纯文档重复索引。

主线仍需用户确认[上一轮候选](2026-09-06_native-clock-and-stop-report.md#待用户确认的生产候选尚未采纳)：1ms权威物理步、4ms输入边界、掉队全场停止推进、显式恢复不重放旧控制、冷重置新epoch、停止不推进已暂停物理；先在独立AP候选验证整数时钟和可中断等待。该问题未回答，具体超时/ROS任务时钟等最终契约也未被代答。当前不关闭#8/#18/#19/#20/#42或父图/规格，不缩减Full目标。

