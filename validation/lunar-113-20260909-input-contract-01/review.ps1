$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Push-Location $root
try {
    $paths = @('Simulator/wksim_core/model.py','Simulator/wksim_core/model.cpp',
        'Simulator/wksim_core/model_parameters.py','Simulator/wksim_core/worker.py',
        'Simulator/wksim_core/joint.py','Simulator/wksim_runtime/replay.py',
        'tools/quad_model_parameters.py','tools/major_model_recorder.cpp',
        'docs/2026-09-09-quad-parameters-closure-review.md',
        'docs/2026-09-09-joint-step-acceptance-review.md',
        'docs/plan/46-reexecution-contract.md',
        'validation/quad-parameters-native-20260909-b/baseline.jsonl',
        'validation/quad-parameters-native-20260909-b/baseline.json',
        'validation/quad-parameters-native-20260909-b/baseline.build.json')
    $hashes = [ordered]@{}
    foreach ($p in $paths) { $hashes[$p] = (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLower() }
    $rows = @(Get-Content -LiteralPath $paths[11] | ForEach-Object { $_ | ConvertFrom-Json })
    $ticks = @($rows | Where-Object { $null -ne $_.tick })
    $continuous = $ticks.Count -eq 500
    for ($i=0; $i -lt $ticks.Count; $i++) {
        if ($ticks[$i].tick -ne ($i+1) -or $ticks[$i].output120.Count -ne 120) { $continuous=$false }
    }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive='E:/rflysimtools/RflySimAPIs/4.RflySimModel/1.BasicExps/e0_MinModelTemp/MulticopterModel.zip'
    $zip=[IO.Compression.ZipFile]::OpenRead($archive)
    $members=[ordered]@{}
    try {
        foreach ($name in @('Exp1_MinModelTemp.cpp','Exp1_MinModelTemp.h')) {
            $entry=$zip.GetEntry('e0_MinModelTemp/Exp1_MinModelTemp_ert_rtw/'+$name)
            $stream=$entry.Open()
            try { $sha=[Security.Cryptography.SHA256]::Create(); $members[$name]=[Convert]::ToHexString($sha.ComputeHash($stream)).ToLower(); $sha.Dispose() }
            finally { $stream.Dispose() }
        }
    } finally { $zip.Dispose() }
    $terminal=@($rows | Where-Object { $_.kind -eq 'terminal' -or $_.source_status -eq 'complete' }).Count
    $checks=[ordered]@{
        source_has_500_contiguous_output120=$continuous
        source_has_16_fixed_commands=($rows[0].commands.Count -eq 16)
        source_missing_terminal=($terminal -eq 0)
        source_missing_event_declaration=($null -eq $rows[0].event_policy)
        raw_cpp_matches_pin=($members['Exp1_MinModelTemp.cpp'] -eq 'a35d7c8f39c94f2db8c27b19affee5b66c1b001c63ded334ba83c99f8be54019')
        raw_header_matches_pin=($members['Exp1_MinModelTemp.h'] -eq '2d89ad1b492c5e70e80682a9f53896e0538260946a0180a2ca44e500ba1589bd')
        planned_cli_not_implemented=(-not (Test-Path tools/reexecute_physics.py))
    }
    $passed=@($checks.Values | Where-Object { -not $_ }).Count -eq 0
    [ordered]@{ issue=113; head=(git rev-parse HEAD); branch=(git branch --show-current);
        checks=$checks; passed=$passed; check_count=$checks.Count; skipped=0;
        source_result='insufficient_recording'; source_lines=$rows.Count; terminal_count=$terminal;
        missing=@('terminal','event_policy'); source_sha256=$hashes;
        archive_sha256=(Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLower();
        generated_member_sha256=$members; model_initialized=$false; reexecution_run=$false
    } | ConvertTo-Json -Depth 8
    if (-not $passed) { exit 1 }
} finally { Pop-Location }
