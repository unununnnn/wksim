# #113 · 46-input-contract：物理重新计算输入合同 v1

2026-09-09。本合同冻结 #114 的实现要求与 #115 的独立验证要求。#113 选择完成条件允许的 **explicit insufficient-recording rejection**：本次检查的旧 #24 baseline 记录不能直接准入。没有执行物理重算；#46 和 #20 保持开放，#16/#20/#24 原依赖不变。R1 numerical_failed、RateUnmet 和 G6 原结论不变。

## 1. 已核对的真实接缝

- `Simulator/wksim_runtime/replay.py` 读取 JSON/状态，输出 mode=`offline-records-not-resimulation`；不调用模型积分。回看成功不能证明重新计算。
- `Simulator/wksim_core/model.cpp` 在 create 时 initialize 后把整个 ExtU 清零；每次 step 写入 inPWMs[16]，允许 1..1000 次积分但仅返回最后一次的 Vehicle60、Sensor30、GPS30。原生 ExtU 另含 TerrainIn15d[15]；当前包装未提供地形修改入口。
- `model.py` 的 Model.step 检查 16 个归一化输入与固定时钟，不能导入中途内部状态。`model_parameters.py` 仅开放质量，绑定全部固定配置、原源及包装哈希，ConfiguredModel 强制每进程一次生命周期、未用通道为零。
- `worker.py` 保存每次接受的 request、commands、epoch、tick 和 state；`joint.py` 保留输入来源和共享时钟提交。worker 返回、场景 commit、后续 FC 输入屏障是不同完成位置；缺最后屏障不能凭 worker 行数补作成功。
- `tools/major_model_recorder.cpp` 另支持完整 31 路输入和 major-root/post-step 两种输出，固定 501 次调用；比较截止 0.5s，引擎截止 0.501s。不能与包装的 500 次 post-step 记录错位比较。
- `tools/quad_model_parameters.py run` 的旧记录有 config、库哈希、固定 commands、requested_ticks 及逐 tick output120，缺显式 terminal 和生命周期事件封存。本合同没有回写旧运行的声明。

生成源通过原 ZIP 的 cpp/h 直接读取；根输入、1ms ODE4、随机初始化的身份见本票证据。厂商源码只在本机核对，不随提交分发。

## 2. 准入包和封存

新 schema 名 `wksim.physics-reexecution.v1`。包内仅允许 manifest.json、config.json、inputs.jsonl、expected.jsonl、events.jsonl、terminal.json 和 manifest 明确列出的本地构建证据。导入器拒绝未知必需语义、重复 JSON 键、非有限数、布尔冒充数字、绝对/越界路径、符号链接、重复成员及读取期间变化。源目录只读；输出必须在源目录外以独占新建方式产生。

manifest 必需字段：schema、profile、source_run_id、scene_epoch、instance_id、source_capture_revision、contract_sha256、config_identity、build_identity、initialization、randomness、time、input_encoding、output_phase、event_policy、members。members 对每份原件记录路径、字节数、SHA256、记录数及首末序号；manifest 的 SHA256 由独立运行请求/审计回执绑定，不能以自称哈希代替外部绑定。封存只能在源进程已退出且源文件稳定后完成，记录退出码、原 argv、PID/boot_id/starttime 与最后确认前沿。哈希证明字节身份，不证明来源真实性。

build_identity 必含 ZIP 和五个 allowlist 成员 SHA256、参数化 cpp、实际包装、实际加载库及动态依赖 SHA256、build.json、完整编译 argv、编译器版本、OS/WSL、架构、CPU 浮点环境与 libc/libstdc++ 版本、Python/ctypes 位宽。运行时重算这些哈希并验证加载路径；路径存在或 config 的 model_identity 相等不足以代表同一构建。保留本地来源限制；不从网络或兄弟项目替换缺失的模型。

## 3. 物理输入与源时间

首个支持 profile=`quad-mass-cold-post-step-v1`，使用原 `wksim.quad-mass.v1` 完整配置；固定 Quad X，质量 0.5..5.0kg，其余参数原值。配置原字节和规范化身份都绑定。所有 22 项具名配置及完整生成参数表均由源/构建身份覆盖；仅记录质量不充分。

每个输入行必须包含 scene_epoch、instance_id、tick（整数 1..N）、before_ns=(tick-1)*1000000、after_ns=tick*1000000、inPWMs（16 个 binary64 可往返十进制数）、TerrainIn15d（15 个同精度数）、source_ref、event_frontier。一个输入行只调用一次 1ms step，实际 before/after 引擎时间另记录；不能把墙钟、ROS 或 FC boot 时间当积分时间。

