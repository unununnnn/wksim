$ErrorActionPreference = 'Stop'
$probeExecDir = $PSScriptRoot
$probeRepo = Split-Path (Split-Path (Split-Path (Split-Path $probeExecDir)))
$probeSource = Join-Path $probeRepo 'tools/probe_reference_first_step.m'
foreach ($probeOutput in @('process.json','stdout.log','stderr.log','exit.json')) {
    if (Test-Path -LiteralPath (Join-Path $probeExecDir $probeOutput)) { throw 'Execution receipts already exist; choose a new execution directory.' }
}
if (Test-Path -LiteralPath (Join-Path (Split-Path $probeExecDir) 'run-05')) { throw 'Run directory already exists.' }
if (Get-Process -Name MATLAB -ErrorAction SilentlyContinue) {
    throw 'An existing MATLAB process is active; do not launch a competing probe.'
}
$probeIdentity = Get-Content -LiteralPath (Join-Path $probeExecDir 'invocation.json') -Raw | ConvertFrom-Json
if ((Get-FileHash -LiteralPath $probeSource -Algorithm SHA256).Hash.ToLowerInvariant() -ne $probeIdentity.probe_sha256) {
    throw 'Reviewed probe source changed before launch.'
}
if ((Get-FileHash -LiteralPath (Join-Path $probeRepo 'tools/resolve_probe_solver_input.m') -Algorithm SHA256).Hash.ToLowerInvariant() -ne $probeIdentity.resolver_sha256) {
    throw 'Reviewed resolver source changed before launch.'
}
foreach ($probeCheck in (Get-Content -LiteralPath (Join-Path $probeExecDir 'input-checks.json') -Raw | ConvertFrom-Json)) {
    if ($probeCheck.used -and (Get-FileHash -LiteralPath $probeCheck.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $probeCheck.expected) {
        throw 'A frozen input changed before launch.'
    }
}
$probeInvoke = (Join-Path $probeExecDir 'invoke.m').Replace('\','/')
$probeExpression = "run('$probeInvoke')"
$probeProcess = Start-Process -FilePath 'D:\matlab\install date\bin\matlab.exe' -ArgumentList @('-batch', ('"' + $probeExpression + '"')) -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $probeExecDir 'stdout.log') -RedirectStandardError (Join-Path $probeExecDir 'stderr.log')
@{pid=$probeProcess.Id;started=$probeProcess.StartTime.ToString('o');invocation=$probeExpression} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $probeExecDir 'process.json')
while (-not $probeProcess.WaitForExit(1000)) { }
@{pid=$probeProcess.Id;exit_code=$probeProcess.ExitCode;exited_utc=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $probeExecDir 'exit.json')
Get-Content -LiteralPath (Join-Path $probeExecDir 'exit.json')
if ($probeProcess.ExitCode -ne 0) { throw 'Reference probe failed; preserve its logs.' }
