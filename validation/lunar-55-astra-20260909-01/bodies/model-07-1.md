<!-- full-followup:model-07-1:from-55:v1 -->

来源审计 #55；验收归属 #1。执行层 Astra，核验实际 gpt-6-astra/low，不嵌套。

本票只交付「固定翼」有界工程定义；不以合同完成宣称功能、Full或G0–G6完成。

## 原始范围与缺口

稳定行 MODEL-07，来源 `docs/plan/full-scope-expansion.md:52`。读取 `docs/plan/full-remaining-ledger.json`、纠正映射 `docs/plan/full-followup-tickets.json` 及归属票当前正文/关闭证据。

固定翼、复合翼：未覆盖；当前证据与后续门槛：各自模型来源、控制栈/执行器、运动工况；不能强行要求由ArduCopter控制固定翼

当前缺口：各自模型来源、控制栈/执行器、运动工况；不能强行要求由ArduCopter控制固定翼

## 写入范围

- `docs/plan/full-contracts/model-07-1.md`（新文件）
- `docs/plan/full-contracts/model-07-1.json`（新文件）
- 全新 `validation/full-model-07-1-<unique-id>/` 的命令、原始只读观测、hash与summary。

## 操作与验收

1. 列出本行所有功能原子，逐个给固定来源/版本/hash或精确missing，不从名称猜契约。
2. 仅定义本行输入输出、单位/坐标、身份、权威时间、选择/配置→连接或导入→运行→停止→重连/重置→结果，以及拒绝/失败语义。锁定本模型构型、执行器映射、可编辑来源、适用控制栈和工况；样本名不代表可用资源。
3. 复用已有实施链；仅对未承接原子提出一次真实运行或1–4源码文件后继切片，给确切文件、已有命令/入口、输入输出schema、事前门槛、依赖及所有权。尚无源码/命令则交具体专家前置，不能编造可执行命令。
4. 交付JSON逐原子映射和Markdown合同，含known/unknown/blocked、证据、可复查验收与建议子票正文。后续实施票由主代理审阅合同后发布；本票不改其他票、既有阈值、默认配置或原厂资源。
5. 核验JSON可解析、原子无丢失/重复、每个gap有owner和后继；保存准确命令/退出码/hash及失败边界。只有合同交付齐全才关闭本票；缺资源明确blocked，不以规划替代运行。

只读定义可先执行，不要求验收父票关闭，避免父子环。设备/许可条件沿用#56，插件/环境未决合同沿用#9；数值预算须确认后才能运行。此票不发送硬件命令、不上传私有材料。R1 numerical_failed和#20/#33 RateUnmet不变。既有17父票、本合同均非Full完整实现。
