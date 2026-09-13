param([Parameter(Mandatory=$true)][string]$Executable,[Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference='Stop'
$directory=(Resolve-Path -LiteralPath $OutputDirectory).Path
$gui=Start-Process -FilePath $Executable -ArgumentList '--logging:Comms.LinkManager,Vehicle.MultiVehicleManager','--log-output' -WindowStyle Normal -PassThru -RedirectStandardOutput (Join-Path $directory 'qgc.stdout.log') -RedirectStandardError (Join-Path $directory 'qgc.stderr.log')
$gui | Select-Object Id,StartTime,Path | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $directory 'qgc-owned.json') -Encoding UTF8
$forced=$false
try {
    while(-not $gui.WaitForExit(200)) {
        if(Test-Path -LiteralPath (Join-Path $directory 'qgc.stop')) { break }
    }
} finally {
    if(-not $gui.HasExited) {
        $null=$gui.CloseMainWindow()
        if(-not $gui.WaitForExit(8000)) {
            $forced=$true
            $gui.Kill()
            $gui.WaitForExit()
        }
    }
    @{pid=$gui.Id;returncode=$gui.ExitCode;forced_close=$forced} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $directory 'qgc-exit.json') -Encoding UTF8
}
