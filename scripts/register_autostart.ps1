$ErrorActionPreference = 'Stop'

# Derive the project root from this script so the task works when the folder moves.
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$PythonW = Join-Path $ProjectRoot '.venv\Scripts\pythonw.exe'
$Launcher = Join-Path $ProjectRoot 'scripts\launcher.py'
$CurrentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

if (-not (Test-Path -LiteralPath $PythonW -PathType Leaf)) {
    throw "Python windowed interpreter not found: $PythonW"
}
if (-not (Test-Path -LiteralPath $Launcher -PathType Leaf)) {
    throw "JARVIS launcher not found: $Launcher"
}

# Keep the script path quoted because the project folder may contain spaces.
$Action = New-ScheduledTaskAction `
    -Execute $PythonW `
    -Argument ('"{0}"' -f $Launcher) `
    -WorkingDirectory $ProjectRoot

# Run at sign-in for the current user, delayed to allow the desktop to load.
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $CurrentUser
$Trigger.Delay = 'PT30S'

# Run interactively without elevation.
$Principal = New-ScheduledTaskPrincipal `
    -UserId $CurrentUser `
    -LogonType Interactive `
    -RunLevel Limited

# Allow battery operation and retry up to three failures at one-minute intervals.
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -StartWhenAvailable

# Replace any existing task with the same name.
Register-ScheduledTask `
    -TaskName 'JARVIS' `
    -Action $Action `
    -Trigger $Trigger `
    -Principal $Principal `
    -Settings $Settings `
    -Description 'Start the local JARVIS assistant at user sign-in.' `
    -Force | Out-Null

Write-Output 'Registered scheduled task JARVIS.'
