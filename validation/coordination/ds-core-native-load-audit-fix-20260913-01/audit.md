# #75 支撑门禁修复：核心原生加载面的最小 fail-closed 例外钉定

- 工作类别：`new-development / pure-Python policy regression fix`。**不是** #75 实跑复现、不是 ABI 批准、不是兼容性验收。
- 交付目录（本次独占写入）：`validation/coordination/ds-core-native-load-audit-fix-20260913-01/`
- 独占文件：`tools/audit_core_no_vendor_dll.py`、`validation/test_audit_core_no_vendor_dll.py`
- 机器可读审计输出：[audit.json](audit.json)（`status=pass`，`violations=[]`，exit 0）
- 本页、`audit.json`、`test-output.txt`、`regression-output.txt`、`hashes.txt`、`.gitattributes` 是本次唯一交付物；`.gitattributes` 内容为 `* -text`，冻结行尾，使记录哈希不因 CRLF 检出漂移。

---

## 1. 开工核验与实际 checkout

| 项 | 值 |
| --- | --- |
| 实际 cwd | `C:/Users/PC/Documents/odid编译/wksim` |
| 分支 | `main` |
| 派发时 HEAD | `0239f0e459bd8f5d7cdc6c25c0c6aa6687ead54f` |
| 交付时 HEAD | `33c2b06e8794ad865a25b307852d08d4c0845a26` |
| 工作期间对端提交 | `09105fa`（MIXED hook 与 DLL ABI 审计记录）、`33c2b06`（拒绝 MIXED 正式证据中的 perf 诊断） |
| 架构祖先检查 | `git merge-base --is-ancestor f333316e6efa6b299b4288a9d91fb2bccedfb9d6 HEAD` → 退出码 **0**（开工与交付各一次） |
| 引擎 | CPython 3.13.11（Windows），全部命令带 `-B` |

`git diff 0239f0e..HEAD` **未**触及 `tools/audit_core_no_vendor_dll.py`、`validation/test_audit_core_no_vendor_dll.py`、`Simulator/wksim_runtime/perf_capture.py`、`Simulator/wksim_runtime/netns_handoff.py`。两次 HEAD 变动后逐文件复核钉定输入哈希（见 [hashes.txt](hashes.txt)），漂移 **0**；`audit.json` 在 HEAD 变动前后逐字节一致。

已读：`AGENTS.md`、`CONTEXT.md`、`docs/architecture-implementation-20260912.md`、`docs/coordination/architecture-continuation-20260913.md`、`docs/coordination/module-delivery-policy-20260912.md`、`docs/plan/75-core-no-dll-audit.md`（#75 权威材料）、`validation/coordination/ds-dll-abi-evidence-20260913-01/audit.md`（相邻发现 A1：本门禁 RED）、`Simulator/wksim_runtime/perf_capture.py`、`Simulator/wksim_runtime/netns_handoff.py` 及两个被独占文件的既有实现与测试。

**未触碰**：`Simulator/**`（含两个 runtime 模块）、`validation/lunar-27-core-without-dll/run-ec40ec2-01/`（#75 冻结历史运行证据，只读）、共享账本（`validation/coordination/short-cycle-dispatches.json` 等）、`docs/**`、任何 Issue、任何其他 `validation/` 目录。

## 2. 症状与根因

派发 HEAD 上 `python -B -m unittest validation.test_audit_core_no_vendor_dll` 为 70 项 / 68 通过 / **2 失败** / 1 跳过。失败来自审计对两个**早已提交且工作树 clean** 的模块报出钉定单点之外的动态加载点：

```text
unexpected dynamic-load site: Simulator/wksim_runtime/netns_handoff.py:183 (ctypes.CDLL)
forbidden loader reference outside the pinned call (CDLL) at Simulator/wksim_runtime/netns_handoff.py:183
unexpected dynamic-load site: Simulator/wksim_runtime/perf_capture.py:51 (ctypes.CDLL)
forbidden loader reference outside the pinned call (CDLL) at Simulator/wksim_runtime/perf_capture.py:51
```

根因是**门禁规则过窄**（只承认 `model.py` 的调用方给径 CDLL），不是运行面回归：`perf_capture.py`（`ee9312a`）与 `netns_handoff.py`（`b941637`）是已接纳的诊断/交接模块。修复方向因此是把例外**精确钉定**，而不是放宽到"任意文件 / 任意 ctypes loader"。

## 3. 实现的最小 fail-closed 规则

### 3.1 保留原有钉定面（未放宽）

- `Simulator/wksim_core/model.py` 的形态仍必须精确为 `ctypes.CDLL(str(Path(library).resolve()))`，位于 `Model.__init__(..., library)` 内；允许计数仍硬锁为**恰好 1**，消息文本与判据均未改。
- `ctypes` 模块逃逸、`__dict__`/`vars`/`attrgetter`/`getattr`/`__getattribute__` 反射、`importlib.machinery` 原生/无源加载器、`pythonapi`、动态 `eval/exec/compile`、游离二进制/字节码、厂商令牌、配置面、模型身份、审计根等规则**逐条未变**。
- 因此 model.py 的厂商/native 表面识别精度不变（原有全部 model 相关负例继续通过）。

