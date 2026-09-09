# #118 范围核对与回归

基线 fd4d45d，分支 codex/independent-rgb-integration。#116/#117 实时读回 CLOSED；#118 只允许合同与证据目录。交付 47-global-run-contract.md 的具体接入缺口与文件预约。生产源码未改，不能声称接入完成。

准确命令（wksim 根）：

`wsl -d Ubuntu-22.04 -u root -- bash validation/47-global-flight/review-20260909-118/check.sh`

最终退出0，36项中35通过、1跳过。跳过项为 C++ oracle（本轮未传 --oracle）；不挪用 #117 既有 oracle 成绩充当本轮测试。真实 ROS 消息和记录型运输测试覆盖既有两栈映射、home/reset、重放和 ACK 身份；没有验证新全球接入。工具返回原文保存在 test-result.json，含 WSL 本机警告。

首次运行退出1：36项中33通过、2失败、1跳过。失败为 test_native_takeoff_alignment_before_command_stream 和 test_node_rejection_does_not_falsify_connection_or_resume，两者断言 /proc/self/ns/net 与 /proc/1/ns/net 不同，实际同为 net:[4026531840]。随后按已有 check-session-product.sh 加入网络/IPC/mount 隔离后通过；未修改测试断言或产品源码。

check.sh 使用既有三层 ROS 安装提供消息，PYTHONPATH 首项指向当前 checkout 控制源码；进程为有限测试调用，已退出。测试在私有命名空间创建并销毁测试节点；没有启动 FC、物理模型或飞行。

未满足：原生适配接入、datum 实证、运行器、独立审计、两栈全球飞行。下一步为主任务将合同列明的源码文件纳入 #118 允许范围并确认所有权，再实现和验收。现有 AGENTS.md、推进指南改动不纳入提交。

请求设置 gpt-6-astra/low；当前接口不能独立核验实际模型 ID/推理档，本次无子代理。
