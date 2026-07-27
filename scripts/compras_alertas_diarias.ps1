$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$LogDirectory = Join-Path $ProjectRoot "instance"
$LogFile = Join-Path $LogDirectory "compras_alertas.log"

if (-not (Test-Path $Python)) {
    throw "No se encontró el entorno virtual del ERP en $Python"
}

New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null
Set-Location $ProjectRoot

$Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$Output = & $Python -m flask --app app compras-alertas --force 2>&1
$ExitCode = $LASTEXITCODE
Add-Content -Path $LogFile -Value "[$Timestamp] $($Output -join ' ')"

if ($ExitCode -ne 0) {
    throw "La revisión de alertas terminó con código $ExitCode. Revisa $LogFile"
}

