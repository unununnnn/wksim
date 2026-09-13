param(
    [Parameter(Mandatory=$true)][ValidateSet('arducopter','px4')][string]$Stack,
    [Parameter(Mandatory=$true)][string]$RunId,
    [Parameter(Mandatory=$true)][string]$OutputRoot,
    [Parameter(Mandatory=$true)][string]$Output,
    [string]$ColdResetFrom,
    [string]$Python='D:/date/miniconda/python.exe',
    [string]$Stage='E:/ue5.5/build/wksim-native-hex-20260909-01',
    [string]$Engine='E:/ue5.5/files/UE_5.5/Engine/Binaries/Win64/UnrealEditor.exe',
    [string]$AuditRunner
)
$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
$arguments=@('-B',(Join-Path $PSScriptRoot 'audit_hex_live.py'),'run','--stack',$Stack,
    '--run-id',$RunId,'--output-root',$OutputRoot,'--output',$Output,'--stage',$Stage,'--engine',$Engine)
if ($ColdResetFrom) { $arguments+=@('--cold-reset-from',$ColdResetFrom) }
if ($AuditRunner) { $arguments+=@('--audit-runner',$AuditRunner) }
Push-Location $repo
try { & $Python @arguments; $result=$LASTEXITCODE }
finally { Pop-Location }
# 0 complete; 2 Actor checks passed but rendered-image review remains; 1 rejected.
exit $result
