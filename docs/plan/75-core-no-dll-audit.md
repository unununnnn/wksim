# #75 支撑门禁：自主核心无厂商 DLL 面的静态审计

2026-09-12。`tools/audit_core_no_vendor_dll.py` 在当前仓库树上机器证明：默认自主核心不解析、不加载任何供应商 DLL 路径。**这不是 #75 的实跑**——票面"全新目录执行一次运行"的前置 #74 仍阻塞，本切片不解除它。

## 审计的不变量（任一违反即 exit 2）

1. **唯一加载点与动态执行面封闭（AST 级，P1）**：
   - 核心三包全部 `.py` 经 AST 扫描，动态库加载调用恰好一处——`model.py` 的 `Model.__init__` 中形态精确为 `ctypes.CDLL(str(Path(library).resolve()))`（调用方给径）；
   - 拦截反射加载面：`from ctypes import CDLL/PyDLL`、`loader = ctypes.CDLL/WinDLL/...` 赋值别名及其调用、`ctypes.cdll/windll[...]` 下标访问与属性取库、`__import__('ctypes')`/`importlib` 动态导入再 `getattr` 间接调用、`getattr` 别名与 `__getattribute__`、`PyDLL`/`WinDLL`/`OleDLL`/`LoadLibrary`/`dlopen`、任何硬编码库字面量全部检出并保守拒绝；`m = ctypes` 模块赋值别名会被跟踪，其后续 `__dict__`/`vars`/下标面同样封闭；
   - 拦截字典反射面：`ctypes.__dict__` 属性访问、`ctypes.__dict__[loader]` 下标查找、`vars(ctypes)` 动态调用与 `vars(ctypes)[loader]` 下标访问、`.get("CDLL")` 等字典检索全部阻断；
   - 拦截 `operator.attrgetter` 反射面：直接导入、一级/多级 alias、`"".join` 静态拼接及未知/动态参数均保守拒绝；普通 `attrgetter("real")` 等不受影响。普通 dict 下标（`d["CDLL"]`）与普通 `vars()` 调用不误报——加载令牌切片/参数仅当其基对象链涉及 ctypes 时才拒绝；
   - 拦截非 ctypes 原生/无源加载面：`importlib.machinery` 的 `ExtensionFileLoader`（原生 .pyd/.dll/.so）与 `SourcelessFileLoader`（无源 .pyc）的导入、属性访问与调用一律拒绝；
   - `ctypes.pythonapi` 立场：**禁止**。它是当前解释器的预绑定 PyDLL 句柄——不加载新供应商库，但属本审计证明范围之外的活跃原生调用面，核心无合法用途；`from ctypes import *`、`from importlib import *`、`from importlib.machinery import *` 和 `from operator import *` 同样拒绝，避免 wildcard 隐藏 loader/import/attrgetter 名称；
   - 属主链原则：加载令牌仅当其属主链涉及 ctypes（含赋值别名）时拒绝；用户类属性 `Foo.CDLL`、`getattr(user_obj, "CDLL")`、普通 dict 与静态已知非 loader 的 `attrgetter` 保持 clean；未知 `attrgetter` 参数 fail closed；`eval`/`exec`/`compile` 名在任何属主上均拒绝（防内建遮蔽）。
   - 载体传播截断（规则 6c/6d）：ctypes 属主的 loader 类属性引用在**引用点**即拒绝，经容器/元组解包/AnnAssign/return/lambda/for 目标/字典/下标的传播无从洗白；`vars`/`getattr` alias、ctypes 模块 tuple alias、`operator.attrgetter` 导入/多级 alias、`operator.__dict__`/`vars(operator)` 访问跟踪后同规则拒绝；`"".join(("C","DLL"))` 等静态拼接由 `_eval_str` 解析。`from importlib import import_module` 及其返回的 `importlib.machinery` 模块经 `getattr`/下标/`vars`/`.get()` 的 `ExtensionFileLoader`/`SourcelessFileLoader` 访问同样拒绝；动态未知模块名在到达 loader 访问前 fail closed。普通 `from ctypes import c_double` 等非 loader 符号保持 clean；
   - 拦截动态执行面：`eval`/`exec`/内建 `compile` 形成的动态执行面全面拦截；核心包内 symlink、缺目录、不可解析或编码异常源码均拒绝；嵌套包路径采用 `relative_to(root).as_posix()` 规整。
2. **动态代码执行白名单制（行+内容哈希双钉，长度硬锁 1 项，P1）**：
   - 仓库内仅 `Simulator/wksim_runtime/telemetry_dialect.py` 第 20 行存在合法的预哈希方言加载：`exec(compile(raw, str(source), 'exec'), module.__dict__)`；
   - 白名单长度硬编码精确固定为 1 项且禁止扩容；每条钉（相对路径、行号 20、该行 sha256 `f16205be...`、token、理由）；任何未白名单的 `eval`/`exec`/`compile` 调用、行漂移、内容编辑或 AST 观测不一致均立即失败。
