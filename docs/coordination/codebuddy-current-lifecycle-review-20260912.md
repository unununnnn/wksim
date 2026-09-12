# 当前 E0 生命周期独立审查 — 2026-09-12

独立审查，非实现方（D 为唯一作者）。只读源码 + 纯 mock 测试；未编译、未加载 `.so`、未跑 MATLAB/ROS/native/SITL。
本轮**未做**完整 reset/cold 生命周期，故不声称通过。

## 1. 审核对象与冻结 SHA

- 路径（Windows 检出）：`tools/validate_generated_e0_lifecycle.py`、`validation/test_generated_e0_lifecycle_admission.py`
- git：HEAD `ad70633c80beb4fa41c54bf781d70c4a277d9679`；` M tools/validate_generated_e0_lifecycle.py`；`validation/test_generated_e0_lifecycle_admission.py` 未跟踪。
- 实际读到字节的 SHA256（首读与末尾重算一致，审核期间 D 未再改动）：

| 文件 | SHA256 | size | mtime(+09:00) |
|---|---|---|---|
| tools/validate_generated_e0_lifecycle.py | `ec883644acce248921c9775451699ce2c149311d438b720e3e21c361571a2098` | 14673 | 2026-09-12 22:51:35 |
| validation/test_generated_e0_lifecycle_admission.py | `8970c7ed4afeda5de0e6461f972b08c18d1f76f3148990352e7c0e0d90e4f3e3` | 33829 | 2026-09-12 22:53:14 |

末尾重算时间：`2026-09-12T13:58:56Z`。两 SHA 与首读完全相同 → 本报告无未审变化。若 D 之后再次改动，本报告仅覆盖上述字节。

## 2. 结论总览

| 检查项 | 结论 |
|---|---|
| 1 所有坏输入在任何目录/复制/native 前拒绝 | 通过（F1/F2 为异常类型缺口，仍先于副作用） |
| 2 snapshot 失败只清理自己目录 | 通过（F3：cold 目录未清理） |
| 3 manifest SHA 绑定读取时字节 | 通过 |
| 4 编译 argv / 120 维 / 4×1000/1ms / 1e-8 / 精确四周期比较未变 | 通过（O1：门为 assert） |
| 5 output/private snapshot 原件保护 | 通过 |

真实缺陷：F1、F2、F3、F4（均低/中危，非阻断，含具体触发与后果）。加固观察 O1–O3。

## 3. 检查项逐条

### 检查 1 — 坏输入在任何目录/复制/native 前拒绝（通过）

`run()` 的只读准入段（`validate_generated_e0_lifecycle.py:160-184`）严格先于首个副作用 `tempfile.mkdtemp`（L189）：
- output 为符号链接（L165）/ 已存在（含空目录、普通文件，L166）→ 拒绝；
- build manifest 缺失/符号链接/不可读（`read_regular` L37-43）、JSON 畸形/根非对象（`load_build_manifest` L46-53）→ 拒绝；
- 源集合缺失/多余（L73-75）、`wsl_staged_path` 非绝对 POSIX/含 NUL（L80-82）、文件名与键不符（L83-84）、父目录不唯一（L86-87）、根不在 `/root` 下或前缀不符（`resolve_build_root` L62-63）、根为符号链接（L58-59）、根非规范路径（L64-66）→ 拒绝；
- 六源缺失/符号链接/哈希不符（`read_verified_sources` L100-104）→ 拒绝；
- summary 缺失/符号链接/畸形、`library_sha256` 非 64 位、原库缺失/符号链接/哈希不符/大小不符（`check_library_identity` L118-138）、原库在校验后再读哈希不符（L175-177）→ 拒绝。

`mkdtemp` 一旦被 mock 成抛错，上述所有用例都在其之前失败；`OrderingTests`（test 文件 L398-570）逐项断言。**原生/编译/Popen 在整个准入段无调用**（首次 `subprocess.run` 在 L204，`mkdtemp` 与 `output.mkdir` 之后）。

### 检查 2 — snapshot 失败只清理自己目录（通过；见 F3）

`try`（L190）内任意 `BaseException` → `except BaseException: shutil.rmtree(snapshot,ignore_errors=True); raise`（L250-253）。只删除本次唯一的 `mkdtemp` 快照目录，不触碰 `output`、`/root` 原件、manifest、summary 或他人目录。测试 `test_failed_run_cleans_up_its_own_snapshot`（L474-497）以受控 `mkdtemp` 断言其创建的快照被删。

### 检查 3 — manifest SHA 绑定读取时字节（通过）

