# 独立对抗性审查：`34d6076` 核心原生加载例外（纯 Python 静态面）

> 结论先行：**无 P0；发现 3 项 P1 与 3 项 P2。** 三项 P1 同属一个根因——
> `_perf_recorder_load_shape_ok` / `_libc_setns_load_shape_ok` 只校验“守卫/令牌**存在**”，
> 不建立守卫与加载之间的**控制流/数据流关联**，也不约束句柄的符号面。10 个对抗变异在
> 未改动既有源码的前提下（全部只改内存文本、写临时 fixture）全部得到 `status=pass`。
> 唯一对照项（追加第二个 `ctypes.CDLL`）被正确拒绝，说明审计并非整体失效，而是新增例外的
> 判定精度不足。

- 审查对象：`34d607698f90ea5a83901b511baaf4aee7bdd595`（“Pin accepted native load sites in core audit”），
  已确认是 HEAD 祖先。
- 范围：`tools/audit_core_no_vendor_dll.py`、`validation/test_audit_core_no_vendor_dll.py`，
  及其直接读取的当前 core 源（`Simulator/wksim_runtime/perf_capture.py`、
  `Simulator/wksim_runtime/netns_handoff.py`，含 `model.py` 既有钉定点与 `telemetry_dialect.py` 既有白名单的回归核对）。
- 未执行：native、构建、ROS、飞控、模型、UE、MATLAB；未加载任何 `.so`/`.dll`；未 spawn 进程。
  全部证据为纯 Python 读取 + AST 分析 + 临时目录写。
- 未修改任何既有文件；未 `git add/commit/push`。唯一写入目录为
  `validation/coordination/codebuddy-core-native-audit-review-20260913-01/`。

---

## 1. 开工/收工核验

| 项 | 值 |
| --- | --- |
| 实际 cwd | `C:/Users/PC/Documents/odid编译/wksim` |
| 开工时 HEAD | `1a8d5083b70461e6e6984566f7298c993f0c5392` |
| 收工时 HEAD | `287f8ec0e65c2e10b80b450904592f8349aed107`（并发仍在推进） |
| 期间并发提交 | `0a1caa1` “Make promotion catalog test self-contained”、`287f8ec` “Record independent MIXED perf reviews”（对端并发写入） |
| 并发影响 | `git diff 1a8d508..HEAD` 与 `0a1caa1..HEAD` 均未触及任何 in-scope 文件；in-scope SHA256 前后一致（见 §7）；结论不受影响 |
| `34d6076` 祖先 | `git merge-base --is-ancestor 34d6076 HEAD` → 退出码 0 |
| `f333316` 架构祖先 | `git merge-base --is-ancestor f333316… HEAD` → 退出码 0 |
| 引擎 | CPython 3.13.11（Windows/Anaconda），全部命令带 `-B` |
| 基线测试 | `python -B -m pytest validation/test_audit_core_no_vendor_dll.py -q` → `90 passed, 1 skipped, 117 subtests passed` |
| 真仓审计 | `python -B tools/audit_core_no_vendor_dll.py` → exit 0，`status=pass`，`violations=[]`（`0a1caa1` 上复跑） |

in-scope 文件 SHA256（工作树，`0a1caa1`）：

```text
e773d69b2b61ea465b411ddd8e0977cfc96af6e2fee6a488628cd26d9c27c608  tools/audit_core_no_vendor_dll.py
f02f862e6f4df9c3a2779affeae44be2173b94e73aa5ec070452e3d59863983e  validation/test_audit_core_no_vendor_dll.py
c196616fe8324eed2d8b294ef52aaec1f982eb5330abbeb7ee17094399f32e0f  Simulator/wksim_runtime/perf_capture.py
3cfea24602fb6c703898be4bac6e81f71a38a0175260b08d2bad58ba9b973575  Simulator/wksim_runtime/netns_handoff.py
1ca31d2a5435fe5d924b8397194743df9b017618a05d0d4b0f10a89a5237ed0e  docs/plan/75-core-no-dll-audit.md
```

---

## 2. 方法与可复现证据

`repro_pinned_native_load.py` 复用测试文件同款 fixture 构造方式：把**真实**的
`perf_capture.py` / `netns_handoff.py` 文本写入临时目录（使钉定行号 51/183 与行哈希成立），
再对文本做定点行替换/插入，最后调用 `audit_mod.audit(fixture_root)`。
每条变异 = 一次真实审计运行。输出见 `repro_output.txt` / `repro_output.json`。

