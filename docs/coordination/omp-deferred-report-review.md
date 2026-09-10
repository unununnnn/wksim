# OMP 延迟任务报告复核（joint_runtime/joint_evidence ArUco 改动）

日期：2026-09-11。只读复核 + 离线负例；实现未改；无 ROS/仿真/构建；未重跑整库；
不 nested/commit/push。tracking-07/08 原判不变（08 最终 rate 故障仍 failed）。

## 结论

 paced 环路/退出分支/终态加载三段均无误把失败或未退出 worker 当完成的路径；
发现一个真实但低危的报告完整性缺口（不改判任何运行结果）。

## 逐路径核验（实读位置）

- **完成判定**：`joint_evidence.py:6-14` `task_group_completed` 要求两个 worker 且
  `poll()==0`；未退出（None）/非零退出一律 False；`defer_report_reads=True` 时才豁免
  报告读取。worker exit0 与 result.json 的写入顺序安全：joint_task 在 finally 写
  result（fsync）后才退出，poll()==0 必然晚于落盘，无竞态窗口。
- **任务退出分支**（joint_runtime.py:575-592）：aruco 任务退出不在速率期限上解析
  大报告；非零退出仍走 rate.close_segment('task_fault')+clock/lifecycle fault 路径，
  失败语义保留。
- **终态加载**（joint_runtime.py:754-765）：aruco 任务报告在 stop/清理后加载，
  `load_retired_task_report` 验证 run/epoch/stack 身份与 exit0→pass；exit0 但无报告
  → ValueError → `task_report_errors` + status failed；损坏 JSON
  （JSONDecodeError∈ValueError）同样收口。100ms 状态节流与最终失败路径未被绕过。
- **verify_tasks**（joint_evidence.py:36-40）：ARUCO_TASK 恒返回 None，
  flight_completed 不可由 worker 完成置位——08 类"单项过但整体 rate failed"
  的判别无改判风险。

## 发现（1 项真实缺口）

**joint_evidence.py:20 的不对称**：`returncode==0 and status!='pass'` 拒绝，但
`returncode!=0 and status=='pass'` 被接受。复现：worker 写完 pass 报告后被杀/
崩溃（exit≠0），终态加载把"失败进程的 pass 报告"原样纳入 result['tasks'] 而不记
task_report_errors。不能造成完成/飞行误判（完成判定要求 poll()==0，fault 路径已
锁存失败），但削弱了"exit0 对应 pass"的报告完整性。**建议主会话补
`returncode!=0 and status=='pass'` 拒绝**。复核测试
`test_failed_worker_with_pass_report_is_currently_accepted` 固定了当前行为，
修复后翻转该用例。

## 测试（实际命令与结果）

`python -B -m unittest validation.test_deferred_report_review -v`：
**Windows 10/10 OK；WSL 10/10 OK**。覆盖：未退出/失败 worker 永不完成、
deferred 仅用可信 exit0、非 deferred 仍要 pass 报告、单 worker 组不完成、
身份三字段逐项拒绝、exit0 非 pass 拒绝、pass+exit0 加载、已知缺口固定、
失败报告+非零退出加载、损坏 JSON 拒绝。

主会话已修复反向不一致：非零退出携带pass报告现在同样拒绝，测试已翻转为拒绝预期。修复后两组12项WSL检查通过。该修复不改变运行中完成条件或倍率规则。
