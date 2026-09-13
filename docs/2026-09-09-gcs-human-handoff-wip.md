# #42 人工模式交接候选入口

本文件为初始设计历史稿。用户随后授权“全程你自己确认即可”，最终由助手自动操作真实GUI完成双栈验收；300秒决定窗口、流式全包摘要及落地后桥停止握手已取代下面的初始设计。[最新授权](2026-09-09-gcs-automation-authorization.md)与[真实收口报告](2026-09-09-gcs-handoff-closure-report.md)为当前结论，下面45/60秒、人工必做、未实跑和8192项容量描述均保留为历史。

2026-09-09。用户已经批准受控WksimGCS构建/连接，且明确保留本人切走任务模式的动作，见[批准记录](2026-09-08-five-decisions-accepted.md)。本轮准备人工验证候选，尚未启动新的SITL/QGC实跑，没有把自动模式请求算作人工动作，#42保持开放。

## 实际操作

Windows项目根执行预检：

```powershell
python -X utf8 -B tools/validate_contained_gcs.py --stack px4 --manual-handoff
```

用户在场时再执行下列命令，OUTPUT换为新的项目validation子目录：

```powershell
python -X utf8 -B tools/validate_contained_gcs.py --stack px4 --manual-handoff --execute --output OUTPUT
```

候选驱动会启动受控WksimGCS、独立PX4物理/飞控/Control和原始字节桥。任务先按正式公共入口解锁、起飞并移动到离home约[2,3,3] ENU、yaw=-0.9rad的已验证接管工况。到达 `awaiting_human_qgc_mode` 时，由用户在WksimGCS模式菜单选择 **Hold**。本地QGC PX4FirmwarePlugin.cc:36/63/88把Hold映射到AUTO_LOITER；ArduCopter下一轮选择 **Brake**（ArduCopterFirmwarePlugin.h:84，BRAKE=17）。只操作本次自建WksimGCS窗口，不使用现有MissionPlanner或其他设备。

候选等待实际新鲜飞控状态转为AUTO.LOITER/BRAKE及精确external_mode_left_no_automatic_reacquisition撤销事件。随后核验原有任务不继续输出、物理继续、旧请求不被重放。到达 `awaiting_explicit_takeover` 时，需要用户另行明确重新接管；用户可以在会话中说“重新接管”，由主代理执行，或本人运行：

```powershell
python -X utf8 -B tools/request_gcs_takeover.py --output OUTPUT
```

此CLI仅向当前运行提交带run/epoch/nonce的决定，使用同目录临时文件和原子排他hardlink交付完整JSON，不覆盖已有决定。运行器继续核验本机native hold及45秒期限；请求文件不是飞控确认。确认后才发送新的公共接管请求，从当前实际位置/偏航保持，再执行新航点和落地。AP使用独立新OUTPUT及 `--stack arducopter` 重复。每个操作窗口45秒，无人响应就有界失败；不能在用户不在场时启动并等待其偶然出现。

## 实现与身份边界

- 新 `tools/validate_gcs_handoff.py` 复用现有TakeoverProbe的真实起飞、离home/非零yaw、撤销后的零旧位置输出、重复/旧epoch请求拒绝、一次新接管参考、后续任务与落地核验；只把原自动release-mode发送替换为人工等待，并在新接管前增加独立决定。其他撤销原因仍失败，输入失效不会被当作用户操作成功。
- `tools/run-gcs-handoff.sh` 在私有net/ipc/mount、tmpfs shm和固定domain77中运行正式runtime.run；配置使用当前已准入的parameter-*示例加独立遥测/GCS路径，不允许promotion-flight。前一轮正常GCS驱动路径保持原行为。
- Windows驱动新增 `--manual-handoff`，本模式保留桥直到任务结束，输出human-handoff阶段；旧默认模式仍为空中断桥后验证物理继续。Linux wrapper通过新建子进程的pidfd处理bash→unshare→Python的exec变化，SIGINT只作用于同一内核进程；既有默认路径继续完整PID/start_ticks/argv核验。真实本机pidfd检查已通过，原始记录在validation/gcs-handoff-20260909/pidfd-exec-check.log。
- 原模式报文必须来自已经验证的QGC MAVLink 255/190，真正成功通过桥返回，目标22（PX4）或241（AP）。使用原固定dialect解码SET_MODE或COMMAND_LONG/DO_SET_MODE，不发送报文。PX4对应AUTO_LOITER、AP对应BRAKE；最终仍须Windows桥与Observer全体成功反向报文计数/累计字节SHA一致，并有真实QGC载具识别日志。
- QGC Vehicle.cc:1472–1506、FirmwarePlugin.h:144和APMFirmwarePlugin.h:39表明本构建PX4使用SET_MODE，AP使用DO_SET_MODE(custom mode17)。支持其他形式的解码测试不代表本构建实际发出该形式。桥端口和INI继续按既有独占/关闭自动连接检查。

## 当前验证与未完成项

Windows真实预检通过：WksimGCS5.1.4.0，exe SHA134b9b6db4dec56d00707e406e5f8ff20ded25cfba8f5579e2447f1acbd6ace7；INI SHA364f8b1e192cd7780e8d46691901e3361c58d9edfda403bd72dfd77d3a0eee39；没有现有QGC/端口冲突。设置检查负例继续通过。记录validation/gcs-handoff-20260909/windows-preflight.json。

全量矩阵在新增4项阶段为462项（433通过/29跳过），旧预检11通过，日志validation/session-product-checks-GXIFLVKj/。之后新增原子决定CLI的一项测试，针对性WSL5项通过，Windows4通过/1个WSL dialect条件跳过。测试覆盖无人响应零替代发送、非模式原因不被吞掉、旧/错nonce/重复/完成后请求拒绝、真实SET_MODE/COMMAND_LONG字节的目标/模式/来源/成功转发检查以及原子完整JSON交付。首轮测试fixture误给只读state赋值的失败保留，修正为既有latest状态入口。

尚未验证候选真实双栈人工动作、完整桥时序与原始独立审计。旧GCS驱动8192个正向源包摘要上限仍在；达到上限会如实失败，不将缺失摘要当作全包验证。人机操作时间和机器墙钟回拨也可能使实验失败，失败不自动重新接管或恢复旧任务。用户答复在场之后才开始真实动作；本准备文档不关闭#42或#48。