| 变异 | 预期 | 实测 | 判定 |
| --- | --- | --- | --- |
| baseline 未改动 | pass | pass | 对照 |
| `perf_capture.py:39` → `… != library_sha256 and False:` | 应 fail | **pass** | 假阴性 (P1-1) |
| `perf_capture.py:40` → `pass`（保留 39 的比较） | 应 fail | **pass** | 假阴性 (P1-1) |
| `perf_capture.py:30` → `(…) and False:` | 应 fail | **pass** | 假阴性 (P1-1) |
| `perf_capture.py:33` → `…)) and False:` | 应 fail | **pass** | 假阴性 (P1-1) |
| 重排：加载保持在 51 行、摘要门整体移到 52–57 行 | 应 fail | **pass** | 假阴性 (P1-1) |
| `perf_capture.py:38` → `digest.update(b'')` | 应 fail | **pass** | 假阴性 (P1-2) |
| `perf_capture.py:36` → `with (library.open('rb'), Path('/etc/hostname').open('rb'))[1] as stream:` | 应 fail | **pass** | 假阴性 (P1-2) |
| `netns_handoff.py:186` 插入 `libc.system(b'id')` | 应 fail | **pass** | 假阴性 (P1-3) |
| `netns_handoff.py:186` 插入 `libc.open(b'/etc/passwd', 0)` | 应 fail | **pass** | 假阴性 (P1-3) |
| `netns_handoff.py:186` 插入 `libc.dlopen(b'/tmp/x.so', 2)` | 应 fail | **pass** | 假阴性 (P1-3，且是真实 loader) |
| 对照：追加 `def extra(): return ctypes.CDLL('vendor/x.so')` | fail | fail | 审计整体仍有效 |

复现命令：

```text
python -B validation/coordination/codebuddy-core-native-audit-review-20260913-01/repro_pinned_native_load.py
```

---

## 3. P1 发现

### P1-1 `caller_path_sha256` 只查守卫“存在”，不查“生效”与“先于加载”

- 位置：`tools/audit_core_no_vendor_dll.py:324-388`（`_perf_recorder_load_shape_ok`），
  核心是 `347-387` 的存在性标志循环与 `388` 的 `all(...)`；
  被证伪的声明在 `11-19`（模块 docstring）与 `1952-1957`（`claim` 字符串）。
- 机制：该函数 `ast.walk(function)` 后只要求下列令牌**在函数内出现过**：
  `Path(<参数>)`（347-357）、`library.open`（358-361）、`is_absolute/is_file/suffix`（362-364）、
  `'.so'`（365-366）、`'0123456789abcdef'`（367-368）、`hashlib.sha256()`（369-372）、
  `len(<参数>) == 64` 与 `<digest>.hexdigest() != <参数>`（373-387）。
  它**不检查**：守卫是否被求值、失败分支是否抛异常/阻断、守卫是否在加载**之前**。
- 可复现用例（均 `status=pass`）：
  1. `perf_capture.py:39` → `if digest.hexdigest() != library_sha256 and False:`
     （`Compare` 仍在，`and False` 令其恒假，摘要门永不触发）；
  2. `perf_capture.py:40` → `pass`（第 39 行比较保留，仅移除 `raise`）；
  3. `perf_capture.py:30` → `(…) and False:`（路径门恒假）；
  4. `perf_capture.py:33` → `…)) and False:`（长度+字符集门恒假）；
  5. 重排：把第 51 行 `self._library = ctypes.CDLL(str(library), use_errno=True)`
     原样留在第 51 行，摘要计算/比较整体下移到 52-57 行。
- 影响：审计对被钉模块给出 `status=pass` 且 `violations=[]`，实际语义是
  **未经验证的 `.so` 已被 `dlopen`（ELF 初始化器先执行）**，或 SHA 门形同虚设。
  这与 `claim`/docstring/证据文档 §3.2、§3.3（“缺路径门/SHA 门…被改即失败”）直接矛盾。
- 最小修复建议：把“存在性”改为“控制流支配 + 生效”：
  1. 摘要门必须是某个 `ast.If` 的**直接 `test`**（拒绝 `BoolOp` 包裹，从而排除 `and False`），
     且该 `If` 的 `body` 必须含 `ast.Raise`（从而排除 `pass`）；
  2. 路径门（`is_absolute/suffix/is_file` 那个 `If`）同样要求 `body` 含 `Raise`；
  3. 要求上述两个 `If` 在函数体中的词法位置**先于**被钉加载语句；无法线性比较时 fail closed。

### P1-2 摘要与被加载文件之间无数据流绑定

- 位置：`tools/audit_core_no_vendor_dll.py:324-388`，具体是
  `opens_path`（358-361）、`sha256_constructor`（369-372）、`digest_gate`（373-380）。
- 机制：`opens_path` 仅要求“函数内存在 `library.open(...)` 调用”，不要求
  **被 `digest.update` 消费的字节**来自该 `open`；`digest_gate` 仅要求
  `hexdigest()` 与某个函数参数出现在 `NotEq` 比较中，不要求 `digest` 由该路径的内容喂入。
  文档 §3.2 声称“且以 `open` 读取同一路径”，代码未实现该绑定。
