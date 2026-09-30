param([string]$Python = '', [switch]$SkipModels)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8 = '1'
if ([Environment]::OSVersion.Platform -ne 'Win32NT') { throw 'Esta distribuicao requer Windows 64 bits.' }
if (!$Python) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $Python = & py -3.12 -c "import sys; print(sys.executable)"
        if ($LASTEXITCODE -ne 0) { throw 'Instale Python 3.12 de 64 bits ou informe -Python com o caminho do executavel.' }
    } else { $Python = 'python' }
}
& $Python -c "import sys,struct; assert sys.version_info[:2] == (3,12) and struct.calcsize('P') == 8, 'Use Python 3.12 de 64 bits'"
if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 necessario' }
& $Python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Falha ao criar ambiente' }
$LocalPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
& $LocalPython -m pip install 'torch==2.11.0' 'torchaudio==2.11.0' --index-url https://download.pytorch.org/whl/cu128
if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar CUDA/PyTorch' }
& $LocalPython -m pip install -r requirements-lock.txt
if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar versoes fixadas' }
& $LocalPython -m pip install -e .
if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar dependencias' }
& $LocalPython -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Dependencias incompativeis; consulte a saida acima.' }
if (!$SkipModels) {
    & $LocalPython scripts\download_models.py
    if ($LASTEXITCODE -ne 0) { throw 'Falha no download dos modelos. Execute Instalar.ps1 novamente para retomar.' }
}
Write-Output 'Execute Autorizar-Community.ps1 para concluir a instalacao dos falantes.'
