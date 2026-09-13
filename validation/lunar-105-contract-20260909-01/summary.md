# #105 最小范围收尾

2026-09-09。交付 `docs/plan/44-motor-efficiency-contract.md` 及本目录只读证据。当前结论：OPEN / needs-triage；未实施native效率事件、未启动模型/FC/ROS/UE、未执行飞行或冷重置。

## 实际结果

- `boundary.json`：只读检查退出0，固定ZIP/生成cpp哈希通过；实际质量配置加入 motor_efficiency 后被拒绝，错误为 `configuration fields, fixed mapping, units, source or identity differ`。导出接口只有create/destroy/step，没有效率写入读回。这是阻塞证据，不是效率验收PASS。
- `windows-tests.log`：现有质量配置6项unittest通过、0跳过，退出0。
- `wsl-tests.log`：同6项通过、0跳过，退出0。WSL启动伴随本机localhost代理提示，原始输出完整保留。
- 提交前默认 `git diff --cached --check` 将原始Windows CRLF输出报为行尾空白；WSL日志含启动提示的NUL字节，被Git视为二进制。为保留真实输出未转换这些日志。合同与检查脚本无空白错误；以 `core.whitespace=cr-at-eol` 检查CRLF记录。
- 当前PID协议SHA256仍为 `25d50ddbbd44e658a72123e6d524a5c5021b355367a99e46a898ec9b9cecadc0`。源身份逐项记录于boundary.json；未修改物理预算或生产源码。
- Codebase Memory原生index_status读到ready、50865节点/165157边；检索仅作导航。生成源码和实际模块已直接阅读，没有依赖新增代码的结构查询。

## 准确命令

工作目录 `C:/Users/PC/Documents/odid编译/wksim`，PowerShell：

```powershell
python -B validation/lunar-105-contract-20260909-01/check_boundary.py E:/rflysimtools/RflySimAPIs/4.RflySimModel/1.BasicExps/e0_MinModelTemp/MulticopterModel.zip > validation/lunar-105-contract-20260909-01/boundary.json
python -B -m unittest validation.test_quad_model_parameters -v *> validation/lunar-105-contract-20260909-01/windows-tests.log
wsl -d Ubuntu-22.04 -u root -- python3 -B -m unittest validation.test_quad_model_parameters -v *> validation/lunar-105-contract-20260909-01/wsl-tests.log
```

复跑应使用新证据输出名称，保留本轮日志。此次全部返回0；边界检查中的配置拒绝为真实现有API调用结果，未使用mock/native夹具。

## 解阻与交接

合同列出精确所有者和缺口：单旋翼T/M的native系数映射与读回、ODE4子阶段一致应用、独立候选加载器/配置及模型seed读回、逐1ms observer、任务发布撤销与隔离清理、可执行入口和独立整场审计器。这些必需文件超出#105现有写入范围。仅新增Python事件对象无法形成该物理路径，因此本次依用户授权交付精确合同，保留needs-triage。#106–#108仍不得启动。

候选固定motor0前右、气动系数multiplier=0.97、事件seed=0、start=origin+2000、duration=1000tick；模型seed仍须单独读回。未以PID四路输入缩放代替单旋翼气动效率。R1/RateUnmet及历史失败原结论保持。

采用ponytail最小实现原则：复用现有测试，仅新增标准库只读证据脚本，未引入未接入native的运行抽象。

## 设置与范围

主会话执行，无子代理。用户指定 `gpt-6-astra/low`；当前可见系统仅能确认GPT-6系列，工具未提供本会话精确模型ID/推理档元数据，故无法独立核验该组合，不将用户指定当成实测结果。

开工时AGENTS.md及推进指南已有改动，未编辑或暂存。仅提交本合同与本证据目录；不关闭#44或#105。
