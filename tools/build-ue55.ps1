param([string]$Stage)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$engine = 'E:/ue5.5/files/UE_5.5'
$reference = Join-Path $repo 'work/dependencies/ue55/Content'
if (-not (Test-Path -LiteralPath $reference)) { throw 'Missing project-owned UE content: see docs/project-isolation.md' }
if (-not $Stage) { $Stage = 'E:/ue5.5/build/wksim-native-' + [guid]::NewGuid().ToString('N').Substring(0, 8) }
$stageFull = [IO.Path]::GetFullPath($Stage)
if (-not $stageFull.StartsWith('E:\ue5.5\build\wksim-native-', [StringComparison]::OrdinalIgnoreCase)) { throw 'Unexpected staging directory' }
if ((Split-Path -Parent $stageFull) -ne 'E:\ue5.5\build') { throw 'Stage must be a direct child of the build directory' }
if (Test-Path -LiteralPath $stageFull) {
    $stageItem = Get-Item -LiteralPath $stageFull -Force
    if (-not $stageItem.PSIsContainer -or ($stageItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
        @(Get-ChildItem -LiteralPath $stageFull -Force).Count -gt 0) {
        throw "Stage must be new or empty (and not a link): $stageFull"
    }
}
New-Item -ItemType Directory -Path $stageFull -Force | Out-Null
$evidence = Join-Path $repo ('validation/ue55-build-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $evidence | Out-Null
Copy-Item -LiteralPath (Join-Path $repo 'Simulator/ue55/WksimVisual.uproject') -Destination $stageFull -Force
foreach ($folder in @('Config','Source','Plugins')) {
    Copy-Item -LiteralPath (Join-Path $repo "Simulator/ue55/$folder") -Destination $stageFull -Recurse -Force
}
if (-not (Test-Path -LiteralPath (Join-Path $stageFull 'Content'))) {
    Copy-Item -LiteralPath $reference -Destination (Join-Path $stageFull 'Content') -Recurse
}
$referencePlugin = Split-Path -Parent $reference
foreach ($asset in @('Materials/MI_RefHexX_Body.uasset','Textures/T_RefHexX_Surface.uasset')) {
    $relative = 'Plugins/AeroTwinVisualRuntime/Content/Vehicles/RefHexX/' + $asset
    $destination = Join-Path $stageFull $relative
    if (-not (Test-Path -LiteralPath $destination)) {
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
        Copy-Item -LiteralPath (Join-Path $referencePlugin $relative) -Destination $destination
    }
}
$project = Join-Path $stageFull 'WksimVisual.uproject'
$p450Source = Join-Path $repo 'Simulator/ue55/Content/Wksim/P450'
$p450Manifest = Join-Path $repo 'Simulator/ue55/p450-visual-manifest.json'
if (-not (Test-Path -LiteralPath $p450Source) -or -not (Test-Path -LiteralPath $p450Manifest)) { throw 'Prepare/import the pinned P450 assets before building' }
New-Item -ItemType Directory -Path (Join-Path $stageFull 'Content/Wksim') -Force | Out-Null
Copy-Item -LiteralPath $p450Source -Destination (Join-Path $stageFull 'Content/Wksim/P450') -Recurse
Copy-Item -LiteralPath $p450Manifest -Destination $stageFull
$assetPaths = @('p450-visual-manifest.json') + @(Get-ChildItem -LiteralPath $p450Source -File | Sort-Object Name | ForEach-Object { 'Content/Wksim/P450/' + $_.Name })
$assetInputs = @(foreach ($relative in $assetPaths) {
    $sourceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $repo "Simulator/ue55/$relative")).Hash.ToLowerInvariant()
    $stagingHash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $stageFull $relative)).Hash.ToLowerInvariant()
    if ($sourceHash -ne $stagingHash) { throw "Asset changed during staging: $relative" }
    [ordered]@{path=$relative; source_sha256=$sourceHash; staging_sha256=$stagingHash}
})
$inputPaths = @(
    'Source/WksimVisual/WksimVisualGameMode.cpp',
    'Source/WksimVisual/WksimVisualGameMode.h',
    'Source/WksimVisual/WksimVisual.Build.cs',
    'Source/WksimVisual.Target.cs',
    'Source/WksimVisualEditor.Target.cs',
    'Config/DefaultEngine.ini',
    'Plugins/AeroTwinVisualRuntime/AeroTwinVisualRuntime.uplugin',
    'WksimVisual.uproject'
)
# Capture the source/staging identity before invoking the compiler.
$buildInputs = @(foreach ($relative in $inputPaths) {
    $sourceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $repo "Simulator/ue55/$relative")).Hash.ToLowerInvariant()
    $stagingHash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $stageFull $relative)).Hash.ToLowerInvariant()
    if ($sourceHash -ne $stagingHash) { throw "Source changed during staging: $relative" }
    [ordered]@{path=$relative; source_sha256=$sourceHash; staging_sha256=$stagingHash}
})
$engineVersionPath = Join-Path $engine 'Engine/Build/Build.version'
$engineVersion = Get-Content -LiteralPath $engineVersionPath -Raw | ConvertFrom-Json
$engineVersionHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $engineVersionPath).Hash.ToLowerInvariant()
$buildCommand = Join-Path $engine 'Engine/Build/BatchFiles/Build.bat'
$buildArgv = @('WksimVisualEditor', 'Win64', 'Development', $project, '-WaitMutex', '-NoHotReloadFromIDE', '-NoLiveCoding', '-UTF8Output')
$buildLog = Join-Path $evidence 'build.log'
$manifest = [ordered]@{stage=$stageFull; project=$project; evidence=$evidence; engine=$engine; reference_content=$reference; utc=[DateTime]::UtcNow.ToString('o')}
$manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $evidence 'manifest.json') -Encoding utf8
Write-Output ($manifest | ConvertTo-Json -Compress)
$buildTimer = [Diagnostics.Stopwatch]::StartNew()
& $buildCommand @buildArgv 2>&1 | Tee-Object -FilePath $buildLog
$buildExitCode = $LASTEXITCODE
$buildTimer.Stop()
if ($buildExitCode -ne 0) { throw "UE build failed: $buildExitCode; $evidence" }
foreach ($inputEntry in @($buildInputs) + @($assetInputs)) {
    $currentHash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $stageFull $inputEntry.path)).Hash.ToLowerInvariant()
    if ($currentHash -ne $inputEntry.staging_sha256) { throw "Staged input changed during build: $($inputEntry.path)" }
}
$binary = Join-Path $stageFull 'Binaries/Win64/UnrealEditor-WksimVisual.dll'
$candidate = [ordered]@{
    project=$project
    binary=$binary
    binary_sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $binary).Hash.ToLowerInvariant()
    build_exit_code=$buildExitCode
    build_seconds=$buildTimer.Elapsed.TotalSeconds
    build_inputs=$buildInputs
    asset_inputs=$assetInputs
    visual_model='prometheus_p450_visual_v1'
    engine=$engine
    engine_version_path=$engineVersionPath
    engine_version=$engineVersion
    engine_version_sha256=$engineVersionHash
    build_command=$buildCommand
    build_argv=$buildArgv
    build_log=$buildLog
    evidence=$evidence
    live_ue_run=$false
    utc=[DateTime]::UtcNow.ToString('o')
}
# Create once, then mark read-only: subsequent builds must use new evidence.
$candidatePath = Join-Path $evidence 'candidate-manifest.json'
$candidateBytes = [Text.UTF8Encoding]::new($false).GetBytes(($candidate | ConvertTo-Json -Depth 10))
$candidateFile = [IO.File]::Open($candidatePath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
try { $candidateFile.Write($candidateBytes, 0, $candidateBytes.Length) }
finally { $candidateFile.Dispose() }
(Get-Item -LiteralPath $candidatePath).IsReadOnly = $true
Write-Output "Candidate manifest: $candidatePath"