- 可复现用例（均 `status=pass`）：
  1. `perf_capture.py:38` → `digest.update(b'')`：摘要退化为空串哈希，
     第 36 行 `with library.open('rb')` 仍满足 `opens_path`，门仍“存在”；
  2. `perf_capture.py:36` → `with (library.open('rb'), Path('/etc/hostname').open('rb'))[1] as stream:`：
     真实被哈希的是**另一个文件**，而 `library.open('rb')` 作为诱饵满足 `opens_path`；
     随后仍以 `str(library)` 加载未验证目标。
- 影响：摘要门可被替换为对任意文件的哈希（甚至空输入），被加载字节完全不参与验证，
  审计仍 `pass`。
- 最小修复建议：要求 `with` 的 `context_expr` **恰为** `path_name.open(...)`（`Call`，
  拒绝 `Tuple`/`Subscript` 形态），并要求 `digest.update(...)` 位于该 `with` 体内、
  由对 `stream.read(...)` 的循环喂入；否则 fail。

### P1-3 被钉 libc 句柄是未受约束的原生符号面（可借道成为新 loader）

- 位置：`tools/audit_core_no_vendor_dll.py:391-444`（`_libc_setns_load_shape_ok`），
  根因辅助：`_abstract` 对 `ctypes.CDLL(...)` 返回**无标签**值 `935-936`；
  相关规则 `1665-1670`（rule 6c）与 `1791-1801`（load-site）。
  被证伪的声明：`114-119`（钉定理由 “used only for the Linux setns syscall”）、`14-16`（docstring）。
- 机制：`_libc_setns_load_shape_ok` 只证明“用到了 setns（安装 argtypes、以 `CLONE_NEWNET`
  调用、读 errno）”，**不证明“只用 setns”**。同时 `_abstract` 对被承认的
  `ctypes.CDLL(...)` 调用返回 `_StaticValue()`（无 `ctypes_loader`/`unknown_loader` 标签），
  因此绑定的 `libc` 不被 `is_loader_expr` 认作加载属主；`libc.<symbol>` 既不被 rule 6c
  也不被 load-site 规则识别。
- 可复现用例（在 `netns_handoff.py:186` 前插入一行，均 `status=pass`）：
  1. `libc.system(b'id')` —— 任意 libc 符号可达；
  2. `libc.open(b'/etc/passwd', 0)` —— 文件系统符号可达；
  3. `libc.dlopen(b'/tmp/x.so', 2)` —— **真实原生动态加载器**，同样漏检。
  （`ctypes.CDLL(None)` 暴露整个当前进程映像的符号表，`dlopen` 通常经 libc/libdl 可达。）
- 影响：审计声称“除钉定加载点外无原生面”，但一句插入即可经被钉句柄获得新的
  `dlopen`/`system`/`execve` 原生调用面，且 `status=pass`。这是本次提交**新引入**的可借道面
  （提交前 `netns_handoff.py:183` 本身会被拒绝，通过树中不存在该 libc 句柄）。
- 最小修复建议：在 `_libc_setns_load_shape_ok` 内遍历该函数（及模块）所有
  `ast.Attribute`，凡 `value` 为 `handle` 而 `attr ∉ {"setns"}` 即 fail（`setns.argtypes`/
  `restype` 属 `setns` 链，允许）。可选加固：把“被承认的钉定 CDLL 调用结果”绑定的名字
  标记为 `ctypes_loader`，对其任何非受审属性/`dlopen` 使用 fail closed。

---

## 4. P2 发现

### P2-1 回归测试未覆盖上述三类假阴性

- 位置：`validation/test_audit_core_no_vendor_dll.py`
  - `967-973` `test_recorder_sha_gate_removal_rejected`：把第 39 行整体替换为 `if False:`，
    只覆盖“比较表达式被**整体删除**”，不覆盖 `and False`（令牌保留、语义失效）；
  - `975-979` `test_recorder_path_gate_removal_rejected`：同理只覆盖整体删除；
  - `989-1004` 只覆盖调用形态变体；`1020-1053` 只覆盖 `CLONE_NEWNET` 常量、`setns` 参数、
    `None`/路径/loader 变体，均不涉及句柄的**其它符号**。
- 缺失用例：`and False` 令牌保留型弱化、`raise→pass`、守卫/加载顺序倒置、
  `digest.update(b'')` 与诱饵 `open`、`libc.system`/`libc.dlopen`。
- 最小修复建议：把 `repro_pinned_native_load.py` 的 10 条变异移植为
  `PinnedNativeLoadSiteTests` 的负例（每条断言 `status=="failed"`）。

### P2-2 权威工单文档与工具声明漂移

