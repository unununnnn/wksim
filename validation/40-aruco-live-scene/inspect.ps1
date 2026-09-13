$ErrorActionPreference = 'Stop'
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$output = Join-Path $PSScriptRoot 'inspection.json'
if (Test-Path -LiteralPath $output) { throw 'Evidence already exists; do not overwrite' }
$stage = 'E:/ue5.5/build/wksim-native-hex-20260909-01'
$paths = @(
    'Simulator/wksim_perception/aruco.py', 'Simulator/ue55/rgb.py',
    'Simulator/ue55/Source/WksimVisual/WksimRgbSensor.h',
    'Simulator/ue55/Source/WksimVisual/WksimRgbSensor.cpp',
    'Simulator/ue55/Source/WksimVisual/WksimRgbFixture.cpp',
    'Simulator/ue55/Source/WksimVisual/WksimVisualGameMode.cpp',
    'docs/2026-09-09-aruco-consumer-report.md',
    'docs/rgb-capture-component.md', 'docs/rgb-geometry-fixture.md',
    'docs/2026-09-09-hex-visual-contract.md',
    'work/dependencies/ue55/content-sha256.json'
) | ForEach-Object { Join-Path $repo $_ }
$paths += @("$stage/WksimVisual.uproject", "$stage/Binaries/Win64/UnrealEditor-WksimVisual.dll",
    'E:/ue5.5/files/UE_5.5/Engine/Build/Build.version',
    'E:/ue5.5/files/UE_5.5/Engine/Binaries/Win64/UnrealEditor-Cmd.exe')
$paths += Get-ChildItem -LiteralPath "$stage/Content" -Recurse -File | ForEach-Object FullName
$identities = foreach ($path in $paths) {
    $item = Get-Item -LiteralPath $path
    [ordered]@{path=$item.FullName;bytes=$item.Length;sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()}
}
$resourceRoot = Join-Path $repo 'work/dependencies/ue55'
$archive = foreach ($entry in (Get-Content -LiteralPath "$resourceRoot/content-sha256.json" -Raw | ConvertFrom-Json)) {
    $actual = (Get-FileHash -LiteralPath (Join-Path $resourceRoot $entry.path)).Hash.ToLowerInvariant()
    [ordered]@{path=$entry.path;expected=$entry.sha256;actual=$actual;matches=($actual -eq $entry.sha256)}
}
$processes = @(Get-CimInstance Win32_Process -Filter "name like 'UnrealEditor%'" | Select-Object ProcessId,ExecutablePath,CommandLine)
[ordered]@{schema='wksim.aruco-scene-inspection.v1';utc=[DateTime]::UtcNow.ToString('o');
    command='powershell -NoProfile -ExecutionPolicy Bypass -File validation/40-aruco-live-scene/inspect.ps1';
    head=(git -C $repo rev-parse HEAD);branch=(git -C $repo branch --show-current);
    identities=@($identities);archive=@($archive);editor_processes=$processes;
    true_ue_acquisition=$false;calibration_verified=$false;created_assets=@();
    boundary='Read-only resource inspection; no renderer, scene, authority or flight launched'
} | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $output -Encoding utf8
Write-Output "Resources: $($identities.Count); archive matches: $(@($archive | Where-Object matches).Count)/$($archive.Count); editor processes: $($processes.Count)"
