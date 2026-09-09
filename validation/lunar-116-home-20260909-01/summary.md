# #116 47-home-contract 交付

完成静态合同 `docs/plan/47-global-home-contract.md`。仅该文件及本新证据目录属于此次提交。identity.txt 为输出转录，已去掉 NUL、行尾空白及 EOF 空行；哈希值保持原样。

源码核查确认 AP 权威 AHRS home 与 PX4 HomePosition、EKF origin 的区别；合同冻结单位、AMSL/home-relative 基准、算法、数值门槛、两栈身份/失效、原生适配文件预约和真实飞行审计要求。identity.txt 为只读命令原始输出，含项目基线、外部源 SHA256、控制/配置/补丁 SHA256；开头保留 WSL localhost 警告乱码，不影响后续哈希读回。

准确检查命令（Windows PowerShell，cwd 为 wksim）：

```powershell
gh issue view 116 --repo unununnnn/wksim --json title,body,state,labels
gh issue view 47 --repo unununnnn/wksim --json body
gh issue view 117 --repo unununnnn/wksim --json body
gh issue view 118 --repo unununnnn/wksim --json body
git status --short
git diff --cached --name-only
git diff --check -- docs/plan/47-global-home-contract.md validation/lunar-116-home-20260909-01
$contract=Get-Content docs/plan/47-global-home-contract.md -Raw
@('home_generation','local_origin_generation','datum_unverified','0.001m','0.5m','2.0s','get_relative_position_NED_home','HomePosition','FRAME_GLOBAL_REL_ALT','MapProjection','尚未创建','写入范围') | ForEach-Object { if(-not $contract.Contains($_)){throw ('Missing: '+$_)} }
Test-Path Simulator/wksim_control/global_reference.py
Test-Path tools/run-global-flight.sh
```

原始结果：diff 检查退出0；暂存区当时为空；12项合同锚点 PASS（仅文档完整性，不是算法测试）；两个未来入口均 False。源码比较与公式为人工静态审查，未运行转换 oracle 或飞行。原始早期定位错误也明确记录：Simulator 下 native_px4.py/native_arducopter.py/frames.py 不存在；图查询定位到 ros2 实际路径后读取。PX4 msg 顶层旧路径不存在，实际版本化消息位于 msg/versioned。未更改任何源文件来消除这些路径错误。

外部源复查命令（WSL Ubuntu-22.04/root）：

```sh
cd /root/wksim-px4-state-ONa1Kw/src
git rev-parse HEAD
cat msg/versioned/HomePosition.msg msg/versioned/VehicleGlobalPosition.msg
grep -n -A4 -B2 -E 'home_position|vehicle_global_position' src/modules/uxrce_dds_client/dds_topics.yaml
grep -n -A25 'MapProjection::project' src/lib/geo/geo.cpp
sha256sum msg/versioned/HomePosition.msg msg/versioned/VehicleGlobalPosition.msg msg/versioned/VehicleLocalPosition.msg src/lib/geo/geo.cpp src/lib/geo/geo.h src/modules/uxrce_dds_client/dds_topics.yaml
cd /root/wksim-dependencies/ardupilot-1511f271
git rev-parse HEAD
grep -n -A35 get_relative_position_NED_home libraries/AP_AHRS/AP_AHRS.cpp
sha256sum libraries/AP_AHRS/AP_AHRS.cpp libraries/AP_Common/Location.cpp
```

Codebase Memory 原生 index_status 成功，ready、50865 nodes/165157 edges；search_graph 查询 `home global native_px4 native_arducopter` limit8 定位 AP 源文件（has_more=true），仅用作导航，没有据此作覆盖率或完整调用图结论。

边界：#118 当前写入范围不足以改原生源码，合同列出具体预约，须主代理先更新该票范围。AP 同值 home 重设不可由当前 tuple 检测；实际 ABSOLUTE/AMSL 配置链、PX4 消息安装与真实周期尚待实证。以上是明确后继接入条件，不把本静态设计宣称为实现/飞行通过。#47 和所有父票保持原状。

模型/推理设置：用户指定 gpt-6-astra / low；当前可见系统说明仅标识 GPT-6，未提供可独立读取的实际运行 model ID/effort，因此不声称已核验精确设置。本任务由当前主代理独立完成，未创建子代理。

范围检查时还有 AGENTS.md、推进指南、Simulator/wksim_core/gnss_event.py、Simulator/wksim_core/px4_mavlink.py 及 validation/test_gnss_px4_injection.py 的其他任务改动；全部排除并保留。