### 3.2 只新增两张钉定条目（长度硬锁 2，禁止扩容）

`KNOWN_NATIVE_LOAD_SITES`（`EXPECTED_PINNED_NATIVE_LOAD_SITES = 2`）每条固定：**相对路径、1 基行号、该行 sha256、精确调用文本、宿主类（或 `None`）、宿主函数、形状 id、理由**。

| 形状 id | 文件:行 | 钉定调用 | 形状判据（全部必须成立） |
| --- | --- | --- | --- |
| `caller_path_sha256` | `Simulator/wksim_runtime/perf_capture.py:51` | `ctypes.CDLL(str(library), use_errno=True)` | 恰好 1 个位置参数 + 恰好 `use_errno=True`；参数为 `str(<name>)`；该 name 在**同一函数内**由 `Path(<函数参数>)` 得出（调用方给径，禁字面量）；存在 `is_absolute`、`is_file`、`.suffix` 与 `'.so'` 路径门；存在 `hashlib.sha256()`、`len(<sha 参数>) != 64`、`'0123456789abcdef'` 字符集门、`<digest>.hexdigest() != <sha 参数>` 摘要门，且以 `open` 读取同一路径 |
| `libc_setns` | `Simulator/wksim_runtime/netns_handoff.py:183` | `ctypes.CDLL(None, use_errno=True)` | 恰好 1 个位置参数 + 恰好 `use_errno=True`；位置参数必须是常量 `None`（当前进程映像，**不是路径**）；句柄必须绑定到局部名；模块级 `CLONE_NEWNET` 必须精确为 `0x40000000`；该函数内必须对该句柄 `setns` 安装 `argtypes`、以 `CLONE_NEWNET` 调用 `setns`，并经 `ctypes.get_errno` 读 errno |

### 3.3 漂移与借用一律失败（fail-closed）

以下任一情况都产生 violation 且该点**不获得例外**（随后仍被原有 6c/加载点规则二次拒绝）：

- 行内容被编辑、行被移动、文件被替换（行 sha256 + 精确调用文本双钉）；
- 同一钉定行上不是"恰好一个 loader 调用"；
- 宿主函数/宿主类漂移（例如把记录器加载挪到别的方法，或去掉类）；
- 形状漂移：缺 `use_errno`、缺路径门/SHA 门、`None` 变成路径、`CLONE_NEWNET` 常量或 `setns` 调用/argtypes/errno 读取被改；
- 形状 id 未知（新增显式分支，保守拒绝）；
- 钉定文件在核心包内缺失、被软链或被改名；
- 白名单计数不等于 2、出现重复文件或重复 file/line 条目；
- **其它文件**（相邻命名、子目录、核心包其它目录）出现同样调用——路径必须逐字符等于钉定路径；
- 钉定文件内出现**第二个** ctypes 加载点或 loader 赋值别名。

## 4. 测试与实跑证据

全部为纯 Python、离线、无 native/构建/ROS/飞控/模型/UE/MATLAB；测试仅使用临时目录 fixture，仓库内不产生文件（`-B`，无字节码）。

| 命令 | 结果 | 原始输出 |
| --- | --- | --- |
| `python -B -m unittest validation.test_audit_core_no_vendor_dll -v` | **91 项 / 全部 OK / 1 跳过 / exit 0**（派发时为 70 项、2 失败） | [test-output.txt](test-output.txt) |
| `python -B -m unittest validation.test_validate_legacy_abi_manifest validation.test_promotion_flight -v` | **30 项 / 全部 OK / 1 跳过 / exit 0**（相邻纯 Python 模块无连带回归） | [regression-output.txt](regression-output.txt) |
| `python -B tools/audit_core_no_vendor_dll.py` | `status=pass`、`violations=[]`、**exit 0** | [audit.json](audit.json) |

输出字节确定性：同命令连跑两次 `--output` 逐字节一致，且与 HEAD 变动前记录逐字节一致（`sort_keys`、无 NaN）。

新增 21 项测试（`PinnedNativeLoadSiteTests`），正例与反例：

- 正例：真实 fixture（含两个真实钉定模块）整体通过；钉定表本身冻结（路径/行/形状 id 精确集合，真实行 sha 与调用文本复核）；移除例外后真实仓库必须失败（证明例外正是让真实核心通过的那一条）。
- 反例（**借用/漂移**）：相邻文件（同目录改名、子目录、核心包其它目录）复制记录器/`setns` 正文；行漂移（两文件各一）；SHA 摘要门被抹除；路径门被抹除；宿主函数改名；参数变体（缺 `use_errno`、硬编码路径、`str('/tmp/x.so')`、`PyDLL`、`WinDLL`）；记录器文件内第二个加载点；两个文件内的 loader 赋值别名；`CLONE_NEWNET` 常量漂移；`setns` 第二参数漂移；libc 点参数变体（`'libc.so.6'`、`resolve()` 路径、缺 `use_errno`、`WinDLL`、不绑定句柄）；钉定文件缺失；白名单计数锁 2；重复文件条目；未知形状 id。

