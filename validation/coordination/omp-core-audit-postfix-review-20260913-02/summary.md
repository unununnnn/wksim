# 独立对抗性复核：三项 P1 修复未达 fail-closed（omp-core-audit-postfix-review-20260913-02）

> 结论先行：**无 P0；3 项 P1；2 项 P2。** 针对 `tools/audit_core_no_vendor_dll.py` 与
> `validation/test_audit_core_no_vendor_dll.py` 的未提交修改（即对
> `codebuddy-core-native-audit-review-20260913-01` 三项 P1 的修复），17 条复现用例中
> **15 条成功绕过**（审计 `status=pass`、`violations=[]`），2 条对照（基线通过、追加第二
> CDLL 被拒）行为正确。三项修复各自仍为"令牌存在性"检查，未建立可达性、绑定唯一性与
> 句柄上下文白名单，fail-closed 声明不成立。

- 审查对象：当前工作树未提交 diff（in-scope SHA256 见 findings.json，会话前后不变）。
- 范围只读：未修改任何既有文件；未 `git add/commit/push`；未触碰 docs/账本/Issue。
- 执行边界：纯 AST + 临时目录；未加载 `.so`/`.dll`、未启动 ROS/飞控/模型/UE/MATLAB、未操作进程。
- 唯一写入目录：`validation/coordination/omp-core-audit-postfix-review-20260913-02/`。
- 开工 HEAD `72ef95d`，收工 HEAD `0106b90b31365481f8f60052a22e184039dce353`（对端并发推进）；
  架构祖先 `f333316…` 检查退出码 0；in-scope 四文件 SHA256 前后一致，结论不受并发影响。

## 复现与纯测试证据

| 命令 | 退出码 | 结果 | 输出 SHA256 |
| --- | --- | --- | --- |
| `python -B validation/coordination/omp-core-audit-postfix-review-20260913-02/repro_tests.py` | 0 | 17 例：2 对照正确、15 绕过；三连跑逐字节一致 | `753b4c78ad52a35dfc15120317c96f2f31c7b7f13f4ec0008dc41c33680093ca` |
| `python -B -m pytest validation/test_audit_core_no_vendor_dll.py -q` | 0 | 99 passed, 1 skipped, 120 subtests passed | `c4d1c0a4e7c5b6277dbea6e3b1c643fe4c9b68e7b7a3f2d3399f528fa51d529c` |
| `python -B tools/audit_core_no_vendor_dll.py` | 0 | `status=pass`、`violations=[]` | `de3b8dd998e439df6cc894ba146eb5488b254f18c9be77a87b555679a0cc128c`（与修复记录的 audit.json 哈希逐字节一致） |

## 发现一览（最小变异与修复建议的完整版见 findings.json）

### P1-1 门禁可达性：`_if_body_raises` / 词法序 ≠ 支配（6 条绕过）

根因：`ast.walk` 深度穿透 + `_if_body_raises` 接受埋在不可达内层的 `Raise` + 门禁 `If`
可嵌套在死外层条件、死嵌套函数或吞异常的 `try/except` 中；`lineno < call.lineno` 只是词法序。

| 用例 | 最小变异（均保持钉定行 51 不动） |
| --- | --- |
| A1/A2/A3 | 第 40/31/34 行 `raise …` → `if False: raise …`（单行；摘要门/路径门/SHA 门各自永不触发） |
| B | 39–40 行外套 `if False:`（2 行换 2 行） |
| F | 30–40 行整体移入**永不被调用**的嵌套 `def _verify(...)`，顶层只留 `library = Path(library_path)` 与裸加载 → 完全未验证的 dlopen，审计全绿 |
| G | 摘要门包进 `try: … except PerfCaptureError: pass`（合并 47–50 行保持行数） |

修复要点：门禁 `If` 必须是宿主函数**顶层的直接语句**且钉定调用在其后同序列出现；
`_if_body_raises` 改为"body 恰为一条无条件 `Raise`"，任何嵌套复合语句 fail closed。

### P1-2 数据流：无绑定唯一性、read 尺寸不检（3 条绕过）

