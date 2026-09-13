# OMP C2 readiness 微基准（2026-09-12，纯 Python）

产物：`validation/coordination/c2-readiness-microbench-20260912/`
（`microbench.py` 执行脚本、`result.json`、`block-new-pre.py`/
`block-new-inloop.py`/`block-old-inloop.py` 提取块快照）。

## 被测对象与提取方法

- 旧：Linux 实验区 git `7cb7e84` 的 runner（SHA `fd0b7ee6…`）；新：当前 runner
  （SHA `c208b1d07a9054458e13b3f7bf74c145cb8641ec495e46fc7df5b6fb1626e408`）。
- C2 差异：go/ready 的 Path 构造从每 tick 循环体内移到 while 前。
- 提取：`ast.parse` 两版源码，按 `MAX_TICKS` 定位循环；新版取 4 个 while 前
  Assign（`go_path_initial` 等，与循环同缩进且行号在前）+ 2 个循环内 If
  （`go_path_initial`/`pv_go_paths` 匹配）；旧版取 2 个循环内 If
  （`live/'go.json'`/`pv-go-{leg}` 匹配）。块**原样编译 exec**，未重写算法。

## 协议

tempdir 固定 `go.json`、`pv-go-1/2.json` 与两 stack 的 ready 文件（分支不触发
save/read，断言 save=0、json.loads=0）；workers 两 key 不变；`clock.tick`
0..19999 逐 tick 递增、pv=True。计数轮（不计时）与计时轮隔离；两臂同量热身
（各 2 遍 20000 tick）后**交替 new/old 各 5 次**、每次 20000 tick；样本全部
保留（失败不抹）。

## 结果（median，ns/tick；两臂含相同 exec 框架开销，只看差值）

| 臂 | wall/tick | thread CPU/tick |
|---|---:|---:|
| 旧（循环内构造） | 5179.5 | 5179.7 |
| 新（while 前构造） | 1270.2 | 1270.5 |
| **delta** | **−3909.3** | **−3909.3**（−75.5%） |

按 4-tick 组折算约 **−15.6µs/组**（readiness 代码本身）。FS 检查频率两臂
**逐字相同**：exists 各 30000 次（20000 go + 10000 pv 腿），is_file 各 0——
C2 减少的是 Path 构造频率，不是检查次数。

## 边界（不夸大）

- exec-per-tick 框架开销两臂相同，仅差值有意义；绝对值不代表 runner 实测 tick 成本。
- 单主机单进程、同量热身、冷/热不混推；仅一轮 5+5 交替，不外推。
- 只量化 readiness 路径构造在**相同 FS 调用频率**下的减少；
  **不宣称 PV/0.5×/100ms 通过**，不替代 C2 native 场。
- 微基准在 WSL Ubuntu-22.04 python3 运行，fixture 在 tmpfs tempdir。

主会话可据此收口并预约 C2 native；本包已终态，无后台任务。
