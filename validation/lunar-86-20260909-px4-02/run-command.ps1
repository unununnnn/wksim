param([Parameter(Mandatory=$true)][ValidateSet('preflight','flight','audit')][string]$Stage)
$ErrorActionPreference = 'Stop'
$repoRoot = 'C:/Users/PC/Documents/odid编译/wksim'
$caseRoot = $PSScriptRoot
$runId = 'pid-px4-20260909-02-7e3ce147'
$outputRoot = '/root/wksim-pid-flight-pid-px4-20260909-02-7e3ce147'
$arguments = @('-d','Ubuntu-22.04','-u','root','--','bash','tools/run-pid-flight.sh',
    '--stack','px4','--run-id',$runId,'--config','Simulator/wksim_runtime/pid-flight-v1.json',
    '--output-root',$outputRoot)
if ($Stage -eq 'preflight') { $arguments += '--preflight' }
if ($Stage -eq 'flight') {
    $check = Get-Content -Raw -LiteralPath (Join-Path $caseRoot 'preflight.stdout.log') | ConvertFrom-Json
    if (-not $check.ok) { throw 'Fresh preflight must succeed before flight' }
}
if ($Stage -eq 'audit') {
    $arguments = @('-d','Ubuntu-22.04','-u','root','--','bash',
        'validation/lunar-86-20260909-px4-02/audit.sh')
}
$stdoutPath = Join-Path $caseRoot ($Stage + '.stdout.log')
$stderrPath = Join-Path $caseRoot ($Stage + '.stderr.log')
$recordPath = Join-Path $caseRoot ($Stage + '.command.json')
foreach ($path in @($stdoutPath,$stderrPath,$recordPath)) {
    if (Test-Path -LiteralPath $path) { throw ('Refusing existing evidence: ' + $path) }
}
Set-Location -LiteralPath $repoRoot
$started = [DateTime]::UtcNow.ToString('o')
$process = Start-Process -FilePath 'wsl.exe' -ArgumentList $arguments -WorkingDirectory $repoRoot `
    -WindowStyle Hidden -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -PassThru
$process.WaitForExit()
$process.Refresh()
$code = $process.ExitCode
@{ stage=$Stage; executable='wsl.exe'; argv=$arguments; cwd=$repoRoot; started_utc=$started;
    ended_utc=[DateTime]::UtcNow.ToString('o'); returncode=$code; run_id=$runId; output_root=$outputRoot
} | ConvertTo-Json -Depth 6 | Out-File -LiteralPath $recordPath -Encoding utf8
Get-Content -LiteralPath $stdoutPath -Tail 30
Get-Content -LiteralPath $stderrPath -Tail 10
exit $code
