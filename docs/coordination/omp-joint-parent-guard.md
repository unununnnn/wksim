# OMP 联合任务 DirectParentGuard（内核亲子关系活性检查）

日期：2026-09-11。仅新增 `Simulator/wksim_runtime/joint_parent.py`、
`validation/test_joint_parent.py` 与本文；joint_task.py 接入由主会话负责，未改。
无新依赖、无通用进程框架；未 commit/push；未嵌套。

## 实现

`DirectParentGuard(expected)`（Linux 限定，非 Linux 构造即 OSError）：

- 构造：`os.getppid()==expected['pid']` → 真实 `json_identity` 复核
  pid/pgid/start_ticks → 再复核 getppid（闭合启动竞态：两次检查间父退出会重归属）。
  expected 字段严格校验（拒绝 bool/非法/缺失）。
- 每次调用：纯 `os.getppid()` 比较。父退出即重归属（init/subreaper），getppid
  必然变化；PID 复用不会重新成为旧父（getppid 在 fork 时设定，只会离开死父）。
  不缓存存活结果，不放宽任何频率/期限。
- 失败语义原文保留：`RuntimeError('Joint supervisor retired; no automatic task
  recovery')`。

替代收益：原 health 每个 pump 经 json_identity 读 /proc/<pid>/stat+cmdline 两次文件
读取；新检查每次为单系统调用。

## 测试（实际结果）

- WSL（真实内核行为）：`python3 -B -m unittest validation.test_joint_parent -v`
  → **9 ran，8 OK + 1 skip（Windows 专用用例），0.459s**。覆盖：真实父接受与
  100 次调用、初始身份错（pgid/start_ticks 篡改）、错误父 pid、启动竞态（getppid
  两次检查间变化）、重归属后调用失败、**真实短命父进程退出→孙进程 guard 以原文
  失败且自行退出无残留**（os.kill(pid,0) 仅探活，不按名杀）。
- Windows：9 ran，8 skip + 1 OK（非 Linux 构造拒绝）。
- 真实微基准（同一存活父，20000 样本/臂，证据 x 模式
  `validation/coordination/joint-parent-guard-benchmark-93fabf4a.json`，含原始样本
  与源码 SHA）：json_identity 中位 13,328ns vs getppid 187ns（约 71×）。
  **该数字不声称解决任何飞行/倍率问题。**

## 接入点（主会话）

`joint_task.run` 的 `health()`：以 `settings['parent']` 构造
`DirectParentGuard` 一次，health 改为调用 guard；失败语义不变。

主会话接入：joint_task.run 在创建Task前构造一次DirectParentGuard；每次health仍即时调用，不缓存、不调整任何期限。收紧pgid为正整数。真实子进程测试增加退场/回收等待，性能微基准改为WKSIM_PARENT_BENCHMARK=1显式运行，避免普通单测反复基准；既有13,328ns/187ns是原始单次json_identity/getppid测量，不是飞行收益。主会话相关48项WSL检查通过（3项条件跳过）。