- 位置：`docs/plan/75-core-no-dll-audit.md:8` 仍写“动态库加载调用**恰好一处**”，
  而工具现已承认三处（model + perf_recorder + libc）；
  工具 docstring `11-19` 与 `claim`（`1952-1957`）、证据文档 §3.2 声称
  “after an exact … SHA256 gate”“以 `open` 读取同一路径”“only the Linux setns syscall”，
  均被 P1-1/P1-2/P1-3 证伪。
- 影响：文档/声明的证明边界大于代码实际证明力，属兼容性/可审计性漂移；
  本提交未同步更新 `docs/plan/75`。
- 最小修复建议：更新不变量 #1 的措辞为“1 + 2 处钉定加载点”，并把 `claim`/docstring 收窄为
  代码可证内容（或按 P1-1/2/3 收紧代码后再保留原措辞）。

### P2-3 绝对行钉定的脆弱性 与 哈希→按路径加载的 TOCTOU 说明

- `KNOWN_NATIVE_LOAD_SITES`（`107-120`）把行号 51/183 硬编码。对
  `perf_capture.py`/`netns_handoff.py` 的任何无关键改动（如新增一行 import）都会使钉定漂移并
  令审计失败——这是刻意的 fail-closed 取舍，但会在无关提交上产生噪声。**信息项，非缺陷。**
- `perf_capture.py:36-39` 对文件哈希后，第 51 行以 `str(library)` **按路径**再 `dlopen`；
  静态审计无法证明“被加载字节 == 被哈希字节”。该运行时性质超出静态审计的既定 non-claims，
  但 `claim` 措辞不应被读作“仅加载已验证字节”。**信息项，非缺陷。**

---

## 5. 兼容性评估

- `model.py` 路径判定逻辑未变：`1163-1166` 仅在非 model 文件改走
  `_pinned_native_load_ids`；`_model_allowed_loader_call_ids` 与“恰好一个允许 CDLL”
  的 `allowed_count==1`（`1806-1807`）保持原样；真仓审计在 `0a1caa1` 上 exit 0。
- 未发现对既有 loader 别名/反射/动态执行/厂商令牌/配置面/模型身份规则的放宽：
  对照变异（追加 `ctypes.CDLL`）仍被 rule 6c 与 load-site 双重拒绝。
- 无发现消费 `claim`/`schema` 的外部脚本被本提交破坏；仅 `docs/plan/75` 措辞滞后的文档漂移（P2-2）。

## 6. 已核对为“稳健”的既有机制（非发现）

- 钉定行 `sha256 + 精确调用文本 + 行号 + 宿主类/函数` 多重钉定：基线通过；
  行漂移/内容编辑用例失败（测试 `953-965`、`967-979`）。
- 白名单长度硬锁 2（`449-451`）、重复 file/line 拒绝（`452-457`）、未知 shape 拒绝（`506-509`）、
  钉定文件缺失拒绝（`459-461`）均 fail closed。
- 相邻/嵌套/复制文件无法借用任一例外（测试 `934-951`），与本次对照一致。
- `perf_capture.py` 追加第二个 `ctypes.CDLL` 被拒绝（测试 `1006-1013`，本次对照复现）。
- `telemetry_dialect.py:20` 动态执行白名单与 `model.py:15`/`joint_runtime.py:478` 厂商引用
  白名单未受本次提交影响。

## 7. 并发与隔离

- 会话期间对端先后提交 `0a1caa1`、`287f8ec`。核验：
  `git diff --stat 1a8d508..HEAD -- <in-scope files>` 与 `0a1caa1..HEAD` 均为空——
  `34d6076` 的审计行为与其输入在所有版本 HEAD 间未变（审计纯函数式读取工作树文件，
  且这些文件内容一致，in-scope SHA256 记录前后相同）。
- 本审查仅向 `validation/coordination/codebuddy-core-native-audit-review-20260913-01/` 写入；
  `git status --porcelain` 未显示任何既有文件被本会话改动。所有并发脏文件（`docs/**`、
  其它 `validation/**` 未跟踪文件等）保持原样。
- 该目录被 `.gitignore:53`（`/validation/*/`）忽略，故交付物不出现在 `git status`；
  未执行 `git add/commit/push`。

## 8. 交付物

| 文件 | 说明 |
| --- | --- |
| `review.md` | 本报告 |
| `review.json` | 机器可读发现清单与核验记录 |
| `repro_pinned_native_load.py` | 纯 Python 对抗复现脚本（10 变异 + 1 对照） |
| `repro_output.txt` / `repro_output.json` | 复现运行的人类可读/结构化输出 |
| `baseline_test_output.txt` | 基线测试输出（90 passed） |
| `real_repo_audit.json` / `.err` | 真仓审计 CLI 输出（exit 0） |
| `SHA256SUMS` | 上述交付物哈希 |
| `.gitattributes` | `* -text`（冻结行尾） |
