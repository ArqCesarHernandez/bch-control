$ErrorActionPreference = "Stop"

$Runner = Join-Path $PSScriptRoot "compras_alertas_diarias.ps1"
if (-not (Test-Path $Runner)) {
    throw "No se encontró el ejecutor de alertas en $Runner"
}

$TaskName = "ERP V2 - Alertas de Compras"
$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Runner`""
$Trigger = New-ScheduledTaskTrigger -Daily -At 7:00AM
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Revisa diariamente requisiciones, entregas y pagos por vencer del ERP V2." `
    -Force | Out-Null

Write-Host "Tarea '$TaskName' instalada para ejecutarse diariamente a las 7:00 AM."