3. **核心包游离可加载工件静态扫描拦截（P2）**：
   - 严格限定核心包合法边界：核心包为纯 Python 源码与静态资产包；
   - 严禁任何游离原生动态链接库或二进制扩展工件（`.dll`、`.pyd`、`.so`、`.dylib`、`.exe`）驻留于核心包内；
   - 严禁 `__pycache__` 外部存在游离 Python 字节码（`.pyc`、`.pyo`）；
   - `__pycache__` 内部仅允许合法字节码缓存，且每一个缓存文件必须在其上层目录存在同名对应 `.py` 源码；无源孤儿字节码（orphaned bytecode）或缓存目录内非字节码文件一律拒绝。
4. **厂商引用白名单制（行+内容哈希双钉，长度硬锁 2 项不可扩容）**：
   - `.dll`/`CopterSim.exe`/`DllSimCtrlAPI`/`RflySim` 令牌只允许两处现存引用（`model.py:15` 与已提交 `bdd39ee` 的 `joint_runtime.py:478` guard 行）；当前 guard 行精确内容的 sha256 为 `50d84d7a7fea63689a2af3763da245811b96dfac46b7f2054843f8dff530193a`，与工具 allowlist 一致；
   - 白名单长度硬编码精确固定为 2 项且禁止扩容；每条钉（相对路径、行号、该行 sha256、token、理由）；新增引用、行漂移、内容编辑、白名单增删/重复即失败。
5. **配置面无插件字段与非法值**：两份示例配置经严格 JSON（拒重复键/NaN/Inf）+ `validate_config` 归一化后递归键集合不含 dll/plugin/vendor，值字符串亦递归扫描严禁包含 vendor/loader 令牌；schema 校验异常稳定转化为 audit violations 而非异常崩溃；config/joint_config 源码在位且非软链；导入在校验后被精确还原（无模块缓存/sys.path 残留，有恢复测试）。**受信有副作用边界**：本检查会在同一解释器中 import 并执行仓库 `config.py` 的全部顶层代码；当前版本只定义常量/函数，但审计不沙箱、不回滚该顶层代码对环境变量、文件、网络、线程、第三方模块缓存或其他全局状态的副作用。当前代码若引入此类副作用，必须在复核中显式记录并扩大恢复测试；不能把 `sys.path` 与 `Simulator.*` 模块缓存恢复误解为任意副作用隔离。
6. **模型身份为项目自建且各文件独立精确封闭**：`capability-index.json` 与 `joint-profiles.json` 分别独立精确等于冻结期望集 `{libwksim_model.so}`，严禁跨文件 union 集合遮蔽——任何单文件中删除条目均独立判负。
7. **审计根**：必须真实绝对目录、非软链。
8. **输出固定**：`schema=wksim.core-no-vendor-dll.v1`，status pass/failed，non_claims 三条固定文本，字节确定性（sort_keys、无 NaN）。

- #75 完成条件要求一次真实运行 + 原始审计 PASS，前置 #74（←#73 needs-triage，ABI manifest 门已就位等证据包）。本切片只提供持续机器门禁：任何把厂商 DLL 面引入核心的提交会被立刻拒绝。
- #26 closure 门禁（`tools/audit_26_closure_readiness.py`）与本审计互补：前者钉证据链，后者钉运行面。

## Non-claims

- 静态审计，不加载任何库、不执行模型、不证明物理/倍率/飞行验收。
- 不批准、不否定任何厂商 ABI；不改变 #9/#27/#73–#75 状态。
- 白名单两处引用只是现状承认，不构成对厂商材料权利的判断。

## 信任根与当前状态

- 本工具不自带完整性证明：其自身源码哈希由外部提交/证据链（评审记录与仓库钉扎）保证；白名单自修改会被行哈希钉捕获，但"攻击者同时改工具与白名单"超出本门禁范围。
- 2026-09-12：`bdd39ee` 的 `joint_runtime.py:478` guard 行仍保持精确 hash `50d84d7a7fea63689a2af3763da245811b96dfac46b7f2054843f8dff530193a`，无需 repin；Windows、Ubuntu-22.04、RflySim-20.04 的 real-repo CLI 均通过。配置校验会在当前解释器中执行仓库 `config.py` 顶层 import；工具只恢复 `sys.path` 与 `Simulator.*` 模块缓存，不沙箱、不回滚环境变量、文件、网络、线程或其他全局副作用，这些副作用仍属于工具信任边界。
