# 2026-09-07 联合生命周期、MATLAB与显示接缝

本轮承接 `6d2e371` 及此前未提交进展，恢复了已迁移到E盘的Ubuntu-22.04资源。完整Goal、#18/#19/#20/#22/#41及G0–G6/Full仍开放。原Wayfinder父图及38票原生依赖未改写；G0只读复核确认48故事有归属、38票的87条原生阻塞边与发布清单一致。

## 已通过的联合生命周期

修复恢复/继续的最终ACK跨越5s截止仍可能成功，以及模型/FC退出后冷重置请求被缺失maps证据阻断。退出参与者明确记录maps不可用，其余参与者保留实际映射、身份及退出状态；健康审计的正常退出要求没有放宽。停止失败必须有failed响应，不能伪报completed。SIGTERM后采用本机Humble的幂等清理，避免重复shutdown覆盖原始失败。

|真实场景|证据目录（validation/）|结果|
|---|---|---|
|PX4模型进程退出|joint-input-stall-5o_zb26v|已提交tick52056，pending52057不提交；显式冷重置、新地面epoch及停止通过|
|AP飞控进程退出|joint-input-stall-0fexbp4y|tick51924模型已提交、ap_input未完成；原输入/屏障边界保留，冷重置及停止通过|
|健康共同任务|product-joint-flow-koyf3_wj|69572共同tick、同飞13.960s、暂停/四tick单步/继续/落地通过|
|PX4 Agent空中断连|product-joint-flow-d3dqnmx8|显式恢复、新Task降落、冷重置及旧请求隔离通过|
|AP Agent空中断连|product-joint-flow-2nzfj9ta|同上，独立真实病例通过|

五份原始审计通过。死亡病例分别解码模型、原生执行器/传感器线路、权威clock、公共DDS和任务；两份各两个损坏负例被拒绝。它们不等于成功飞行，也不把死亡后缺失的映射宣称为完整生命周期无依赖证明。[死亡审计](../validation/retirement-audit-20260907/px4-model-audit.json)、[AP死亡审计](../validation/retirement-audit-20260907/arducopter-fc-audit.json)、[健康审计](../validation/migration-resume-20260907/audit-healthy.json)、[PX4恢复审计](../validation/migration-resume-20260907/audit-px4-dds.json)、[AP恢复审计](../validation/migration-resume-20260907/audit-ap-dds.json)。

## 已通过的MATLAB与真实显示

新增可选localhost TCP/JSON桥，复用公开工作台HTTP→正式WSL入口。基础MATLAB客户端不参与step/keepalive；配置只允许既有mission字段，不暴露任意文件、运行库或原生命令。请求/连接/运行身份、有界帧、超时和重连不重放分别校验。完整接口和本机启动环境边界见[MATLAB桥说明](matlab-bridge.md)。

|真实病例|MATLAB退出后FC boot推进|物理推进|终态|
|---|---:|---:|---|
|PX4 run3|61.560s|61.720s|6航点各10s驻留、暂停/显式恢复、正常落地；16张LIVE原生UE画面，其中10张在退出后的观察窗口|
|ArduCopter run2|65.427417s|66.780s|同一MATLAB操作链，正常落地；本例未启动UE|

每例两次真实MATLAB启动均为R2022b，基础许可可用且实际PID退出。第二次连接只有状态/结果/日志读取，start恰为一次、mission-action恰为两次。原始结果通过raw_json保持精度及数组结构。[独立审计](../validation/migration-resume-20260907/matlab-flight-audit-verified.json)重新计算原物理窗口，核对公共请求、原生确认记录、任务动作文件及UE Actor误差；位置流只有公共受理与物理完成，不伪称每个位置设定值都有原生ACK。

真实UI显示修复来自实际socket复现：私有/tmp中的同名目录遮住主机后来绑定的显示socket。现在只把已准入显示/遥测父目录按原inode绑定到私有挂载，其他/tmp写入仍隔离。目录FD、所有者、0700和绑定后inode均校验，实际迟到绑定及socket重开、原隔离两个检查通过。支持在同一父目录中重建socket；不自动跟随删除/重建后的父目录。该修复无需修改或重导P450资产。

工作台旧默认模型位于已清空的/tmp，真实预检正确拒绝后，使用原构建函数在`/root/wksim-dependencies/models/wksim-model-1__iz_qj`重新构建。新产物SHA256仍为`cc0bc2d10790043251f38bb6a53f4d774379dd37a02b09cceba43ac1fafb02b3`。统一资源映射只改变位置，保留archive/wrapper/compiler/profile/library及实际build路径检查和历史基线。[构建清单](../validation/migration-resume-20260907/persistent-model-build.json)。