`load_build_manifest` 只读一次字节（`read_regular`），用**同一份 `data`** 解析并返回 `hashlib.sha256(data).hexdigest()`（L48-53）。该值即 `manifest_sha256`，被写入 `contract['build_manifest_sha256']`（L184）；快照副本另以该值校验（L191-193）。不存在“先 hash 路径后重读”的窗口。测试 `test_sha_is_bound_to_the_exact_bytes_that_were_read`（L243-251）证明改盘后旧 digest 不变。对比旧实现 `sha(build_manifest)`（diff 中 `-` 侧）——本轮由路径重读改为读取时字节，属收紧。

### 检查 4 — 冻结行为未被改变（通过；见 O1）

`git diff` 显示以下内容为**逐字移动**（`-`/`+` 文本相同），未被改写：
- 编译 argv（L201-202）：`g++ -std=c++17 -O2 -fno-fast-math -fPIC -shared -Wl,--no-undefined -I <cold> Exp1_MinModelTemp.cpp model.cpp -o <cold>/libwksim_e0.so`；
- probe 子进程 argv（L216）：`sys.executable -B <__file__> --probe <lib> --output <dir>`；
- 120 维：`len(values)==120`（L152）、`len(row['output'])==120`（L236）、`output_count=120`（L182）；
- 4×1000 / 1ms：`range(1,1001)`×2 reset×2 库（L148）、`dt_s=.001`（L179）、`ticks_per_cycle=1000`/`cycles=4`/`compared_values=4*1000*120`（L245）；
- 时钟 `1e-8`：`abs(row['output'][2]-tick/1000)<=1e-8`（L237）、`clock_absolute_error_s=1e-8`（L182）；
- 精确四周期比较：`assert all(rows==raw[0] for rows in raw[1:])`（L242，四周期全部 `==`）。

仅有的语义改动是 `build_manifest_sha256` 改用读取时字节、`original_summary['library_sha256']` 改为等值变量 `original_library_sha256`，均不改变门限。`FrozenContractTests`（test L578-730）对 argv 尾部、两路 probe、contract 数值与 4 周期比较计数逐项钉住。

### 检查 5 — output / private snapshot 原件保护（通过）

- output 已存在（含空目录、文件）一律拒绝（L166），失败分支不删除 output，故预置 output 永不被改。测试 `test_occupied_output_rejected_before_any_read_or_spawn`（L451-455）断言 `stale.json` 保留；`test_output_that_is_a_file_is_rejected`（L457-461）断言文件内容不变。
- 六个源与原库全程只读：`read_regular`/`sha`/`check_library_identity` 仅读；快照写入的是内存中已校验字节（L194-195），不写原件。
- private snapshot 成功保留（测试 `test_successful_run_keeps_exactly_one_private_snapshot` L725-730），失败仅删自身（检查 2）。

## 4. 真实缺陷（含触发与后果）

### F1 — manifest 缺少 `staged_sources` 时抛裸 KeyError，而非 AdmissionError

- 位置：`tools/validate_generated_e0_lifecycle.py:169` `sources=manifest['staged_sources']`。
- 触发输入：`--manifest` 指向内容为 `{}`（或任意合法 JSON 对象但不含 `staged_sources`）的文件。
- 后果：`load_build_manifest` 只校验“根是对象”（L52），随后 L169 直接 `KeyError` 冒泡，CLI 打印 traceback 而非准确的 `AdmissionError`；仍先于任何目录/复制/编译，故不违反检查 1 的副作用顺序，但违反“准确拒绝坏输入”。测试无此用例（`ManifestLoadTests` L221-262 未覆盖）。
- 建议：L169 改为 `sources=manifest.get('staged_sources')` 后交 `source_root`（其 L72 已能报 `staged_sources must be a JSON object`）。

### F2 — `library_size_bytes` 非整数抛裸 ValueError；缺键时大小门静默失效

- 位置：`tools/validate_generated_e0_lifecycle.py:135` `size=int(summary.get('library_size_bytes',library.stat().st_size))`。
- 触发输入（a）：summary.json 含 `"library_size_bytes":"abc"`（或 `null`）→ `int()` 抛 `ValueError`，非 AdmissionError。
- 触发输入（b）：summary.json **不含** `library_size_bytes` 键 → 默认值取当前 `stat().st_size`，`size!=stat` 恒为假，大小绑定成为空操作。
- 后果：非准确拒绝（a）；少一层大小绑定（b，哈希仍绑定，影响有限）。测试 fixture 总带该键（L105），故未覆盖。
- 建议：缺键即拒绝；非整数用 try/except 包为 AdmissionError。

### F3 — 失败时 `/root` 冷目录未清理（只清 snapshot）

