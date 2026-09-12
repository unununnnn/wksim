# 当前 wrapper 独立冷重建与重置证据

2026-09-12，主会话在 Ubuntu-22.04 实际执行当前 wrapper 的独立生命周期验证。

入口为 `tools/validate_generated_e0_lifecycle.py`（执行 SHA256 `ec883644acce248921c9775451699ce2c149311d438b720e3e21c361571a2098`），输入 `validation/codegen-e0-build-current-wrapper-01/build-manifest.json`，输出新目录 `validation/codegen-e0-lifecycle-current-wrapper-01/`。运行前分别核验 Ubuntu-22.04 与 RflySim-20.04 无现存 native；冻结记录和主会话独立复核在 `validation/coordination/native-inputs-20260912/current-lifecycle-01.json`。

```bash
cd /mnt/c/Users/PC/Documents/odid编译/wksim
/usr/bin/python3 -B tools/validate_generated_e0_lifecycle.py \
  --manifest validation/codegen-e0-build-current-wrapper-01/build-manifest.json \
  --output validation/codegen-e0-lifecycle-current-wrapper-01
```

输出目录现已存在，以上是已执行命令，不得就地重跑覆盖。

结果 `audit.json` 为 pass（SHA256 `0b5d96c97fcba5120213a2143ca641375878140435bc681b58ea3fcef8c5ff29`）：原库和独立冷库各运行两个重新创建模型的周期，每周期 1000 步、1ms、120 维。四份原始记录 SHA256 均为 `0979200da666f80d679203f07c47effd5d7385d3a0ddb1fe2b30e1bbc70b7553`；48 万个输出值精确一致，时钟误差门保持 `1e-8s`。两个子进程正常退出，主会话独立确认 PGID 705、706 均为空。

当前 wrapper SHA256 为 `150ddf3bab66e9e59701791392f6d792a14346e0b75ecdfe94872095e72d0290`。原库 `/root/wksim-codegen-e0-build-current-wrapper-01/libwksim_e0.so` 与冷库 `/root/wksim-codegen-e0-cold-907225b3b06c/libwksim_e0.so` 均为 `528db3241baa43ef79166fbba74f6a4176aa2d82bf7c238bfe8f8db68267b328`。构建参数、依赖扫描和实际加载映射均已留存；没有 MATLAB 运行库依赖。43 项输入及历史文件哈希前后不变。

准入修复先完整读取并验证六源和原库，再创建快照、输出和冷构建目录；拒绝已有输出、源名/hash 错配、构建根符号链接和越界。负责人和独立审查均在 Ubuntu-22.04 root 下验证 52 项纯行为测试。测试顶部“host-agnostic”旧表述不适用当前实现，运行宿主边界以本记录及审查报告为准。保留 cold 目录用于复核构建来源，不执行审查中的删除建议。

外层 bash 在所有 native 验证及输入哈希后检查成功后，多出一个回车命令，返回 1；收据单独记录该包装错误。编译、两个 native 子进程、四周期审核和之后的哈希检查已经完成。没有因包装尾部错误重复运行。

这补齐当前 wrapper 的冷重建、独立运行、重置和终止证据；未覆盖新增 terrain/初始化接口的全部语义、MATLAB 数值对照、可选 DLL ABI、飞行或 G6。2026-09-12 实时 GitHub 核对 #24 CLOSED、#9 OPEN，#26 原依赖和全部原 AC 保持，不能据本结果关闭 #26 或 Full。历史 `26-closure-readiness-manifest.json` 不改写成当前场次。

## 主会话对 #26 证据映射的复核

本节是主会话复核记录，补足 DS-D 交付时仍标记缺失的 AC5；其报告保留为交付时快照。主会话核对 `G/source-manifest.json` 中 SLX/init 的具名来源与哈希、`generated-sources-manifest.json`、当前 build manifest 的 `generation_run_id=short-cycle-codegen-01` 及六源身份，并核对本次四周期原始结果。可编辑材料的直接来源是生成场的 source manifest，43 项生命周期冻结收据用于本次输入与历史不变性，不能替代 SLX/init 来源。

既有 `G/codegen-report.json` 的五项产品 test/checkout 均为 1、九阶段均为 ok，核对的是实际记录，不重复执行 MATLAB、不以文件存在代替许可检查。工具检出不推导厂商材料再分发许可。

AC1–AC4 的本地证据及 AC5 的命令、身份、结果、失败边界与主会话复核已完成到本记录所列范围。`R`、`L` 仓库证据目录不含 `.so`；原库与冷库仍保留在 Linux 本地，未发布厂商源码或二进制。#9 的正式依赖继续未满足，#26 仍不可关闭。G6、可选 DLL ABI 与新增环境反馈语义不在此结论内。