inPWMs 单位是归一化量 [0,1]，不是微秒 PWM。Quad X 0/1/2/3=前右/后左/前左/后右，FRD 角度45/225/315/135度，源旋向 -1/-1/+1/+1；4..15 必须严格零。记录在适配器转换、饱和、保持之后实际施加的值；原 FC 帧字节/哈希、来源时基、序号、接收时间保存在 source_ref 引用的封存证据中。静态人工输入 source_ref 指向预先冻结的实验计划，不伪造 FC 时间。

当前 profile 要求 TerrainIn15d 全15项严格零，含表示地面 NED z 的第0项；其余槽位按原生槽位身份保存，未确定物理单位的槽位不得开放非零。需要地形、风、故障效率或其他新输入时，必须先交付新 profile 的原生施加与读回接缝，再接受该输入；不能静默忽略字段。

统一输入编码为逐 tick 行。旧运行原先明确声明的恒定输入计划可由未来导入器无损展开，但须保留计划原件及覆盖范围，并逐 tick 绑定到输出；不得对降采样状态或缺失执行器插值、猜零、后向填充。已经记录的 sample-and-hold 是源输入语义，事后用“可能保持”修补缺段不是。

联合场景每个成员都需独立输入/输出流与同一共享 epoch/commit 证据，严格绑定各成员 model tick 和 FC 来源时基。不把两次独立实验拼成联合重算。当前首个 profile 仅支持独立静态源；未知联合事件映射应拒绝，不能降格后报告整场通过。

## 4. 初态与随机性

initialization 必须声明 cold_initialize_at_tick_zero、原始构造/initialize/ExtU清零调用顺序和完整配置身份。初始位置 NED、速度/角速度 FRD、Euler rad、motor初速均为源固定零值；GPS原点40.1540302/116.2593683度、环境高度参数-50m也保留。完整 X/DW、离散滤波器、积分器、延迟、求解器与多速率计数器由同一构建的 initialize 确定，不能仅以姿态位置五个字段代替。

随机性不是 none。原生成源 `rt_urand_Upu32_Yd_f_pw_snf` 使用乘数16807/模2147483647及生成 initialize 的种子变换/边界规则。逐块列出 S246 Number1=[12233,645554,678766]、Number2=[3243,44556,2334343]、Number3=[45465,454534,1234232]、Number=15634、Number4=25634；S245 Number2=[1452,787,69]、Number4=[5445,45433,33433]，合计17个标量流。randomness 必须声明这些块、种子、算法源码哈希、初始化消费和逐步消费顺序绑定到实际生成源。没有 OS 随机种子注入；禁止以统一 seed=0 或重算器自行换 PRNG。

只允许新进程从 tick0 完整推进；非零 tick 起始、warm restart、只恢复输出120、缺内部随机/滤波状态均拒绝。冷重置是新进程和新 epoch 的独立包，记录 parent run/terminal 哈希，重新 initialize；不继承旧任务、时钟或 RNG 状态。未来若支持 checkpoint，须先定义并验证完整内部状态序列化 ABI，本合同未批准该路径。

## 5. 事件、缺段与 terminal

events.jsonl 为有序流，字段 event_seq、run/scene/instance 身份、effective_tick、phase(before_step/after_step)、kind、source_ref、payload；manifest 必须声明无事件或给出精确数量。空文件不能自动推断无事件。

暂停和恢复只改变调度，不消耗积分步或 RNG；单步令牌显式给出批准步数，每次调用仍记录一个 tick；恢复不追补墙钟时间或历史动作。倍速/重锚只属墙钟映射，不能更改 dt。故障/异常输入必须记录施加前后输入和事件顺序；不受支持的模型内部突变拒绝。未知事件、乱序、身份跨代、暂停中额外积分、恢复补步均拒绝。v1静态 profile 除开始/正常结束外的事件直接报 unsupported_event，后续事件 profile 必须按本节语义实现，不能丢弃事件以运行静态入口。

terminal 必须包含正常退出码0、attempted/returned/emitted=N、last_tick=N、engine_end_ns=N*1000000、全部事件消费前沿、stream哈希/数量、source_status=complete。场景还须记录 committed_tick 与各成员确认前沿；inflight 或未确认尾步保留为失败，不能剪掉尾段后声明原整场完整。缺行、重复tick、乱序、非有限、尾行截断、缺terminal、哈希变化、模型/参数/来源身份不符均 fail-closed。部分轨迹可用于诊断，不能输出 reexecution_passed。

