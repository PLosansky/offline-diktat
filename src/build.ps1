$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Python-Umgebung konnte nicht erstellt werden.' }
& .venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Abhängigkeiten konnten nicht installiert werden.' }
# Prefer the exact Python OpenSSL DLLs, including when another OpenSSL exists in System32.
$pythonBase = & .venv\Scripts\python.exe -c 'import sys; print(sys.base_prefix)'
$pythonDlls = Join-Path $pythonBase 'DLLs'
$sslArguments = @()
foreach ($dll in Get-ChildItem -LiteralPath $pythonDlls -File | Where-Object { $_.Name -match '^lib(ssl|crypto).*\.dll$' }) {
    $sslArguments += @('--add-binary', ($dll.FullName + ';.'))
}
# Some Python distributions ship an additional certificate policy file used by ssl.py.
# Preserve it unchanged; do not weaken verification to work around a missing resource.
$certificatePolicy = Join-Path $pythonBase 'Lib/codex-rejected-cas.pem'
if (Test-Path -LiteralPath $certificatePolicy) {
    $sslArguments += @('--add-data', ($certificatePolicy + ';.'))
}
$env:PATH = "$pythonDlls;$env:SystemRoot\System32;$env:SystemRoot;$PSScriptRoot\.venv\Scripts"
& .venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --onedir --name Offline-Diktat --icon dictate.ico --version-file version_info.txt --add-data 'resources;resources' @sslArguments --collect-all sherpa_onnx --hidden-import pynput.keyboard._win32 --hidden-import pynput.mouse._win32 --copy-metadata sounddevice --copy-metadata sherpa-onnx app.py
if ($LASTEXITCODE -ne 0) { throw 'EXE konnte nicht erstellt werden.' }
Copy-Item -LiteralPath resources\LICENSES -Destination dist\Offline-Diktat\LICENSES -Recurse -Force
Copy-Item -LiteralPath LICENSE,THIRD_PARTY.md,README.md,MODELLE.md -Destination dist\Offline-Diktat
Write-Host 'Fertig: dist\Offline-Diktat\Offline-Diktat.exe. Den gesamten Ordner weitergeben. Das Modell ist optional separat unter models abzulegen.'