- 位置：冷目录创建 `cold=Path('/root')/('wksim-codegen-e0-cold-'+uuid…); cold.mkdir(mode=0o700)`（L198）；清理仅 `shutil.rmtree(snapshot,…)`（L250-253）。
- 触发：冷构建返回非零（L206 `RuntimeError`）或此后任一断言/异常。
- 后果：每次失败在 `/root` 遗留 `wksim-codegen-e0-cold-<uuid>`（内含六源副本与可能的半成品库）。属“清理不足”而非“误删他人”——满足检查 2 的“只清理自己目录”，但与“清理自己的目录”在语义上不完整。成功路径同样保留 cold（`build.json` 记录 `cold_directory`，可能是有意留存证据，需 D 明确）。
- 建议：失败分支一并 `rmtree(cold)`（若 cold 已创建），或显式声明 cold 为留存证据。

### F4 — 测试 docstring 的“主机无关、不依赖 `/root`”声明与实现相反

- 位置：`validation/test_generated_e0_lifecycle_admission.py:1-19` 声明 “host-agnostic; it does not require Linux and does not depend on `/root`”；但 `_Fixture.__init__` 硬编码 `Path("/root")`（L83）并 `mkdir(parents=True)`（L84），`BuildRootResolutionTests`/`OrderingTests` 亦在 `/root` 下建目录。
- 后果：该套件**必须**在 Linux 且对 `/root` 可写（root）下运行。在当前 Windows 检出直接运行会失败：`resolve_build_root` 的 `resolved!=root`（L65）在 Windows 上恒真（`Path('/root')/x` 的 `resolve()` 返回 `C:\root\x`，实测 `canonical_eq=False`），所有有效根被误判 “non-canonical path”。
- 本轮实测：在 WSL Ubuntu-22.04（uid=0）对同一字节运行 → **52/52 OK**（0.661s）。Windows 宿主未运行（会创建 `C:\root`，且按上分析必失败）。
- 建议：修正 docstring 为“requires Linux root and `/root`”，或在 Windows 上改为可注入根（当前测试未做，属声明与实现不一致的文档缺陷）。

## 5. 加固观察（非阻断）

- **O1 门限依赖 `assert`**：L207、L208、L211-212、L226、L232-237、L241-243 的关键比对（含四周期 `==`、120 维、`1e-8`、库哈希相等）均为 `assert`，在 `python -O` 下会被剥离 → 可能误报 pass。validator 以 `-B` 启动子探针但不控制父进程优化级别。建议父进程入口显式拒绝 `__debug__` 为假（`if not __debug__: raise`）。
- **O2 output 祖先符号链接未覆盖**：`output.is_symlink()`（L165）只查末段，`output=output.resolve()`（L188）在检查之后，符号链接父目录可把创建重定向到别处。属运营者提供的路径，风险低。
- **O3 “只清自己目录”测试覆盖不完整**：`test_failed_run_cleans_up_its_own_snapshot`（L474-497）只断言 track 到的 snapshot 被删，未断言 sandbox/output 及其它路径未被触碰。代码层面仅 `rmtree(snapshot)`，行为正确，但缺“他人未被误删”的断言。

## 6. 测试证据（仅纯 mock，符合限制）

命令：WSL Ubuntu-22.04 `python3 validation/test_generated_e0_lifecycle_admission.py` → `Ran 52 tests ... OK`。
覆盖：源集合/文件名/父目录/根前缀与符号链接拒绝、manifest 读时字节绑定、六源内存校验与失败不落盘、库身份与大小、排序契约（坏输入不触碰 mkdtemp/compiler/probe）、失败仅清自身快照、冻结 argv/120/4×1000/1e-8/四周期与 contract 数值。
mock 面：`subprocess.run`/`Popen`/`shutil.copyfile`/`json_identity`/`sys.platform`；未执行编译、`.so` 加载、ROS/native。

## 7. 证据边界（明确不声称通过）

- 本轮仅纯 mock + 只读源码，**未**做完整 reset/cold 生命周期，故不构成通过结论。
- 原 private 当前 wrapper library `528db3241baa43ef79166fbba74f6a4176aa2d82bf7c238bfe8f8db68267b328` / 87584B 来自历史会话（见 `docs/coordination/ds-26-host-recheck-20260912.json`、`docs/plan/26-current-wrapper-recheck-plan.md`），本轮未重测、未重算其字节；不能据此宣称 wrapper/生命周期通过。
- 结论仅覆盖第 1 节所列 SHA 的两个文件。

## 8. 末尾 SHA 冻结

```
FROZEN_AT 2026-09-12T13:58:56Z
ec883644acce248921c9775451699ce2c149311d438b720e3e21c361571a2098  tools/validate_generated_e0_lifecycle.py
8970c7ed4afeda5de0e6461f972b08c18d1f76f3148990352e7c0e0d90e4f3e3  validation/test_generated_e0_lifecycle_admission.py
```

与首读一致，无未审变化。本报告文件自身 SHA256 见交付回执。