| 用例 | 最小变异 |
| --- | --- |
| C | 37 行 `read(1024 * 1024)` → `read(0)`：循环零次喂入，摘要退化为空输入哈希（与被修的 `digest.update(b'')` 同类） |
| D | 47 行 → `self.library_path = str(library); library = Path('/tmp/evil.so')`：**验证真文件、加载恶意文件**，无需调用方配合，完整逃逸 |
| E | 38 行 → `digest.update(chunk); digest = hashlib.sha256()`：门比较的是新空摘要 |

修复要点：`path_name`/`digest_name`/`stream_name` 在函数内**恰好一次绑定**（统计
Assign/AnnAssign/AugAssign/NamedExpr/for-target/with-var），重绑定即 fail；路径绑定须先于
with 与门禁；`read()` 尺寸参数须为正常数常量或其乘积。

### P1-3 句柄禁闭：三条黑名单模式挡不住容器/闭包/返回值/参数逃逸（6 条绕过）

根因：529–540 行只拒绝 `libc.<attr≠setns>`、`x = libc`、`getattr(libc,…)` 三种形态；
`_abstract` 对 CDLL 结果返回无标签值（1064–1065），句柄一旦改名/入容器即全规则隐身——
H5 证明经 `[libc][0]` 连 `dlopen` 这个真实 loader 令牌也不被 rule 6c/load-site 捕获。

| 用例 | 单行变异（插入 netns_handoff.py:186 或替换 194 行） |
| --- | --- |
| H1 | `(h := libc).system(b'id')`（海象） |
| H2 | `[libc][0].system(b'id')`（容器） |
| H3 | `(lambda: libc)().system(b'id')`（闭包） |
| H4 | 194 行 `return dict(...)` → `return libc`（返回值把整进程符号面交给所有调用方） |
| H5 | `[libc][0].dlopen(b'/tmp/x.so', 2)`（**真实第二 loader**） |
| H6 | `[x.system(b'id') for x in [libc]]`（推导式改名） |

修复要点：改白名单——对模块内每个 `id == handle` 的 `ast.Name` 用父指针核验其上下文
只能是：钉定 Assign 的 value、`.setns` 属性链、setns 调用 func；其余一切上下文
（Return/Yield/调用实参/容器/NamedExpr/Lambda/推导式/默认值）fail closed。可选加固：
给钉定句柄的抽象值打 `ctypes_loader` 标签，让 6c/load-site 双保险。

### P2-1 测试缺口
新增测试只覆盖令牌删除型弱化（`and False`、`raise→pass`、整体重排、decoy open、直接
别名/符号）。把 `repro_tests.py` 的 15 条变异移植为负例（各断言 `status == "failed"`）。

### P2-2 声明仍超出证明力
`docstring`“every gate dominates the load”被 B/F/G 证伪；“any alias copy … fails closed”
只对直接赋值别名成立。`docs/plan/75` 旧措辞漂移依旧（他方所有，本次按范围未动）。

## 已核对为稳健（非发现）

- `_gate_test_intact` 只挡布尔常量在现有检测形状下**够用**：`and 0`/`or 1` 类非布尔常量
  要么改变顶层 BoolOp 类型导致检测失败（fail closed），要么令 Or 门过触发（拒绝方向，非逃逸）。
- 对照成立：基线 pass；追加第二 `ctypes.CDLL` 被双重拒绝。
- 所有变异经断言保持钉定行 51/183 行号与内容不变，绕过全部归因于新增形状逻辑而非钉定漂移。
- 真仓审计与纯测试套件均 exit 0：绕过是假阴性，不是基线损坏。

## 交付物

| 文件 | 说明 |
| --- | --- |
| `findings.json` | 机器可读发现、复现命令/退出码/SHA256、修复建议 |
| `summary.md` | 本报告 |
| `repro_tests.py` | 纯 AST/临时目录对抗复现（17 例），三连跑输出字节一致 |
| `manifest.sha256` | 上述三文件的 SHA256 |

交付后停止写入。
