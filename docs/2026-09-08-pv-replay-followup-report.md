# AP 候选核验与 Full 离线回看跟进

从本地 `2c7a6b3`、干净工作区继续。此次交付候选准备和已批准 Full 日志工具的输入完整性修复；未改变固件默认配置、控制包或任何验收数值。#31 保持已关闭，#32/#33 与 Full 保持开放。

## 已交付

1. **可重复的 AP P+V 候选身份核验**：新增 `tools/verify_ap_pv_candidate.py`，要求交接提供的独立 manifest SHA256；只读校验预构建源码快照、固定基线、独立 Git 目录、补丁及准备脚本、固件和构建日志，拒绝清单重复键或非对象。实际候选 `/root/wksim-ap-pv-vn04950x` 的 24,593 个文件、22 个子仓库与准备快照一致；固件仍为 `7dfeb027e06712380f499611e2ba1bc809ed71f74ae477807ac5b2d51d62bb44`，固定源未变。输出明确 `production_admitted=false, flown=false`，没有接入准入器或生成默认放行入口。
2. **实际 C++ 函数体边界验证**：逐字提取候选 DDS handler、高度帧转换、Copter P+V 与 ready 函数体，使用真实 IDL 常量编译执行。65,536 个 mask 仅四个合法，帧/数值/速度溢出/ENU→NED/yaw/返回值传播与拒绝下游调用检查通过。依赖为显式 stub，不能代替真实 Location、Guided、DDS、fence 或 timeout 验证；详见[边界报告](2026-09-08-ap-pv-boundary-report.md)。
3. **离线回看完整性**：修复浮点溢出、重复 JSON 键覆盖身份、行身份被结果元数据覆盖，以及巨大整数和合成时间戳溢出。歧义身份报告 partial，原始载荷/原文保留；详见[回看报告](2026-09-08-replay-integrity-report.md)。真实 AP 的 20,144 条记录逐条与原始流字节及哈希一致，原有未知身份保持未知。

## 实际验证与证据

在 `wksim` 根目录执行：

```powershell
wsl -d Ubuntu-22.04 -u root -- python3 -B tools/test_verify_ap_pv_candidate.py -v
wsl -d Ubuntu-22.04 -u root -- python3 -B tools/verify_ap_pv_candidate.py /root/wksim-ap-pv-vn04950x/pv-build.json --sha256 e05e5c9d0b2b576d2cf1751b01557219d6da36998b22ded396ca33d7f5c4db62
wsl -d Ubuntu-22.04 -u root -- python3 tools/test_ap_pv_native_boundary.py
wsl -d Ubuntu-22.04 -u root -- bash tools/check-session-product.sh
git diff --check
```

- 候选验证器：4 项真实临时 Git 树测试通过，覆盖源码增加/篡改、基线/固件/日志/补丁/清单/准备器篡改，以及错误外部哈希、链接、重复键和非对象；不是模拟飞控。
- C++ 边界：g++ 11.4、`-Werror`、UBSan/float-cast-overflow 编译及执行退出 0。证据 `validation/ap-pv-boundary-ea28l5nf/evidence.json`。
- 完整矩阵：`validation/session-product-checks-ilmOXxgK/`，430 项中 **401 通过、29 跳过**；旧预检 **11 通过**。6 项回看检查已包含在矩阵内，不重复计数。
- 当前候选核验与4项测试日志：`validation/pv-replay-followup-20260908/ap-pv-current-verification.json`、`candidate-tests.log`。
- 真实回看产物已从临时目录按原 SHA256 归档至 `validation/pv-replay-followup-20260908/ap-replay.json`；主代理再次逐行比对真实输入，见同目录 `replay-archive-verification.json`。导出 SHA256 为 `0fe97bf363c36e45fb35dc5a5f1ffe03ed863f20b9cb95de065a1357c9a3e7ab`。
- `git diff --check` 通过。没有启动 SITL、UE、MATLAB 或硬件测试；上轮55个进程身份审计没有被冒充为本轮新增审计。

## 后续前沿

#33 仍依赖 #32，因此本轮保留为候选准备；完整 XYZ P+V 也不覆盖真正 XY 速度/Z 位置。后续仍须显式候选 profile、适配器接入、运行前冻结轨迹误差/驻留/恢复条件，以及真实原生转换、拒绝、超时和轨迹/停止恢复证据，不能仅凭本轮测试提升固件或关闭票据。

Full 故障 #44/#45 分别仍依赖 #24/#23；模型数值预算、参考噪声配置/来源链未闭合。#26 重新生成受本机 Simulink Coder 许可限制；#9 DLL 契约、真实硬件模式及未定义外部系统仍有各自前置条件。#42 的构建和双向包证据已完成，人工切模式动作仍留用户执行。1×、G2/G6 和 Full 的原门槛不变。

本轮三个子代理均通过实际 JSONL 的 `session_meta.agent_path` 与 `turn_context` 核验 `gpt-6-astra/low` 后执行，无嵌套或未经核验的恢复；只读前沿代理结束后另建并核验回看实施代理。产品改动仅 replay 及其测试，其余为工具和报告。未更新 GitHub、提交或推送，便于下一轮继续整合。
