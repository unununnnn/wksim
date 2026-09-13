# OMP 全局飞行证据文件机械核对

日期：2026-09-10。核对对象：`validation/47-global-flight/final-matrix.json`（12 场归档：ap-01..ap-05、px4-01、px4-03..px4-08）及同目录各场 `archive.json`。

**范围声明：本核对仅证明文件身份（文件存在、SHA256 与矩阵记录一致）。不代表 G6 数值等价、联合倍率、默认生产准入（矩阵中 `production_admitted: false` 未变）或任何功能/物理正确性验收。未执行 `archive.py`/`collect-final.py`，未修改任何原件。**

## 结果汇总

- 归档场次：12；哈希核对项：26（每场 tar.gz + result.json，px4-08/ap-05 另加 audit.json）
- SHA256 一致：26/26；不一致：0
- tar.gz 字节数与矩阵 `bytes` 一致：12/12
- 每场 `archive.json` 均存在，且其 raw_sha256/result_sha256 与 final-matrix.json 完全一致：12/12
- 报告引用的本地报告与入口/工具脚本均存在（8/8）；`audit_source_sha256` 所列两个审计脚本 SHA256 复算一致

## 逐场哈希（expected = final-matrix.json，actual = 本地复算）

| 场次 | 文件 | 路径 | expected SHA256 | actual SHA256 | match |
| --- | --- | --- | --- | --- | --- |
| ap-01 | raw-evidence.tar.gz | `C:\Users\PC\Documents\odid编译\wksim\validation\47-global-flight\ap-01\raw-evidence.tar.gz` | `bd0c2ef4c354ba5e02b1085a60c98c387eac1de83cf3c9be3b40bf0150691e10` | `bd0c2ef4c354ba5e02b1085a60c98c387eac1de83cf3c9be3b40bf0150691e10` | PASS |
| ap-01 | result.json | `C:\Users\PC\Documents\odid编译\wksim\validation\47-global-flight\ap-01\result.json` | `32f9285bac0f63522a5281766dce6412cc3db13790c001cdc0160973f88f4ef9` | `32f9285bac0f63522a5281766dce6412cc3db13790c001cdc0160973f88f4ef9` | PASS |
| ap-02 | raw-evidence.tar.gz | `C:\Users\PC\Documents\odid编译\wksim\validation\47-global-flight\ap-02\raw-evidence.tar.gz` | `6975eaa2b8f9cb35415b7bbc09c5bb68258b844da0f080e1de8329c328f26a87` | `6975eaa2b8f9cb35415b7bbc09c5bb68258b844da0f080e1de8329c328f26a87` | PASS |
| ap-02 | result.json | `C:\Users\PC\Documents\odid编译\wksim\validation\47-global-flight\ap-02\result.json` | `8e2491eb776b205afe710a328d027c2336b4a2442f0b0550b59c8cea7d77196b` | `8e2491eb776b205afe710a328d027c2336b4a2442f0b0550b59c8cea7d77196b` | PASS |
| ap-03 | raw-evidence.tar.gz | `C:\Users\PC\Documents\odid编译\wksim\validation\47-global-flight\ap-03\raw-evidence.tar.gz` | `b62f9e8a10982e9dd5aa7f0b52f60dd376ea9a02377e8a0d8967df4aa7ab7546` | `b62f9e8a10982e9dd5aa7f0b52f60dd376ea9a02377e8a0d8967df4aa7ab7546` | PASS |
| ap-03 | result.json | `C:\Users\PC\Documents\odid编译\wksim\validation\47-global-flight\ap-03\result.json` | `50715ae6d5e272974f1de5ecbda221ed66dae933de4ddb386b3eb76263a5c574` | `50715ae6d5e272974f1de5ecbda221ed66dae933de4ddb386b3eb76263a5c574` | PASS |
| ap-04 | raw-evidence.tar.gz | `C:\Users\PC\Documents\odid编译\wksim\validation\47-global-flight\ap-04\raw-evidence.tar.gz` | `5ca0d0cdd8d58bc93c9fb2957f2f16360d34cdae274272d59993ed9857cd2267` | `5ca0d0cdd8d58bc93c9fb2957f2f16360d34cdae274272d59993ed9857cd2267` | PASS |
| ap-04 | result.json | `C:\Users\PC\Documents\odid编译\wksim\validation\47-global-flight\ap-04\result.json` | `7a58458ccdf58292b53a14db208d86054a7c9bfb02e736c11c46fe47b86da1db` | `7a58458ccdf58292b53a14db208d86054a7c9bfb02e736c11c46fe47b86da1db` | PASS |
| ap-05 | raw-evidence.tar.gz | `C:\Users\PC\Documents\odid编译\wksim\validation\47-global-flight\ap-05\raw-evidence.tar.gz` | `9d5e311f079d5938d768811170ad6e58d036a352bf5702e8bab81a7c12c44658` | `9d5e311f079d5938d768811170ad6e58d036a352bf5702e8bab81a7c12c44658` | PASS |
| ap-05 | result.json | `C:\Users\PC\Documents\odid编译\wksim\validation\47-global-flight\ap-05\result.json` | `906699da62e3d6064d0e5d89eede5ce1a29cceeb70e18e047c453c6ad51ba419` | `906699da62e3d6064d0e5d89eede5ce1a29cceeb70e18e047c453c6ad51ba419` | PASS |
| ap-05 | audit.json | `C:\Users\PC\Documents\odid编译\wksim\validation\47-global-flight\ap-05\audit.json` | `2ff7caf36e29735378e5e4e4e347c8b5a15a8a73cd5248a3b2583f538265fd41` | `2ff7caf36e29735378e5e4e4e347c8b5a15a8a73cd5248a3b2583f538265fd41` | PASS |
| px4-01 | raw-evidence.tar.gz | `C:\Users\PC\Documents\odid编译\wksim\validation\47-global-flight\px4-01\raw-evidence.tar.gz` | `f2e2421d01bbfff47ad56c3ddfd9acd7d64377e67278d95bf7afd36b5fc4ed88` | `f2e2421d01bbfff47ad56c3ddfd9acd7d64377e67278d95bf7afd36b5fc4ed88` | PASS |
| px4-01 | result.json | `C:\Users\PC\Documents\odid编译\wksim\validation\47-global-flight\px4-01\result.json` | `1dc3112963d16d51cae2bf419d962a71985e0af4477bde4ffcd71508ed80add1` | `1dc3112963d16d51cae2bf419d962a71985e0af4477bde4ffcd71508ed80add1` | PASS |
| px4-03 | raw-evidence.tar.gz | `C:\Users\PC\Documents\odid编译\wksim\validation\47-global-flight\px4-03\raw-evidence.tar.gz` | `71e4ba4e919ea2c87742ade776458d7644e300a5ac1e27c53a911b526bb21102` | `71e4ba4e919ea2c87742ade776458d7644e300a5ac1e27c53a911b526bb21102` | PASS |
| px4-03 | result.json | `C:\Users\PC\Documents\odid编译\wksim\validation\47-global-flight\px4-03\result.json` | `b8983e566860995c726965f8fd8ed91678adca389023608615482c8a3169e0de` | `b8983e566860995c726965f8fd8ed91678adca389023608615482c8a3169e0de` | PASS |
| px4-04 | raw-evidence.tar.gz | `C:\Users\PC\Documents\odid编译\wksim\validation\47-global-flight\px4-04\raw-evidence.tar.gz` | `5557c0593f1ceb449243c0fbf04cdadbfaeb7f07e73975796dec8407d37a9d0d` | `5557c0593f1ceb449243c0fbf04cdadbfaeb7f07e73975796dec8407d37a9d0d` | PASS |
| px4-04 | result.json | `C:\Users\PC\Documents\odid编译\wksim\validation\47-global-flight\px4-04\result.json` | `f0b6883db801b87ae1851e609dec87091eec1989d9db43cf471c76fecfc5ba0f` | `f0b6883db801b87ae1851e609dec87091eec1989d9db43cf471c76fecfc5ba0f` | PASS |
| px4-05 | raw-evidence.tar.gz | `C:\Users\PC\Documents\odid编译\wksim\validation\47-global-flight\px4-05\raw-evidence.tar.gz` | `61b0c71758730229be693d7be1e4774dcfd8bf78c6c6df75d9e36ffeefccf0dd` | `61b0c71758730229be693d7be1e4774dcfd8bf78c6c6df75d9e36ffeefccf0dd` | PASS |
| px4-05 | result.json | `C:\Users\PC\Documents\odid编译\wksim\validation\47-global-flight\px4-05\result.json` | `19b0c986be1bbc34c7bd0e07484530b428375b39ee8662a678b380baec04e508` | `19b0c986be1bbc34c7bd0e07484530b428375b39ee8662a678b380baec04e508` | PASS |
| px4-06 | raw-evidence.tar.gz | `C:\Users\PC\Documents\odid编译\wksim\validation\47-global-flight\px4-06\raw-evidence.tar.gz` | `51d3b875438a29f79adeee2f125657eccef5b90c01b374b1aed556c7b4b5155b` | `51d3b875438a29f79adeee2f125657eccef5b90c01b374b1aed556c7b4b5155b` | PASS |
| px4-06 | result.json | `C:\Users\PC\Documents\odid编译\wksim\validation\47-global-flight\px4-06\result.json` | `13da9d2dc193ebbd0d077873becd4a6c8551b2a32ba2e7c4cfa4d96953bd262f` | `13da9d2dc193ebbd0d077873becd4a6c8551b2a32ba2e7c4cfa4d96953bd262f` | PASS |
| px4-07 | raw-evidence.tar.gz | `C:\Users\PC\Documents\odid编译\wksim\validation\47-global-flight\px4-07\raw-evidence.tar.gz` | `b83121d0bc623671fa061fda958c4dfc0461166ee71652174aa5a2eecbeb7fde` | `b83121d0bc623671fa061fda958c4dfc0461166ee71652174aa5a2eecbeb7fde` | PASS |
| px4-07 | result.json | `C:\Users\PC\Documents\odid编译\wksim\validation\47-global-flight\px4-07\result.json` | `192f2ece89ec57c0f07cdb223c09d6c817a56005f5c99226c719b04517bd476a` | `192f2ece89ec57c0f07cdb223c09d6c817a56005f5c99226c719b04517bd476a` | PASS |
| px4-08 | raw-evidence.tar.gz | `C:\Users\PC\Documents\odid编译\wksim\validation\47-global-flight\px4-08\raw-evidence.tar.gz` | `e09f0acb58a9c334558d1af0bc446db524a4dc04eb96762dd538bcecb2c93e1b` | `e09f0acb58a9c334558d1af0bc446db524a4dc04eb96762dd538bcecb2c93e1b` | PASS |
| px4-08 | result.json | `C:\Users\PC\Documents\odid编译\wksim\validation\47-global-flight\px4-08\result.json` | `0a340c9abbefdba99f4847553e9bda9724ab4f3cb7e4a07c575a00c5c90daa12` | `0a340c9abbefdba99f4847553e9bda9724ab4f3cb7e4a07c575a00c5c90daa12` | PASS |
| px4-08 | audit.json | `C:\Users\PC\Documents\odid编译\wksim\validation\47-global-flight\px4-08\audit.json` | `d3d94fe44a2ae10b07789311c39c32ff443d4f41f705a43f592e0bf644fc4d06` | `d3d94fe44a2ae10b07789311c39c32ff443d4f41f705a43f592e0bf644fc4d06` | PASS |

## 报告引用文件存在性

| 文件 | 存在 | 备注 |
| --- | --- | --- |
| `docs/2026-09-10-global-flight-report.md` | 是 |  |
| `validation/47-global-flight/final-matrix.json` | 是 |  |
| `tools/run-global-flight.sh` | 是 |  |
| `validation/47-global-flight/audit-command.sh` | 是 |  |
| `tools/global_origin_probe.cpp` | 是 |  |
| `tools/px4_home_candidate.py` | 是 |  |
| `tools/audit_global_flight.py` | 是 | SHA256 与矩阵 audit_source_sha256 一致（`e31e165e40428720…`） |
| `tools/audit_global_home_flight.py` | 是 | SHA256 与矩阵 audit_source_sha256 一致（`9ee2901c882a0e17…`） |

## 未覆盖项（明确声明）

- 本核对不评估物理正确性、不改变预算、不运行仿真或构建。
- 不证明：G6 数值等价、联合倍率验收、默认生产准入、功能验收；以上均以原报告与矩阵自身声明为准（`experimental: true`、`production_admitted: false`）。
- 机器可读结果见 `validation/coordination/omp-global-evidence-check.json`。
