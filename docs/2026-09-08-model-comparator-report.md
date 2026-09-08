# #23 / G6 离线数值对照工具

2026-09-08。新增 `tools/compare_model_traces.py` 和合成单测。只读取显式合同 JSON 与两份 JSONL，结果写 stdout；不导入模型模块、不启动 MATLAB/Simulink/SITL/DLL、不修改输入、不调整预算。**pass 只表示这些数据满足所给预算，不表示用户批准、独立参考成立或 G6 验收完成。** 本次未执行真实模型对照，也未确定实际动力学预算。

## 完整输入格式

合同 `schema` 固定为 `model-trace-comparison-v1`。必填字段：

- `case`：非空工况名；`epoch`：非负整数。每次调用只处理一个工况和一个 epoch。
- `reference` / `candidate`：各含且仅含 `model_sha256`、`configuration_sha256`、`execution_sha256`，均为小写 64 位 SHA256。配置材料应绑定输入、初态、参数、种子和采样约定；执行材料应绑定执行引擎/编译器/库清单。工具核对记录身份，不验证这些外部材料的真实性或工程完整性。
- `samples`：非空 `{ "k": 0, "time": 0.0 }` 数组；k 从 0 连续增长，模型内 time 严格递增。时间与两侧记录作数值精确相等比较，无容差、插值、移行或相位猜测。
- `quantities`：逐轴条目，每项显式给 `name`、`reference_index`、`candidate_index`（零基扁平向量索引）、`unit`、`comparison`、`max_abs_error`。预算必须是有限非负数，不接受缺值、null、布尔值或字符串。没有隐式预算。允许显式零预算，但不自动写入或赋予其工程依据。

JSONL 每行包含 `contract_sha256`（合同原始文件字节 SHA256）、`case`、`epoch`、`identity`（对应一侧的三项身份）、`k`、`time`、`values` 与等长 `units` 数组。必须按合同顺序记录全部样本；所有值包括未选索引都必须为有限数值；每侧布局和单位保持不变。量名不能重复。JSON 重复键也拒绝。

合同是离线比较协议，不能替代 readiness 文档所要求的完整运行合同及审批证据。工具不接受或产生 `approved` 状态。

## 支持范围与输出

`absolute` 计算每轴绝对差；`euler_wrap` 只接受 `rad`，计算 ±π 包裹差。四元数比较明确不支持，待分量顺序、方向和归一化规则形成合同后另行实现。没有自动单位换算、相对误差、统计噪声假设或预算拟合。

输出包括三份原始输入 SHA256、pass/fail、逐量 max/RMS、逐量及全局首个超预算 k、全部超预算样本（含双方原值）、未验证索引。结构/身份/数值非法则 fail 并给 `error`，此时统计可能未生成，`first_failure_k=null` 不代表没有错误。绝对差浮点溢出也拒绝，避免输出非有限统计。CLI 通过返回 0，失败返回 1。错误报告不替代保存原始 JSONL。

## 可重复的人工例子

在仓库根目录 PowerShell 运行下列命令。它在系统临时目录写三份人工数据，并调用 CLI；例中预算仅为单测常数，不能移作模型验收预算。例子有 2 个样本，candidate 将 x/yaw 索引互换；x 误差 0.05 m，yaw 原始值跨 ±π 而包裹误差为 0.02 rad。

```powershell
python -m unittest discover -s tools -p test_compare_model_traces.py -v
@'
import pathlib, subprocess, sys, tempfile
sys.path.insert(0, 'tools')
from test_compare_model_traces import fixture, write_fixture
with tempfile.TemporaryDirectory(prefix='wksim-comparator-synthetic-') as d:
    paths = write_fixture(d, *fixture())
    command = [sys.executable, 'tools/compare_model_traces.py',
               '--contract', str(paths[0]), '--reference', str(paths[1]),
               '--candidate', str(paths[2])]
    print(subprocess.list2cmdline(command), flush=True)
    raise SystemExit(subprocess.call(command))
'@ | python -
```

真实已获授权数据的调用格式：

```powershell
python tools/compare_model_traces.py --contract C:/evidence/contract.json --reference C:/evidence/reference.jsonl --candidate C:/evidence/candidate.jsonl
```

本次验证：4 个 unittest 方法全部通过，非法输入表含 18 个子例；另外验证重复 JSON 键、坏 JSON、全部失败保存、原始哈希和输入字节未改动。测试未触及真实仿真资源。#23/G6 仍需有依据且预先批准的预算、已核实的参考身份/采样相位和真实采集数据。