### 变异验证（证明反例非空转）

- 把形状校验器替换为恒真 → "抹除 SHA 门"的漂移变成 `pass`（即该负例确实由形状门拦住，而非其它规则）。
- 放开"路径必须逐字符等于钉定路径" → 相邻文件借用例变成 `pass`（即该负例确实由路径限制拦住）。

## 5. 兼容性说明（明确边界）

1. **报告契约不变**：`schema` 仍为 `wksim.core-no-vendor-dll.v1`；`non_claims` 仍为原有**三条固定文本**（未改一字，避免破坏下游对固定文本的断言）；不新增任何顶层字段；`status` 取值 `pass`/`failed` 不变。
2. **`claim` 文案已更新**（如实描述三个例外），`claim` 不属于被钉定的固定字段；除本测试模块外，全仓库无其它 Python 消费者读取该字段（已检索）。
3. **既有 violation 文案未改**：`expected exactly one allowed CDLL site, got N` 仍只统计 `model.py` 加载点，原断言与外部日志解析不受影响；本次只**新增** violation 文案（`pinned native load site ...`）。
4. **新增行为**：`perf_capture.py` 与 `netns_handoff.py` 成为钉定文件——删改它们即使功能等价也会使门禁 RED，需由归属方复核并重新钉定（这是 fail-closed 的预期代价）。
5. **已知文档缺口（不在本次写入范围）**：`docs/plan/75-core-no-dll-audit.md` 仍写"核心仅一处加载点"的旧不变量，本次未改该文件（非独占）。其归属方需在该页补记两条钉定例外；在补记前，该页与工具存在表述差异。
6. **#75 历史运行证据不变**：`validation/lunar-27-core-without-dll/run-ec40ec2-01/` 未读取为写入对象、未改写、未复用；本次是静态门禁修复，不构成对 #75 实跑结论的重新验收，也不使其失效。
7. **未改 runtime**：两个被承认例外的模块**逐字节未修改**（哈希见 [hashes.txt](hashes.txt)）；例外以"钉定其现状 + 约束其形状"的方式承认，不改变其运行语义。
8. **行尾**：本目录所有文件均为 LF（`.gitattributes` 为 `* -text`）。

## 6. 稳定 SHA 与交付范围

| 项 | 值 |
| --- | --- |
| 派发时 HEAD | `0239f0e459bd8f5d7cdc6c25c0c6aa6687ead54f` |
| 交付时 HEAD | `33c2b06e8794ad865a25b307852d08d4c0845a26` |
| `tools/audit_core_no_vendor_dll.py` SHA256 | `e773d69b2b61ea465b411ddd8e0977cfc96af6e2fee6a488628cd26d9c27c608` |
| `validation/test_audit_core_no_vendor_dll.py` SHA256 | `f02f862e6f4df9c3a2779affeae44be2173b94e73aa5ec070452e3d59863983e` |
| `audit.json` SHA256 | `de3b8dd998e439df6cc894ba146eb5488b254f18c9be77a87b555679a0cc128c` |
| `test-output.txt` SHA256 | `5079db2b8b2aa8ad5783e9b3a20546469dff69a6724ae16abe604224e12a6741` |
| `regression-output.txt` SHA256 | `9c13b126f2c82d4fc28e1bf62a006e15eeb6e91d19798d4b41958df1d4bf5f72` |
| `.gitattributes` SHA256 | `705fd4d6451a31d36b3df7de96f83f30ac976c9b4a6d1e51671d8e2f33e2d0da` |
| 本次写入 | 仅两个独占文件 + 本证据目录；**交付后停止写入** |
| 提交归属 | 主会话（本目录按 `.gitignore:53`（`/validation/*/`）被忽略，需 `git add -f`） |

## 7. 非声称

1. 这是静态审计修复，**不是** #75 的"新目录实跑一次"；`non_claims` 三条原文不变。
2. 不批准、不否定任何厂商 ABI；不改变 #9/#27/#73–#78 任何状态；未加载、执行、反编译任何库或模型。
3. 只证明"当前工作树的受支持静态语法与配置不引入钉定面之外的 native 加载点"，**不**证明运行期 `dlopen`、实际 ABI 调用、物理/倍率/飞行验收。
4. 未执行 native、构建、ROS、飞控、模型、UE、MATLAB；未操作任何后台进程或用户进程。
5. 审计工具不自带完整性证明：白名单自修改会被行哈希钉捕获，但"同时改工具与白名单"超出本门禁范围（与 #75 原页一致）。
6. 未修改 `Simulator/**`、共享账本、其它 `validation/` 目录、`docs/**` 或任何 Issue。