## 失败与实际边界

- `joint-input-stall-2bglzwj8`保留驱动误将故障诊断文本变化计作物理推进的失败。物理字段精确比较修正后才取得新成功病例。
- MATLAB PX4 run1因旧模型缺失在预检被拒，零飞行；run2实际任务pass而UE无Actor回读，整体仍失败。AP run1未等到当前合法resume offer；公开取消后依据重新读取的合法offer显式恢复并LAND，最终cancelled/safe_landing/children_reaped，失败未改判。
- 第一次MATLAB启动实际触发用户既有RflySim启动脚本更新CmakeInfo/编译配置并删除变更标记。未取得启动前完整外部哈希，不能声称知道完整改动集合；未回滚未知改动。后续任务私有startup.m、-sd和which校验实测成功，不再运行该自动注册脚本，详见桥说明及原始日志。
- 首次默认矩阵的新生命周期测试错误导入旧无scene模块，已按既有候选门槛分开执行；Windows命令有一次测试模块名拼写错误，日志保留。两次MATLAB审计开发失败分别来自终态物理继续产生26条记录、误要求位置流也有原生ACK；只修审计适用规则，没有修改原始记录或数值阈值。
- MATLAB正常cancel随后由真实客户端单独通过，见下方补验。实际浏览器/QGC、联合双载具UE、全部Full义务及正式数值预算仍未完成。单机PX4本例使用保留的旧参考固件，不能据此宣称无Gazebo或完整G5；独立无Gazebo候选已有联合路径证据。

## 检查与下一前沿

在显示挂载修复前的完整矩阵：Windows51项、安装联合候选79项、默认355项（29跳过）、旧预检11项通过；对应日志均在`validation/migration-resume-20260907/`。其后显示挂载两个真实检查和双栈MATLAB实飞/独立审计通过。倍率源随后继续变更，新的全量矩阵与正式倍率验收另行记录，不能把前一版结果当作所有新源的验收。

首期0.5×/1×倍率已实现，尚在真实调优/验收。第一次0.5×在地面tick28376因累计迟到100.217ms真实冻结，结果保留于`joint-rate-flow-z8q5vds2`，未放宽批准预算。优化等待释放点后，`joint-rate-flow-wjcmw9uu`完整联合飞行132524 tick，26个完整10s窗全部在±2%内、首60s窗在±1%内、最坏累计迟到84.737ms；仍需独立区分地面/飞行阶段及补齐3epoch。1× `joint-rate-flow-sufbeqlt`实测0.967828×，在tick3032/100.318ms迟到冻结并正常停止，不标1×通过。变速/过载/冷重置及Full后续倍率仍须逐项满足。

额外当前清理核验：已结束MATLAB病例的30个记录Windows PID均无当前匹配进程，12个不同Linux进程组ID均为空；6个联合病例的10个epoch保留同时期无残留记录。当前新的倍率实验不在这批已结束运行中。见[清理选择范围](../validation/migration-resume-20260907/cleanup-selection.json)、[Windows实读](../validation/migration-resume-20260907/current-windows-processes.json)、[Linux实读](../validation/migration-resume-20260907/current-linux-groups.json)。

所有代理均从实际turn_context核验gpt-6-astra/low，无嵌套。主线维护互斥写入与真实资源，读取实际代码、串行实飞并独立审计；没有通过此报告关闭Goal或原父图，没有推送混合工作区或厂商资源。

## 后续补验：倍率、批量模型收发与 MATLAB 取消

串行模型收发版本的三个独立 0.5× epoch `joint-rate-flow-7tcgrb6o`、`joint-rate-flow-ynhheu8i`、`joint-rate-flow-iz01zhz7` 完成了完整原始数据审计。三例各有 26 个完整 10s 窗及一个真实连续双机空中 60s 窗，最坏累计迟到分别 28.607132 / 53.680553 / 66.825204ms。聚合审计核对不同 epoch、相同源快照和全部批准预算，见 [三运行审计](../validation/migration-resume-20260907/rate-half-cohort.json)。0.5× 验收没有借用地面 60s 代替空中窗口。

