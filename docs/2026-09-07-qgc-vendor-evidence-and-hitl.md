# 2026-09-07 #42 厂商证据核查与受控地面站 HITL 包

承接 `f2437eb`，分支 `codex/independent-rgb-integration`。本轮全部由主代理完成（本会话无 gpt-6-astra 可核验配置）。#42 保持 open；未启动任何地面站可执行文件，未改厂商安装/系统设置/产品代码。

## 证据核查（按 2026-09-06 研究指定的「立即下一步」执行）

| 来源 | 结果 |
| --- | --- |
| `E:/rflysimtools/HowToUse.pdf`（厂商官方使用文档，1.1MB 全文提取） | 仅工具链总览；确认 QGroundControl 为厂商随附地面站；**无**隔离启动/私有设置/自动连接抑制说明 |
| rflysim.com 官方文档站（web 检索 8 条） | 均为通用配置/使用文档；无 QGC 隔离/受限连接机制 |
| 厂商 exe 只读字符串扫描 | RflySim 定制痕迹（RflySimFirmwares.json/RflySim3DImg_）；两个 40-hex 嵌入值经 GitHub API 实查**非**上游 QGC 提交；无版本/来源对应证据 |
| `E:/rflysimtools/QGroundControl/` 目录 | 仅 exe/Qt5 运行库/configData（已证实为相机配置）；无文档/源码/隔离工具 |

**结论：厂商 exe 的来源对应与受控启动机制仍不存在，维持 2026-09-06 研究结论。**

## 新事实：本机存在完整 QGC 源码检出（`../qgroundcontrol/`）

- 现代源码快照（CMake≥3.25、Qt6、`src/Utilities/QGCCommandLineParser.cc`、`custom-example/` 定制机制、`build-android-*` 构建目录、`aqtinstall.log` 86KB），无 .git 元数据。版本以 `.github/build-config.json` 为准（本轮未逐一展开）。
- CLI 选项实读：`system-id/clear-settings/clear-cache/logging/log-output/simple-boot-test/fake-mobile/allow-multiple`；**无 `--settings-file`**（与既有 `qgc-local-launch.md` v5.1.4-2 结论一致），`clear-settings/clear-cache` 为破坏性清除而非私有配置。
- 因此「受控地面站」唯一可核验工程路径是 **QGC_CUSTOM_DIR 定制构建**：独立应用/组织身份（私有设置文件）、源码级关闭全部自动连接默认、单一回环 UDP 链路；不修改厂商安装，GPL/Apache 本地使用合规，构建环境（aqt Qt）已在本机。

## HITL（提交用户，不代为决定）

1. **范围决策**：是否授权按上述定制构建本机受控 QGC（预计构建 30–60 分钟；不触碰厂商 exe/安装/系统设置；构建源码哈希与选项入档）。
2. **验收分工**：GUI 输入自动化不可用（既有边界），QGC 界面内的「切走任务模式」动作需用户亲手执行；接收侧证据走 QGC 自身 LinkManager/Vehicle 日志与系统截图（PowerShell 只读截屏），遥测/交接/撤销/不抢回语义由实验驱动与审计核验。

## 本轮其他维护

Codebase Memory 原生 CLI 刷新成功（CBM_CACHE_DIR/CBM_RUNTIME_DIR 显式）：**50,515 节点 / 163,780 边，ready**，日志 `C:/CBMData/logs/wksim-prometheus-1788790869.log`（前快照 46,541/158,981）。部分解析仍为既有第三方头文件，非新缺口。

#42/#21/#20/1×/G2/Full 保持 open；未放宽任何阈值，未推送远端。
