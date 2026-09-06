# Prometheus ROS2 完整接口包本机验证

2026-09-05：上游43个消息、3个服务、1个动作已迁移为Humble接口包，构建及运行类型测试通过。52个可序列化类型的104次CDR往返、代表性话题/服务/动作交互和24项累计单元测试通过。原ROS1文件未修改；控制器、任务、联合场景共享时间和完整CopterSim功能尚未完成。本报告为普通工程验证（flavor=null），不是飞行或动力学精度验收。

## 范围与实现

按用户已确认的Prometheus主体、WSL/Windows运行分工推进接口迁移；数值对照方法仍是固定工况与预声明误差阈值。与本报告并行的运行边界决议在[RflySim 模块组织与 UE5.5 SITL 运行边界决策](https://github.com/unununnnn/wksim/issues/4)，完整复刻范围见[重建说明](coptersim-reconstruction.md)。本次没有启动飞控或UE、安装依赖、修改厂商目录、运行脚本消息或提交/推送源码。

源为`Modules/common/prometheus_msgs`、提交`5dcd8cfa764d558f3e15dcb88aa7d49e32c54cce`，目标为`ros2/src/prometheus_msgs`。通过Git固定树清单与逐文件内容核验，不以稀疏工作区“看起来齐全”为依据。96处声明改变仅涉及ROS2字段/常量名称、类型别名和`Class`关键字；详细映射和哈希在[UPSTREAM.json](../ros2/src/prometheus_msgs/UPSTREAM.json)。许可保留根仓库Apache-2.0和AMOVLAB归属；原package.xml的TODO许可字段不作为新许可结论，LICENSE复制仅规范末尾换行。

构建仅依赖ament/rosidl与builtin_interfaces、std_msgs、geometry_msgs、sensor_msgs；原包CMake中的MAVROS、PCL和catkin不是新IDL包依赖。ROS2 Header去掉seq、Time.sec改为int32的已知差异明确记录；没有ROS1线格式兼容声明。接口命名依据[ROS2官方定义](https://design.ros2.org/articles/legacy_interface_definition.html)，并由本机Humble生成器实际编译检验。

## 本机结果

最终构建工作区：`/root/wksim-ros2-JYxwlj`。证据：`validation/prometheus-ros2-39nRU6Qm/`。Humble、Python3.10.12、rosidl-default-generators1.2.1、rclpy3.3.21、rmw_fastrtps_cpp6.2.10；完整Debian版本写在结果内。构建使用4个并发编译任务、Release，无依赖安装。

- 完整清单43/3/1一致，96处映射一致；无额外或缺失接口。
- ament/rosidl生成并编译C/C++/Python类型支持成功。导入路径验证为本次私有install目录，暂存schema SHA256与迁移清单逐项相等。
- 43个消息，加6个服务请求/响应，加3个动作目标/结果/反馈，共52个类型。默认值和嵌套/数组/Unicode等非默认值分别序列化后反序列化并比较，104次均通过。固定数组长度和原float32/float64声明保留。
- 在私有网络命名空间、domain78、localhost限定下，同一个rclpy节点实际完成`UAVCommand`话题、`SwitchLocationSource`服务、`CheckForObjects`动作目标/反馈/结果交互，内容与动作成功状态匹配。测试夹具不代表合法传感器工况，也不会连接现有飞控网络。
- 24项单元测试包括原物理、DDS、UE桥与新增3项迁移检查，全部通过。单元测试不是再次进行实机SITL或UE画面测试；既有闭环证据仍引用各自报告。

## 复现与失败记录

构建和验证入口见[ROS2工作区说明](../ros2/README.md)。在Windows PowerShell执行：

```powershell
wsl.exe -d Ubuntu-22.04 --exec bash /mnt/c/Users/PC/Documents/odid编译/wksim/tools/build-prometheus-ros2.sh
```

完整回归在wksim目录、WSL Python3中执行：

```bash
python3 -m unittest validation.test_wksim_core validation.test_sitl_dds validation.test_ue55_bridge validation.test_prometheus_interfaces -v
```

首次创建补丁的命令输出未通过apply_patch边界校验；提高输出额度、重新取得并检查完整补丁后才成功应用，未部分覆盖原包。初次静态校验发现LICENSE仅差末尾换行，明确规范生成器输出后重新检查通过，未改许可正文。首次完整构建`prometheus-ros2-lcm6Zso0`已通过；随后增加导入路径/暂存哈希检查，并修正构建脚本从任意工作目录调用时的定位，最终全新构建`prometheus-ros2-39nRU6Qm`再次通过。旧结果保留，不把失败或较早证据改写成最新结果。

## Evidence → Finding → Path

所有证据日期为2026-09-05，source_type=file；linked_workitem为上述运行边界决策，supersedes=none。下列路径相对wksim根；每份文件可按构建入口重建为新的独立证据目录，完整回归日志由上一节单元测试命令复现。

| Evidence | source_ref / artifact_path | content_hash（SHA256） | raw_excerpt |
| --- | --- | --- | --- |
| E-01 固定源码及映射 | `validation/prometheus-ros2-39nRU6Qm/source-check.json` | `1c4d0f52725e582b0ba040c7c6f4a5225987946bb754f0d43cde57bf8acba514` | status=pass，43/3/1，96，mismatches=[] |
| E-02 原生编译 | `validation/prometheus-ros2-39nRU6Qm/build.log` | `e4e6491d1a2f870a73ee3ff32fe85ea9e4699a964078145e41f03409d408814a` | 1 package finished |
| E-03 类型及中间件运行 | `validation/prometheus-ros2-39nRU6Qm/result.json` | `c3db3cc60a0c208c4267fc318c6caffb72b5e6ef1a51f69f0308a2973f16faf7` | status=pass，47/52/104，action_feedback=1 |
| E-04 累计回归 | `validation/prometheus-ros2-39nRU6Qm/all-unit-tests.log` | `aecc319e1e68bf686147c4dd365837e9d29dcd3545ceeda8f83fd50b3184d34e` | Ran 24 tests / OK |

F-01：完整接口包在本机Humble可构建、生成并使用。severity=n/a_re，category=other，status=validated，confidence=high；evidence_ids=[E-01,E-02,E-03,E-04]。location=`ros2/src/prometheus_msgs`；impact=为后续Prometheus控制/任务迁移提供可追溯类型基础；repro_steps=执行上述构建及回归命令；remediation=n/a（非漏洞）；不包含业务行为正确性或ROS1互操作结论。

P-01：path_type=callflow；start=固定上游接口，goal=可运行ROS2接口包。步骤为固定Git清单及源文本转换（E-01/F-01），ament/rosidl生成构建（E-02/F-01），本次构建类型CDR往返与私网RMW交互（E-03/F-01），累计回归（E-04/F-01）。residual_risks：测试不穷举所有数值/消息尺寸/跨进程网络故障；控制器、同场景权威时间、产品级DDS与UE状态分发和完整功能验收仍需实现。

## Codebase Memory 与下一步

本轮已用现有图定位并直接阅读Prometheus控制来源；索引仍是06:27:29 UTC的44,399节点/144,211边快照。变更检查正确列出新增ros2目录，但只返回未跟踪目录、seed_symbols=0，不能推断没有变更。新schema/CMake/测试为not_tracked，tools为刻意排除目录；它们本轮通过直接读取、固定源码清单与编译验证，不冒称已具备图覆盖。下次依赖新结构的查询前刷新索引，详见[使用与覆盖说明](codebase-memory.md)。

继续迁移上游命令处理和实验入口，逐模式核对PX4/AP能力，再做真实Prometheus任务闭环。用户已确定的联合场景共享时间必须实现和另行验证；现有独立计时实验、接口包编译或创建决策票均不能替代该交付。
