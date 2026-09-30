$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$LocalPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $LocalPython)) {
    $PreparedPython = Join-Path $PSScriptRoot '..\..\work\venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $PreparedPython) { $LocalPython = (Resolve-Path -LiteralPath $PreparedPython).Path }
    else { throw 'Execute Instalar.ps1 primeiro.' }
}
Remove-Item Env:HF_HUB_OFFLINE -ErrorAction SilentlyContinue
Remove-Item Env:TRANSFORMERS_OFFLINE -ErrorAction SilentlyContinue
& $LocalPython scripts\download_models.py --community
if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel baixar Community-1. Verifique aceite e token.' }
