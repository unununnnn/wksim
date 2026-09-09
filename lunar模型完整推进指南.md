# lunar 模型完整推进指南

本文件是 `wksim` 的执行交接入口，记录时间为2026-09-09。用户所称 **lunar** 对应当前官方名称 **GPT-5.6 Luna**，模型标识为 `gpt-5.6-luna`。[OpenAI 模型文档](https://developers.openai.com/api/docs/models/gpt-5.6-luna)。本指南不依赖模型专属API，也不要求更换现有工具链。

目标：Luna每次执行一个边界清楚的子票，完成实现或一次验证，保存真实证据并更新票据，再取下一票。原17张实施父票及Full要求仍在，拆票不降低验收门槛。未知原生设计、独立审计和硬件/资源决策已经单列，Luna不需要自行补猜。

## 1. 直接接手

在Codex界面选择 GPT-5.6 Luna，建议从 medium 推理档开始。本机CLI也可使用：

```powershell
Set-Location -LiteralPath 'C:\Users\PC\Documents\odid编译\wksim'
codex -m gpt-5.6-luna -c 'model_reasoning_effort="medium"' '先完整阅读 lunar模型完整推进指南.md。运行 tools/lunar_queue.py next，只执行返回的一个 Luna 子票；按原始证据判定，完成后更新子票并继续取下一票。遇到专家前置或真实失败，保留证据并按指南处理。'
```

这是启动新Luna主任务的示例，本次交接没有擅自切换当前任务模型。仓库现有AGENTS对子代理要求 `gpt-6-astra`；该规则没有被本指南改写。**Luna按单主任务执行即可，不派发子代理。** 需要Astra的条目交给相应专家任务，得到规定产物后再继续其后继子票。

开工先运行：

```powershell
Set-Location -LiteralPath 'C:\Users\PC\Documents\odid编译\wksim'
git status --short
git branch --show-current
git log -1 --oneline
python tools/lunar_queue.py next
```

完成条件：确认项目根是独立的 `wksim`，看到当前分支/改动，并取得一个 `status=ready`、`tier=luna` 的实际子票。若没有ready票，读取返回的阻塞清单；不要把父票或Astra票当作下一张Luna票。

## 2. 工作区和工具

| 用途 | 当前实际位置/方式 |
| --- | --- |
| Windows项目根 | `C:/Users/PC/Documents/odid编译/wksim` |
| WSL项目根 | `/mnt/c/Users/PC/Documents/odid编译/wksim` |
| GitHub仓库 | `unununnnn/wksim`，所有gh命令显式带仓库 |
| 当前工作分支 | `codex/independent-rgb-integration`；以开工时git读回为准 |
| Windows Python | `D:/date/miniconda/python.exe` |
| ROS/原生执行 | WSL `Ubuntu-22.04`、`/usr/bin/python3`，通过仓库已有隔离脚本 |
| ArUco专用Python | `work/dependencies/aruco-python/Scripts/python.exe` |
| UE引擎 | `E:/ue5.5/files/UE_5.5` |
| 已构建Hex UE候选 | `E:/ue5.5/build/wksim-native-hex-20260909-01/WksimVisual.uproject` |
| 原始证据 | 仓库 `validation/` 或各run指定的 `/root/wksim-*` 持久目录 |

先读 `AGENTS.md`、`CONTEXT.md` 和当前子票列出的输入文件。父目录是多项目工作区，Prometheus上游和兄弟项目不是随意改写的工作目录。

每次shell工具调用都显式设置工作目录为上述项目根。工具调用之间不要依赖上一段PowerShell变量或Set-Location仍然存在；进行中的票号/目录保存到下面的active文件，后续重新读取。

定位规则：已知文件直接读；查文字、配置、日志使用 `rg`；未知符号或调用关系先用Codebase Memory，再读实际源码。项目名为 `wksim-prometheus`。MCP不可用时用已记录的原生入口：

```powershell
$env:CBM_CACHE_DIR = 'C:/CBMData'
$env:CBM_RUNTIME_DIR = 'C:/CBMRuntime'
& 'C:/Users/PC/.local/bin/codebase-memory-mcp.exe' cli index_status --project wksim-prometheus
```

后续查询格式见 `docs/codebase-memory.md`。图是导航，真实文件才是修改依据。无需为改报告或运行已知脚本重建全库索引。

## 3. 当前状态：哪些已完成，哪些只是候选

以GitHub实时状态、选中子票和最新报告为准。`docs/plan/README.md` 后部含历史叙述，不能拿历史“仍开放”覆盖最近已关闭状态。

| 范围 | 交接时状态 |
| --- | --- |
| #23 | 数值对照交付已关闭；R1仍 `numerical_failed`，不代表G6精度通过 |
| #24 | 质量保存/导入/实际静态响应已关闭 |
| #34 | 两栈姿态/推力、恢复、原始审计已关闭；默认位置/速度profile未替换 |
| #25 Hex模型 | 六路原生静态18项通过，原始补证保存完整；模板参数不是实机标定 |
| #25 Hex PX4 | 第三轮完成77项参数读回、任务和落地，状态 `observed`，独立整场审计待做 |
| #25 Hex AP/冷重置/实时UE | 尚待相应子票；没有用静态UE夹具冒充实飞显示 |
| Hex UE | 候选编译通过；真实UE静态夹具153 ACK、11拒绝及停帧检查通过；未提升默认manifest |
| #35 PID库 | 1,884次原C++、18,840值对照通过；12项纯检查通过 |
| #35 PID运行候选 | 14项纯检查通过；真实preflight、两栈飞行和独立审计尚未执行 |
| #40 ArUco | 消费端12项离线检查通过；真实相机跟踪闭环待做 |
| #45 GNSS | 事件纯逻辑10项通过；真实PX4/AP注入与恢复待做 |
| #20/#33 | 仍有真实倍率阻塞；不要盲重试或放宽合同 |
| Full/#1/#10/#9余项 | 仍开放；初期集成通过不覆盖Full的全部能力 |

详细证据和失败原因：[本轮收尾报告](docs/2026-09-09-hex-round-handoff.md)。最近通用WSL矩阵为667项：626通过、41跳过；旧预检11通过。41跳过含29项既有条件及12项可选视觉依赖；ArUco私有环境另跑12项全部通过。后来增加的队列6项测试独立通过，不混入667计数。

## 4. 任务来源和选择规则

三个文件共同提供完整任务定义：

- `docs/plan/lunar-backlog.json`：72个稳定键、写入范围、输入、步骤、完成条件和逻辑依赖。
- `docs/plan/lunar-issued.json`：稳定键到真实GitHub编号、父子关系和原生阻塞边的映射。
- `docs/plan/lunar任务索引.md`：全部任务的人类可读索引与链接。

GitHub父子关系和依赖也会实际写入并读回。原父票AC和原Blocked by保持原文；源码/纯检查子票只保留自身真实前置，因此可以先于无关的整场性能验收推进。**父票最终关闭仍检查原AC、原依赖和所有必要证明。**

```powershell
python tools/lunar_queue.py list
python tools/lunar_queue.py next
python tools/lunar_queue.py inspect 35-preflight
```

`next` 每次读取GitHub当前状态、triage标签及候选票的原生依赖，不把本地缓存当运行授权。它只选Luna票；Astra和decision不会被自动降级派给Luna。

最初可进入的五个切片是：

| 稳定键 | 只做这一件事 |
| --- | --- |
| `35-preflight` | 一次PX4 PID只读准入 |
| `35-ap-preflight` | 一次AP PID只读准入 |
| `25-physics-core` | 两文件实现Hex逐毫秒输入/时钟基础审计 |
| `40-target-command` | 两文件实现新鲜ArUco目标到公共速度意图，不发ROS |
| `1-full-ledger` | 逐项整理Full原规格覆盖台账，不判完成 |

前两项是执行现有命令；中间两项是有明确定义的纯代码切片；最后一项是覆盖检查。队列若因后续进展给出其他票，以实时结果为准。

## 5. 每个子票的固定执行流程

1. **绑定任务。** 完整读取子票正文、输入报告和归属文件；保存选中编号/稳定键。完成条件是明确本票要交付什么、什么不属于本票。
2. **核对前置。** 确认原生依赖已关闭，预检/资源身份可得。新文件路径是本票要创建的文件，不误当成现有入口。专家前置承诺的脚本或命令尚未交付时，保持阻塞。
3. **执行最小改动或一次运行。** 源码只改本票归属文件。所有子票另共同允许写 `validation/lunar-active.json` 和全新的 `validation/lunar-<票号>-<唯一ID>/`，用于选择记录、证据、summary和handoff；这是下述统一交接流程的额外归属范围，与票据专用证据目录并列。运行使用新ID、新目录；纯实现票先完成针对性测试，不自行启动整场飞行。
4. **核对完成条件。** 对照原始结果字段、实际返回码、身份和不变阈值。一次受理、编译成功、`observed`、绿色LIVE或测试跳过都不是更高层验收。
5. **保存交接。** 写准确命令、源/配置hash、输出路径、测试结果、失败及尚未验证部分。完成条件是另一任务能直接重查本次证据。
6. **提交并更新本子票。** 阅读diff，检查范围，提交本票实际改动并推送当前分支，贴真实摘要。只有本子票完成条件满足才关闭；随后再运行队列。

源码超出归属、需要新ABI/新原生接口、需要改变物理预算或修改封存资源时，将具体diff/缺口交Astra。已授权的普通读取、可逆修改和既定检查不需要重复询问用户“是否继续”。

建议保存一次选择：

```powershell
$activePath = Join-Path (Get-Location) 'validation/lunar-active.json'
if (Test-Path -LiteralPath $activePath) {
    $old = Get-Content -LiteralPath $activePath -Raw | ConvertFrom-Json
    $oldState = gh issue view $old.number --repo unununnnn/wksim --json state,labels | ConvertFrom-Json
    if ($oldState.state -eq 'OPEN' -and 'ready-for-agent' -in $oldState.labels.name) {
        throw ('先继续已有任务 #' + $old.number + '，目录：' + $old.case_dir)
    }
    if ($oldState.state -eq 'OPEN' -and -not (Test-Path -LiteralPath (Join-Path $old.case_dir 'handoff.md'))) {
        throw '先为已标记阻塞的旧任务保存handoff.md'
    }
}
$selectionText = python tools/lunar_queue.py next
if ($LASTEXITCODE -ne 0) { throw '没有可执行的Luna票；读取队列的阻塞原因' }
$selection = $selectionText | ConvertFrom-Json
$ticket = [int]$selection.number
$stamp = [guid]::NewGuid().ToString('N')
$caseDir = Join-Path (Get-Location) ('validation/lunar-' + $ticket + '-' + $stamp)
New-Item -ItemType Directory -Path $caseDir | Out-Null
$selectionText | Set-Content -LiteralPath (Join-Path $caseDir 'selection.json') -Encoding utf8
@{number=$ticket;key=$selection.key;case_dir=$caseDir} | ConvertTo-Json | Set-Content -LiteralPath $activePath -Encoding utf8
gh issue view $ticket --repo unununnnn/wksim
```

## 6. 已有入口的准确运行方式

这些例子是可复制的命令形状。只有所选票要求且前置满足时才运行，不在接手时把所有命令全跑一遍。

### 6.1 PID 只读准入

PX4：

```powershell
$run = 'pid-px4-preflight-' + [guid]::NewGuid().ToString('N').Substring(0,12)
$log = Join-Path (Get-Location) ('validation/' + $run + '.log')
wsl -d Ubuntu-22.04 -u root -- bash tools/run-pid-flight.sh --stack px4 --run-id $run --config Simulator/wksim_runtime/pid-flight-v1.json --output-root ('/root/wksim-pid-flight-' + $run) --preflight > $log 2>&1
$code = $LASTEXITCODE
Get-Content -LiteralPath $log -Tail 40
if ($code -ne 0) { throw 'PID只读准入失败，保留本日志并交接具体错误' }
```

AP只读票独立运行：

```powershell
$run = 'pid-ap-preflight-' + [guid]::NewGuid().ToString('N').Substring(0,12)
$log = Join-Path (Get-Location) ('validation/' + $run + '.log')
wsl -d Ubuntu-22.04 -u root -- bash tools/run-pid-flight.sh --stack arducopter --run-id $run --config Simulator/wksim_runtime/pid-flight-v1.json --output-root ('/root/wksim-pid-flight-' + $run) --preflight > $log 2>&1
$code = $LASTEXITCODE
Get-Content -LiteralPath $log -Tail 40
if ($code -ne 0) { throw 'PID只读准入失败，保留本日志并交接具体错误' }
```

两票独立记录。通过必须核对 `ok=true`、实际安装/消息路径和未启动FC/model/ROS节点，而不是只看退出0。

PID合同SHA：`25d50ddbbd44e658a72123e6d524a5c5021b355367a99e46a898ec9b9cecadc0`。若不一致，先查真实文件和票据，不能把旧pin改成当前hash来消除错误。

### 6.2 一次 Hex 候选运行

仅相应运行票在独立审计器、配置和资源前置满足后使用：

```powershell
$run = 'hex-ap-' + [guid]::NewGuid().ToString('N').Substring(0,12)
$output = '/root/wksim-hex-flight-' + $run
$log = Join-Path (Get-Location) ('validation/' + $run + '.log')
wsl -d Ubuntu-22.04 -u root -- bash tools/run-hex-flight.sh --stack arducopter --run-id $run --output-root $output > $log 2>&1
$code = $LASTEXITCODE
Get-Content -LiteralPath $log -Tail 40
if ($code -ne 0) { throw '本次Hex运行失败；先保留原始结果，不重复试飞' }
```

冷重置票使用已结束且安全降落的父结果。现有可供后续PX4冷重建引用的路径是：

```powershell
$run = 'hex-px4-reset-' + [guid]::NewGuid().ToString('N').Substring(0,12)
$output = '/root/wksim-hex-flight-' + $run
wsl -d Ubuntu-22.04 -u root -- bash tools/run-hex-flight.sh --stack px4 --run-id $run --output-root $output --cold-reset-from /root/wksim-hex-flight-px4-03/hex-px4-03/result.json
```

该父结果当前仅 `observed`，所选新子票的独立审计前置仍须先完成。冷重置是从终态冷重建：同模型/配置、新run_id、新进程/参数目录、新control_epoch及模型tick0，不是原live会话热恢复。

### 6.3 单独的实际 UE 边界检查

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/check-hex-view.ps1 -Stage E:/ue5.5/build/wksim-native-hex-20260909-01
```

这个脚本拥有并关闭自己创建的UE进程，输入是合成夹具，结果不能替代真实飞行显示。实际飞行显示使用 `Simulator/ue55/hex_bridge.py`，须由子票给出绑定的真实raw路径、run_id、instance_id、model_identity、端口及新readback路径。先读 `docs/2026-09-09-hex-visual-contract.md`，不能把已结束的raw文件重新标成LIVE。

### 6.4 纯测试与整合回归

```powershell
python -m unittest validation.test_position_pid validation.test_pid_flight -v
python -m unittest validation.test_hex_physics validation.test_hex_flight -v
python -m unittest validation.test_hex_visual -v
work/dependencies/aruco-python/Scripts/python.exe -m unittest validation.test_aruco_consumer -v
wsl -d Ubuntu-22.04 -u root -- bash tools/check-session-product.sh
```

按改动选择其中有关的检查；源码或失败原因没有变化时，不反复重跑完整矩阵。Windows上的原生方言检查可能按平台跳过，应在WSL运行对应检查。ArUco专用执行必须看到12项真正通过、无跳过。

## 7. 证据层级和判定

| 看到的结果 | 可以说明什么 |
| --- | --- |
| 源码/静态检查 | 接口、参数或算法实现可审阅 |
| build exit 0 / codec PASS | 产物构建、编码路径可用 |
| preflight ok | 本次指定资源可准入，不等于飞行就绪 |
| command_accepted / native publish | 请求受理或报文发布，不等于物理动作完成 |
| observed / online_ok | 在线任务观察到候选流程，仍待原始独立审计 |
| 独立审计PASS | 在声明范围和不变门槛下证明对应数据链 |
| 截图/绿色LIVE | 真实渲染或最近收到数据；还须与真实run原始数据关联 |
| 父票关闭 | 原AC、依赖和必要证据都已复核；不自动关闭Full |

所有运行原件保持不变。新审计输出放在原case目录之外的新文件；修复审计误报时保留旧审计、具体错误样本和修正后结果。新的输入/配置修订在运行前冻结，不回写旧失败的输入或阈值。

## 8. 已知问题的处理表

| 现象 | 应采取的具体动作 |
| --- | --- |
| `rclpy` 导入失败 | 使用WSL `/usr/bin/python3`和已有wrapper；保留source后的PYTHONPATH，不能用Windows Python跑ROS |
| MAVLink PARAM_VALUE像29字节或整数呈极小float | 使用 `hex_task.wire_payload` 从原始帧提取；INT32按原载荷四字节解码，不能把极小float当0 |
| PX4零坐标被旧airframe覆盖 | 当前Hex合同仅在地面显式应用CA_ROTOR0/1_PX=0，再读回全部77项；不能改成epsilon或接受0.1515 |
| `RateUnmet` | 保留真实失败，按工程前置处理；原100ms和10s/60s预算、无追赶规则不变 |
| 当前repo Control与姿态候选不同 | 使用明确reviewed-patch准入器；它有独立before/after和完整安装证明，不能放宽通用检查 |
| `/tmp`文件后续消失 | 用持久 `/root/wksim-*` 构建目录，原始数值和metadata在同一调用内归档到validation；控制台摘要不是原件 |
| 正弦fixture跨平台末bit不同 | 使用已冻结 `validation/pid-source-20260909-protocol.json`，由SHA确认；不要在另一平台重新生成“相同”输入 |
| 可选状态字段有NaN | 原始CDR保留；报告用既有 `json_value/write_json` 明确非有限标记，必需物理/控制值仍拒绝非有限 |
| 视觉夹具显示LIVE | 读取manifest的scope及raw来源；静态夹具不算真实模型/FC飞行 |
| 子票没有现成运行命令 | 检查其类型：实现票应先创建入口；依赖运行手册的验证票应等待前置，不能猜CLI |

封存原生源、旧安装、厂商文件与旧证据都按只读处理。新构建使用新目录；清理只针对该run记录的PID/boot_id/starttime/完整argv/cwd。保持单壳路径核验，避免 `git reset --hard`、`git clean`、按进程名批量终止及全局WSL关停。

真实硬件、许可证和新数值合同属于专列决策边界；普通SITL、可逆源码修复和明确脚本验证已有项目授权。遇到具体缺失时写清哪份输入缺失，避免重复请求整个项目的确认。

## 9. 完成或失败后的更新

每个子票的summary至少包含：编号/稳定键、改动文件、精确命令、源/配置hash、实际测试数和skip、原始结果路径、逐项完成判定、失败/未验证范围、进程清理。使用实际值，不填“应该通过”。

成功时只暂存本票文件，先检查diff，再提交。若存在其他人的改动，保持它们原样。统一检查可使用：

```powershell
git -c core.whitespace=blank-at-eol,blank-at-eof,space-before-tab,cr-at-eol diff --check -- . ':(exclude)*.patch'
git diff --stat
```

统一diff补丁的空白上下文有语义，`.patch`应使用对应封存基线的 `git apply --check --whitespace=error`，不能为消除空白提示而改补丁字节。

将真实summary写入本票新目录后更新对应票据：

```powershell
$active = Get-Content -LiteralPath 'validation/lunar-active.json' -Raw | ConvertFrom-Json
$ticket = [int]$active.number
$summary = Join-Path $active.case_dir 'summary.md'
if (-not (Test-Path -LiteralPath $summary)) { throw '先写入真实验证摘要' }
gh issue comment $ticket --repo unununnnn/wksim --body-file $summary
```

仅所有本子票完成条件满足、必要检查通过时，才执行：

```powershell
$active = Get-Content -LiteralPath 'validation/lunar-active.json' -Raw | ConvertFrom-Json
$ticket = [int]$active.number
gh issue close $ticket --repo unununnnn/wksim --reason completed
gh issue view $ticket --repo unununnnn/wksim --json number,state,stateReason
```

未满足时保持OPEN，避免队列重复派发同一失败：

```powershell
$active = Get-Content -LiteralPath 'validation/lunar-active.json' -Raw | ConvertFrom-Json
$ticket = [int]$active.number
gh issue edit $ticket --repo unununnnn/wksim --remove-label ready-for-agent --add-label needs-triage
```

把具体失败交到对应Astra前置；修复并复核后再恢复ready-for-agent。Luna可以继续其他真正ready的子票。禁止用关闭失败票来解除后继运行阻塞。

## 10. 中断和换任务时的完整交接

在本票新目录写 `handoff.md`，包含当前Git HEAD/分支、已修改文件、最后成功步骤、准确失败、原始case路径、未完成的唯一下一步、是否仍有本票进程。停止时不要留下归属不明的运行进程；已经结束的case不重启为“恢复”。

新任务重新执行第1节的检查，读取原handoff及GitHub子票，再运行队列。源文件和当前脚本是可执行事实；文档里的旧路径失效时记录并回到资源构建前置，不能随意搜索另一个二进制替代。

项目完成的最终条件仍是：各原父票原AC成立、原依赖清除、Full覆盖台账无遗漏、G0–G6和适用资源/硬件边界有实际证明。#23交付关闭、#48初期集成关闭、或本指南的72个切片创建，都不等于Full已经完成。
