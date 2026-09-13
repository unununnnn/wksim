<!-- full-followup:ops-10:from-55:v1 -->

来源审计 #55；验收归属 #1、#35、#36、#37、#38、#39、#40。执行层 Astra，核验实际 gpt-6-astra/low，不嵌套。

本票只交付「控制/任务/算法」有界工程定义；不以合同完成宣称功能、Full或G0–G6完成。

## 原始范围与缺口

稳定行 OPS-10，来源 `docs/plan/full-scope-expansion.md:78`。读取 `docs/plan/full-remaining-ledger.json`、纠正映射 `docs/plan/full-followup-tickets.json` 及归属票当前正文/关闭证据。

控制/任务/算法：RC其他模式、更多规划/感知demo、多机任务与队形、公开实验来源逐项映射；当前证据与后续门槛：PID/UDE/NE、单规划器与ArUco只是明确的首批路径，不能代表全部Prometheus算法

当前缺口：#32速度/yaw、#34姿态出口已验；PID有源对照/候选与preflight，UDE/NE、RC、规划/ArUco有现存链。其他公开算法/demo/多机队形的固定来源映射和单实验AC仍缺。

## 写入范围

- `docs/plan/full-contracts/ops-10.md`（新文件）
- `docs/plan/full-contracts/ops-10.json`（新文件）
- 全新 `validation/full-ops-10-<unique-id>/` 的命令、原始只读观测、hash与summary。

## 操作与验收

1. 列出本行所有功能原子，逐个给固定来源/版本/hash或精确missing，不从名称猜契约。
2. 仅定义本行输入输出、单位/坐标、身份、权威时间、选择/配置→连接或导入→运行→停止→重连/重置→结果，以及拒绝/失败语义。保留每项正常/异常操作；宽功能域只交付定义与拆分，本票不实现全域。
3. 复用已有实施链；仅对未承接原子提出一次真实运行或1–4源码文件后继切片，给确切文件、已有命令/入口、输入输出schema、事前门槛、依赖及所有权。尚无源码/命令则交具体专家前置，不能编造可执行命令。
4. 交付JSON逐原子映射和Markdown合同，含known/unknown/blocked、证据、可复查验收与建议子票正文。后续实施票由主代理审阅合同后发布；本票不改其他票、既有阈值、默认配置或原厂资源。
5. 核验JSON可解析、原子无丢失/重复、每个gap有owner和后继；保存准确命令/退出码/hash及失败边界。只有合同交付齐全才关闭本票；缺资源明确blocked，不以规划替代运行。

只读定义可先执行，不要求验收父票关闭，避免父子环。设备/许可条件沿用#56，插件/环境未决合同沿用#9；数值预算须确认后才能运行。此票不发送硬件命令、不上传私有材料。R1 numerical_failed和#20/#33 RateUnmet不变。既有17父票、本合同均非Full完整实现。
