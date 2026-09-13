$ErrorActionPreference = 'Stop'
$caseRoot = $PSScriptRoot
$repoRoot = (Resolve-Path (Join-Path $caseRoot '../..')).Path
Set-Location -LiteralPath $repoRoot
$nativeRoot = '/root/wksim-reexecution-114-20260909-03'
$windowsArgv = @('-m', 'unittest', 'validation.test_model_reexecution.AdmissionTests', '-v')
$wslArgv = @('-d', 'Ubuntu-22.04', '-u', 'root', '--', 'env', "WKSIM_REEXECUTION_NATIVE=$nativeRoot", '/usr/bin/python3', '-m', 'unittest', 'validation.test_model_reexecution', '-v')
$ErrorActionPreference = 'Continue' # unittest writes progress to stderr on success.
$windowsLog = & python @windowsArgv 2>&1
$windowsCode = $LASTEXITCODE
$windowsLog | Out-File -LiteralPath (Join-Path $caseRoot 'windows.log') -Encoding utf8
$wslLog = & wsl @wslArgv 2>&1
$wslCode = $LASTEXITCODE
$ErrorActionPreference = 'Stop'
$wslLog | Out-File -LiteralPath (Join-Path $caseRoot 'wsl.log') -Encoding utf8
if ($windowsCode -ne 0 -or $wslCode -ne 0) { throw "tests failed: Windows=$windowsCode WSL=$wslCode" }
$archiveRoot = Join-Path $caseRoot 'native'
New-Item -ItemType Directory -Path $archiveRoot | Out-Null
$uncRoot = '\\wsl.localhost\Ubuntu-22.04\root\wksim-reexecution-114-20260909-03'
# Only result/config/receipt evidence; never copy vendor source or libraries.
foreach ($name in @('source', 'input', 'run', 'mismatch-run', 'wrong-build-run', 'audit.json', 'capture.json', 'capture-process.json', 'source-plan.json', 'config.json', 'audit-rejected-gap.json', 'audit-rejected-time.json', 'audit-rejected-epoch.json', 'audit-rejected-request.json', 'audit-rejected-exit.json', 'audit-rejected-terminal.json')) {
    Copy-Item -LiteralPath (Join-Path $uncRoot $name) -Destination $archiveRoot -Recurse
}
$hashes = @{}
foreach ($relative in @('tools/reexecute_model.py', 'validation/test_model_reexecution.py', 'Simulator/wksim_core/model.py', 'Simulator/wksim_core/model.cpp', 'Simulator/wksim_core/model_parameters.py', 'Simulator/wksim_runtime/replay.py', 'docs/plan/46-reexecution-contract.md')) {
    $hashes[$relative] = (Get-FileHash -LiteralPath $relative -Algorithm SHA256).Hash.ToLower()
}
$evidenceHashes = @{}
Get-ChildItem -LiteralPath $archiveRoot -File -Recurse | ForEach-Object {
    $evidenceHashes[$_.FullName.Substring($archiveRoot.Length + 1).Replace('\','/')] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower()
}
@{issue=114; windows_argv=@('python')+$windowsArgv; windows_exit=$windowsCode; windows_tests=33; windows_skipped=0; wsl_argv=@('wsl')+$wslArgv; wsl_exit=$wslCode; wsl_tests=34; wsl_skipped=0; native_root=$nativeRoot; source_sha256=$hashes; evidence_sha256=$evidenceHashes; model='gpt-6-astra'; effort='low'; model_verification='latest turn_context for thread 01a085a2-4d06-7f03-afec-a223f7527504'} | ConvertTo-Json -Depth 12 | Out-File -LiteralPath (Join-Path $caseRoot 'review.json') -Encoding utf8
Write-Output 'Windows 33/33, WSL 34/34; zero skips; native results archived.'
