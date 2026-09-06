param(
    [ValidateSet('px4','arducopter')][string]$Stack = 'arducopter',
    [string]$Stage = 'E:/ue5.5/build/wksim-native-a0e91366'
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$stageFull = [IO.Path]::GetFullPath($Stage)
if (-not $stageFull.StartsWith('E:\ue5.5\build\wksim-native-', [StringComparison]::OrdinalIgnoreCase)) { throw 'Unexpected staging directory' }
$engine = 'E:/ue5.5/files/UE_5.5/Engine/Binaries/Win64/UnrealEditor.exe'
$project = Join-Path $stageFull 'WksimVisual.uproject'
$module = Join-Path $stageFull 'Binaries/Win64/UnrealEditor-WksimVisual.dll'
if (-not (Test-Path -LiteralPath $module)) { throw 'Build the wksim UE module first' }
$probe = [Net.Sockets.UdpClient]::new([Net.IPEndPoint]::new([Net.IPAddress]::Loopback, 19060))
$probe.Dispose()
$runId = [guid]::NewGuid().ToString('N')
$evidence = Join-Path $repo ('validation/ue55-' + $Stack + '-' + $runId.Substring(0,8))
New-Item -ItemType Directory -Path (Join-Path $evidence 'frames') | Out-Null
$ueLog = Join-Path $evidence 'ue.log'
$frames = Join-Path $evidence 'frames'
$arguments = @(('"{0}"' -f $project), '/Game/Maps/UrbanBlock?game=/Script/WksimVisual.WksimVisualGameMode',
    '-game','-windowed','-ResX=1280','-ResY=720','-NoSound','-NoSplash','-unattended',
    '-ExecCmds="t.IdleWhenNotForeground 0,t.MaxFPS 30"', ('-abslog="{0}"' -f $ueLog),
    ('-WksimRunId={0}' -f $runId), ('-WksimVehicle={0}' -f $Stack), '-WksimPort=19060', ('-WksimCaptureDir="{0}"' -f $frames))
$process = $null
$exitCode = 1
try {
    $process = Start-Process -FilePath $engine -ArgumentList $arguments -WorkingDirectory $stageFull -WindowStyle Hidden -PassThru
    $manifest = [ordered]@{utc=[DateTime]::UtcNow.ToString('o'); run_id=$runId; pid=$process.Id; engine=$engine;
        project=$project; arguments=$arguments; evidence=$evidence; module_sha256=(Get-FileHash -LiteralPath $module -Algorithm SHA256).Hash}
    $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $evidence 'manifest.json') -Encoding utf8
    Write-Output ($manifest | ConvertTo-Json -Compress -Depth 8)
    $watch = [Diagnostics.Stopwatch]::StartNew()
    while ($watch.Elapsed.TotalSeconds -lt 120) {
        if ($process.HasExited) { throw "UE exited before ready: $($process.ExitCode)" }
        if ((Test-Path -LiteralPath $ueLog) -and (Select-String -LiteralPath $ueLog -Pattern "WKSIM_READY run=$runId" -Quiet) -and
            (Get-ChildItem -LiteralPath $frames -Filter '*.png').Count -gt 0) { break }
        Start-Sleep -Milliseconds 500
    }
    if ($watch.Elapsed.TotalSeconds -ge 120) { throw 'UE readiness/frame timeout; inspect own run log' }
    & 'D:/date/miniconda/python.exe' (Join-Path $PSScriptRoot 'validate_ue55.py') --stack $Stack --evidence $evidence --run-id $runId
    $exitCode = $LASTEXITCODE
} finally {
    if ($process -and -not $process.HasExited) {
        $null = $process.CloseMainWindow()
        if (-not $process.WaitForExit(10000)) { $process.Kill(); $process.WaitForExit() }
    }
    if ($process) {
        [ordered]@{pid=$process.Id; exited=$process.HasExited; exit_code=$process.ExitCode; scope='Only the UE process created by this diagnostic'} |
            ConvertTo-Json | Set-Content -LiteralPath (Join-Path $evidence 'cleanup.json') -Encoding utf8
    }
}
if ($exitCode -ne 0) { throw "UE boundary diagnostic failed; $evidence" }
Write-Output "UE boundary diagnostic passed: $evidence"
