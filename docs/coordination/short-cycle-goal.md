# 当前 Goal 执行检查点

2026-09-12最新：正式get_goal返回active，createdAt **1789219780**。继续现有Full/G0–G6目标。最新调度以 [模块策略](module-delivery-policy-20260912.md) 和 [实际派发收据](../../validation/coordination/continuous-module-queue-20260912.json) 为准；旧恢复/六端队列仅供历史追溯，不直接用于续派。

## 此轮改变与活动任务

已对三个DeepSeek、OMP、codebuddy五个现有外部端实际续派。精确thread read优先于可能过时的thread list。每份任务包括实现或审查、行为验证及可独立的下一项；负责人自行完成内部测试。派发后running是当时状态，下一轮必须重新read。

- A：Linux private runner/manager_gc_candidate及其测试唯一写入者。主会话发现freeze成功后统计异常会丢失所有权、arm与prepare之间缺少状态复核，已完成修复交付，候选23项测试通过（代理结果，独立审查待收）。runner SHA fd0b7ee6dfb99be7a2d6f580555c6f9bfcddf721e25f68e97761d7f5670df246；GC模块 cbf7b0186131c08d4055aea1fcafdb8e7cca36d9acfcb19cdac87938d8786e66。已冻结实现并立即续派两份过时测试夹具修复，唯一写Linux validation/test_joint_rate_probe.py和test_joint_evidence.py。准确AP mixed诊断命令已补齐，之前带planner-release/ap-pv/占位符的命令无效。
- B：Windows新GC诊断比较器+测试及原分析文档；只读7bdfxkb基线。C1明确freeze-only，不disable/改threshold，不能称必要条件或保证节省。
- D：Windows既有validate_generated_e0_lifecycle.py+新行为测试；完整输入准入先于输出/cold目录及native副作用。主会话暂不同时执行/改它。
- OMP：Linux新test_gc_candidate_entry.py；main/parser行为测试，mock所有native；不改A文件。
- codebuddy：旧线程连续片段终态未形成执行审查，改用干净上下文98925ad6-4736-4dd2-8287-1132158e2b14，新报告codebuddy-c1-execution-review-20260912.md，必须检查Linux实际runner及稳定SHA。此前引用Windows joint_runtime的设计报告不是C1执行代码通过证明。

## 最新真实诊断与下一候选

原件Ubuntu-22.04：
`/root/wksim-release-acceptance-fe3/validation/joint-public-flight-7bdfxkb_`
run=joint-public-flight-7bdfxkb_，epoch=85df8c49b8f64de8ba794cff149696d1。

同原0.5/1ms/4tick/100ms、完整两段PV、async-model-evidence，两timing env=1，仅诊断。tick109776发生RateUnmet=100050657ns，wall269.503900622s；不是#83通过。source_unchanged=true，cleanup_errors=[]，独立确认10个所拥有PGID已空，两个async证据closed/complete。

核算163239+99717577+169841=100050657；creep=25703958 work-over+74013619 release excess。tick107572 gen2 GC CPU24329672ns完整嵌于manager PX4等待CPU24787151ns，证明该调用内发生manager GC，不能排他归因PX4睡眠或OS。

保留包 `validation/33-rate-profile/diagnostic-7bdfxkb/`；本轮13项压缩件/元数据SHA全部与manifest一致。完整raw仍在Linux，未改失败原件。

C1仅计时前collect+freeze，GC保持enabled及原threshold；全部native清理之后恢复自有freeze。实现修复已交付，独立审查/回归收口待收；不可立即当合格候选运行。完成后同7bdfxkb命令只追加flag，保留async/AP mixed/c2IXOr/message与两timing env，不带planner-release或PX4 override。随后按原合同另行正式验收，诊断不能晋升。

## 已验收历史，不重做

- 5ec3d38：审计/复现完整模块；真实一正四负通过，原件不变，Linux59项纯测试零skip。证据validation/39-planner-flight/module-delivery-20260912。
- f21fc3a：rate区间核算与相关16项通过；有latch精确闭合、无latch为null。
- b67ad43：current-wrapper-01冷构建/100步1ms通过；wrapper150ddf3b…/4070B，新库528db324…/87584B，40项输入历史不变；不代表reset/terrain/G6/#26完成。
- bomvjsmg真实release+双LAND保持成立，最差75.3217ms；未覆盖完整两段PV/EGO绕障，不重跑。

#83仍待完整验收；#26当前源码独立reset/cold生命周期待主会话新场；#9/Full其余原AC继续开放。晚到EGO起点语义未答，不改门。当前没有主会话存活native句柄，旧42177/49271等已终态。

主分支codex/independent-rgb-integration；Linux执行工作区/root/wksim-release-acceptance-fe3。保护其他任务大批未提交改动，严禁git add全树；主会话独占native并分别检查两WSL。全部原AC完成才完成Goal。