## 6. 输出相位与冻结数值门槛

expected.jsonl 每tick含同一身份、tick、output_phase=`post_step_api`、完整 output120，顺序原样为 Vehicle60[0:60]、Sensor30[60:90]、GPS30[90:120]。坐标/单位保持原生 NED/FRD/SI 与 HIL 原生缩放，禁止比较前重采样、角度重包或按显示单位截断。源模型输出并非全部同一计算相位的连续状态；本 profile 只比较同包装 post-step API，不将它称为 major-root 真值。

本合同预冻结同一受控库/平台的门槛：**所有120槽每tick数值相等，atol=0、rtol=0**（+0/-0视作数值相等；不要求 JSON 字节相同）。整数身份、计数、flags及时间网格严格一致；引擎浮点秒对整数tick网格仅允许既有 Model.step 的1e-8s调度检验，该值不是输出数值容差。拒绝 NaN/Inf。选择零预算是同一库、相同冷启动与相同输入的确定性要求，未从本票结果拟合，也未更改R1物理误差预算。

审计报告必须给出全部比较数N*120、首个不符tick/槽/源值/重算值、逐槽最大绝对与相对差、失败总数及输入/输出身份。任何一项超限即 numerical_failed，不以平均误差掩盖。跨库、编译器或平台只能输出 platform_comparison_unbudgeted 和差异，不套用本门槛声称通过；另行预声明预算后才可作为不同 profile。

## 7. 命令与实现边界

以下是已存在的配置导入/检查命令（Windows仓库根，目标必须不存在），不是重新计算验收：

```powershell
python tools/quad_model_parameters.py import validation/quad-parameters-native-20260909-b/baseline.json validation/lunar-113-20260909-input-contract-01/imported-config.json
python tools/quad_model_parameters.py inspect validation/lunar-113-20260909-input-contract-01/imported-config.json
```

#114 必须实现下列**设计 CLI**，当前文件尚不存在，不宣称可执行；参数名称、失败语义和输出合同在此冻结。全路径由操作者指定，输入不足时 import 退出2且不创建合格包；run仅接收已封存包，不接受任意执行命令。

```bash
python3 tools/reexecute_physics.py import --source /root/wksim-reexecution-source-01 --output /root/wksim-reexecution-input-01
python3 tools/reexecute_physics.py run --input /root/wksim-reexecution-input-01 --library /root/wksim-reexecution-build-01/libwksim_configured.so --output /root/wksim-reexecution-run-01
python3 tools/reexecute_physics.py audit --input /root/wksim-reexecution-input-01 --run /root/wksim-reexecution-run-01 --output /root/wksim-reexecution-audit-01.json
```

import 输出 manifest 和逐tick输入/预期/事件/terminal原件及来源引用；run 输出 request.json（绑定输入manifest哈希）、actual.jsonl、terminal.json、stdout/stderr、加载身份；audit 输出 status、errors、identity_checks、counts、per_slot_errors。退出0只用于对应阶段成功；格式/准入失败2，模型执行/数值失败1，任何失败保留新目录和原始错误。run 无网络、ROS、FC、UE和控制发布者；使用独立进程只加载验证后的模型。不得执行 manifest 提供的 argv、导入路径或动态脚本。实现票须以负例证明准入拒绝发生在模型初始化前。

#115 要取得完整源记录并用独立新进程重新积分，独立审计全部输出。单次生成输出、旧 #24 的两个重建响应相等、major recorder 对照和状态回看均不替代该步骤。需覆盖缺tick/改输入/换模型/改种子/缺初态/错事件代次/缺terminal/截断/相位错配负例；原件只读，篡改仅在新夹具副本。

## 8. 本票结论

选定待准入旧源 `validation/quad-parameters-native-20260909-b/baseline.jsonl`：header固定16路输入、500连续tick和120槽均可查；没有terminal或事件封存，库路径位于旧/tmp，不能假定当前仍可加载。判定 **insufficient_recording**，不得推断完整可重演。完整合同和拒绝结论满足 #113 的二选一 AC；实际实现、重算及父依赖由 #114/#115/#46 保留。

证据：`validation/lunar-113-20260909-input-contract-01/` 的 review.ps1、review.json、summary.md；只读核对命令、当前源哈希、原件字段/行数、模型设置和明确不足均在其中。本票只完成设计审查。
