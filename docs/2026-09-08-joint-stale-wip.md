# #21 真实单机断流同步标陈接缝（待集中实跑）

依照五项批准记录中 #21 选项 (a)，增加真实单侧 FC 输入停流验收。当前仅完成驱动与反例检查，**未运行 UE/SITL，不构成真实验收通过，也不关闭 #21**。

`tools/validate_joint_stale.py` 复用 `validate_joint_visual.run` 的正式服务、真实双栈起飞、View、清理及原始运行封存。唯一新增分支在双机升空后，核对 children.json 与 Linux PID/PGID/start_ticks/executable 后向一侧 FC 发 SIGSTOP，并读回内核 T 状态。等待该侧 InputTimeout 后，在相隔 1 秒的两次观察中要求：

- 真实权威时间不再前进，双模型原始 truth 尾行等于权威提交步且不变。
- 向 UE 发送只读 joint_actor_query；响应身份、请求号、代次一致，两个实际 Actor 均 visible=true、stale=true、同一显示步。
- 每个 Actor 的位置/姿态与其显示步的原始对应栈 truth 一致，容差沿用既有 ACTOR_LIMITS；旋翼角度在两次查询间保持不变。

查询由 depth_slice 在 GameMode 中提供：不 ApplyPacket，不刷新 SourceWall/ReceivedWall，不发送伪造显示数据。普通产品桥只封存每 sequence 首个 ACK，不能证明停流后的 UE 标陈，故此处直接保存只读查询原文。查询不含 RPM，RPM 仅由断流前正常 ACK 覆盖，不宣称新增停流 RPM 独立读回。显示步允许早于最终权威步（显示为 50ms 节流通道），必须精确对应真实已提交物理样本，不能把显示步冒称最终权威步。

测试结束对同一 PID/start_ticks 发 SIGCONT，仅为允许正常清理；不提交 recover、不声称飞行完成；正式 stop 后要求 manager=0、result=stopped、所有记录进程组为空。失败目录保留，不重用输出目录。

## 主代理集中运行

前提：合并并重新构建含 joint_actor_query 的 GameMode；使用与当前所有 UE 构建输入逐哈希一致的新 manifest。旧 a61e137 构建不支持查询，不能用于此验收。Windows UE 19060 空闲，WSL Ubuntu-22.04 项目独立双 FC/ROS 构建已就绪；主代理独占 UE/SITL 资源。

```powershell
D:/date/miniconda/python.exe -X utf8 -B -m unittest tools.test_validate_joint_stale -v
D:/date/miniconda/python.exe -X utf8 -B tools/validate_joint_stale.py --manifest <新构建candidate-manifest.json> --output validation/joint-stale-20260908/arducopter-run1 --target arducopter-fc
D:/date/miniconda/python.exe -X utf8 -B tools/validate_joint_stale.py --manifest <新构建candidate-manifest.json> --output validation/joint-stale-20260908/px4-run1 --target px4-fc
```

本地一个针对性审计测试通过：真实旧证据的数值用于测试夹具，独立修改 stale/epoch/位置/步号均拒绝；该夹具不是本轮真实断流证据。CLI --help 已通过。tools 按 Codebase Memory 覆盖规则排除，采用已知文件直接读取，无结构图查询或索引刷新。

子代理实际模型核验：`C:/Users/PC/.codex/sessions/2026/09/08/rollout-2026-09-08T13-52-58-01a07f5c-b7f5-7351-b540-9b4ea0d73670.jsonl`，session agent_path=/root/joint_stale_seam，turn_context model=gpt-6-astra、effort=low；无嵌套。
