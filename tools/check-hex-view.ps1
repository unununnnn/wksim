param([string]$Stage='E:/ue5.5/build/wksim-native-hex-20260909-01')
$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
$stagePath=[IO.Path]::GetFullPath($Stage)
if ((Split-Path -Parent $stagePath) -ne 'E:\ue5.5\build' -or -not $stagePath.StartsWith('E:\ue5.5\build\wksim-native-')) { throw 'Unexpected candidate stage' }
$instance=[guid]::NewGuid().ToString('N')
$runId='hex-view-fixture-'+$instance.Substring(0,8)
$evidence=Join-Path $repo ('validation/hex-view-fixture-'+$instance.Substring(0,8))
$frames=Join-Path $evidence 'frames'
New-Item -ItemType Directory -Path $frames | Out-Null
$probe=[Net.Sockets.UdpClient]::new([Net.IPEndPoint]::new([Net.IPAddress]::Loopback,0))
$port=$probe.Client.LocalEndPoint.Port
$probe.Dispose()
$engine='E:/ue5.5/files/UE_5.5/Engine/Binaries/Win64/UnrealEditor.exe'
$project=Join-Path $stagePath 'WksimVisual.uproject'
$module=Join-Path $stagePath 'Binaries/Win64/UnrealEditor-WksimVisual.dll'
$log=Join-Path $evidence 'ue.log'
$model='sha256:d703da7f888e7110e402aa32ff911cabcb24e0b01afb8bbf4c9ec1ccb897276a'
$argv=@(('"{0}"' -f $project),'/Game/Maps/UrbanBlock?game=/Script/WksimVisual.WksimVisualGameMode',
    '-game','-windowed','-ResX=1280','-ResY=720','-NoSound','-NoSplash','-unattended',
    '-ExecCmds="t.IdleWhenNotForeground 0,t.MaxFPS 30"',('-abslog="{0}"' -f $log),
    ('-WksimRunId='+$runId),'-WksimVehicle=1','-WksimConfiguration=hex-X',
    ('-WksimInstance='+$instance),('-WksimModelIdentity='+$model),('-WksimPort='+$port),
    ('-WksimCaptureDir="{0}"' -f $frames))
$process=$null
try {
    $process=Start-Process -FilePath $engine -ArgumentList $argv -WorkingDirectory $stagePath -WindowStyle Hidden -PassThru
    [ordered]@{scope='Synthetic state to actual UE only; no native flight';run_id=$runId;instance_id=$instance;
        model_identity=$model;pid=$process.Id;start_time=$process.StartTime.ToUniversalTime().ToString('o');
        engine=$engine;project=$project;arguments=$argv;port=$port;module_sha256=(Get-FileHash $module).Hash;
        evidence=$evidence} | ConvertTo-Json -Depth 10 | Set-Content (Join-Path $evidence 'manifest.json') -Encoding utf8
    Write-Output $evidence
    $watch=[Diagnostics.Stopwatch]::StartNew()
    while ($watch.Elapsed.TotalSeconds -lt 120) {
        if ($process.HasExited) { throw 'UE exited before readiness' }
        if ((Test-Path $log) -and (Select-String -LiteralPath $log -Pattern "WKSIM_READY run=$runId" -Quiet)) { break }
        Start-Sleep -Milliseconds 500
    }
    if ($watch.Elapsed.TotalSeconds -ge 120) { throw 'UE readiness timeout' }
    & 'D:/date/miniconda/python.exe' (Join-Path $PSScriptRoot 'check_hex_view.py') --run-id $runId --instance-id $instance --model-identity $model --port $port --output (Join-Path $evidence 'boundary')
    if ($LASTEXITCODE -ne 0) { throw 'Hex UE boundary checks failed' }
} finally {
    if ($process -and -not $process.HasExited) {
        $null=$process.CloseMainWindow()
        if (-not $process.WaitForExit(10000)) { $process.Kill();$process.WaitForExit() }
    }
    if ($process) {
        @{pid=$process.Id;exited=$process.HasExited;exit_code=$process.ExitCode} |
            ConvertTo-Json | Set-Content (Join-Path $evidence 'cleanup.json') -Encoding utf8
    }
}
