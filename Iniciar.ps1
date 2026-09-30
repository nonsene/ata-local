param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$LocalPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $LocalPython)) {
    $PreparedPython = Join-Path $PSScriptRoot '..\..\work\venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $PreparedPython) { $LocalPython = (Resolve-Path -LiteralPath $PreparedPython).Path }
    else { throw 'Execute Instalar.ps1 primeiro.' }
}
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:HF_HUB_DISABLE_TELEMETRY = '1'
$env:PYANNOTE_METRICS_ENABLED = '0'
$env:PYTHONUTF8 = '1'
if ($NoBrowser) { & $LocalPython -m ata_local --no-browser }
else { & $LocalPython -m ata_local }
exit $LASTEXITCODE