模型传输随后改为同一个 3s 截止内先发送所有参与者请求，再收齐所有真实响应；唯一物理时钟仍只在全员成功后提交。每个实际收到的响应保留独立确认步号，批次故障时已涉及的通道均封闭。补修持续到达部分数据时可能饿死健康检查，以及 KeyboardInterrupt 未封闭通道的问题。真实双模型 1000tick 的全部状态与轨迹逐项一致，17 项专项检查通过，含两个先失败后修复的中断/健康反例，见 `validation/parallel-model-rpc-20260907/checks-green/`。模型独立基准约 1.80 倍提速，不等于飞控联合 1× 通过，也不等于 G6 精度验收。

批量收发版本的 1× `joint-rate-flow-p7xgcrmv` 在 tick12528 累计迟到 100.163672ms 冻结，实测倍率 0.9921762986；仍不通过。首次正常生命周期病例 `joint-rate-flow-glcb_mxb` 在变速/暂停前遇到一个 139.704765ms 步组，累计迟到 163.013993ms 冻结；确切原因尚未证实，失败保留，未放宽预算。前述三运行结果属于旧串行收发源快照，不能自动覆盖当前批量收发版本。

当前批量收发版本已另行取得两种真实行为证据：

- `joint-rate-flow-4kt7s0ei`：内核确认只暂停本任务 supervisor 150ms，tick51488 在完整屏障处冻结，4s 内不推进；显式恢复、新降落任务、tick63564 正常停止。[完整原始审计](../validation/migration-resume-20260907/rate-overload-audit.json)通过，保留每个模型通道的请求与响应进度。
- `joint-rate-flow-td2w1nim`：地面冷重置产生全新 epoch 和命名空间，旧 epoch 的 1× 请求被拒绝，新运行仍为 0.5×；两运行正常清理。[完整原始审计](../validation/migration-resume-20260907/rate-reset-audit.json)通过。本例没有飞行，不冒充空中重置。

`matlab-cancel-px4-20260907-run1` 从真实 MATLAB 客户端仅发送一次公开 cancel，空中最高真实高度 3.478177m，终态 `cancelled/safe_landing/children_reaped`，最后真实高度约 -0.00000264m，MATLAB 实际 PID 已退出。取消发生在第一个航点完成前，因此零已完成航点为预期；不改判任务成功。见 [原始取消证据核对](../validation/migration-resume-20260907/matlab-cancel-proof.json)。

浏览器补验在打开本机工作台之前被管理策略阻断：浏览器安全检查不可用，无法验证管理员策略。没有观察到页面，也没有使用其他浏览器或 HTTP 结果绕过该验收。仅为本次测试启动的工作台服务已核验身份并退出，零作业，见 `validation/browser-workflow-20260907/access-blocked.json`。

后续批量收发病例 `joint-rate-flow-82p4pbu7` 完成 132288 共同 tick、76.968s 同飞、两次变速和正常落地；在 tick56184 暂停 4.107515052s，仅执行 56185–56188 四步，再取得双 Control 新原生状态 ACK。完整原始审计 `rate-lifecycle-audit.json` 通过，最坏累计迟到 55.454487ms；短时 1× 切换不等于持续 1× 验收。

代码复核随后发现重锚前可能清掉旧段尚未检查的迟到，先由两个确定性用例复现三处漏检，再补上活跃边界检查。暂停无锚时间仍豁免；显式故障恢复依旧需要授权。变速/暂停分支的异常进入原有故障锁存，并返回失败请求。`joint-rate-flow-ngzzz774` 的真实短生命周期通过，但新增检查采样尚未单独写日志，旧审计正确拒绝无法重算的累计最大值；这份病例仅记行为通过、原始倍率审计未通过。随后补充带旧理想时刻、实际检查时刻、步号和误差的 `rate_boundary_check` 原始记录，不放宽审计规则或预算；当前源码另行复跑。

本次回归：默认 373 项（33 跳过）、旧预检 11 项、安装候选 79 项、Windows 操作台/桥 100 项通过；最后的边界记录补充又通过 10 项针对检查。日志分别为 `session-product-checks-MnR5QK1d`、`joint-control-checks-rAzldjdM` 和本轮 `windows-post-rate-checks.log`、`rate-anchor-recorded-green.log`。长期倍率病例仍固定 35s/35s 驻留；操作语义复跑采用预先记录的 12s/8s，不用短窗口宣称长期倍率合格。

已确认的 #5/#8 决策已关闭，原文及状态读回见 `publication/decision-resolution-readback.json`。这不关闭对应实现票、不改变 #6/#9 或原 Wayfinder #1。此举纠正已回答决策继续显示为阻塞的流程问题，剩余实现和验收依旧逐票完成。
