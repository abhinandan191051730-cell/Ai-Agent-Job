# scheduling/windows_task.ps1
#
# Windows Task Scheduler setup script.
# Run this script as Administrator to create a scheduled task.
#
# The task runs main.py --apply every 4 hours with lock-file protection.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scheduling/windows_task.ps1
#
# To remove the task later:
#   Unregister-ScheduledTask -TaskName "AiAgent-Job" -Confirm:$false

$TaskName = "AiAgent-Job"
$ScriptDir = Split-Path -Parent $PSScriptRoot
$PythonExe = "python"  # or the full path to your python.exe
$ScriptPath = Join-Path $ScriptDir "main.py"
$LogDir = Join-Path $ScriptDir "data" "logs"
$LockFile = Join-Path $ScriptDir "data" "agent.lock"
$PidFile = Join-Path $ScriptDir "data" "agent.pid"

# Ensure log directory exists
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

# Task action: runs a wrapper PowerShell command that checks the lock file first
$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument @"
-ExecutionPolicy Bypass -Command "
`$LockFile = '$LockFile';
`$PidFile = '$PidFile';
if (Test-Path `$LockFile) {
    Write-Host `"Lock file exists. Skipping run.`";
    exit 0;
}
`$null = New-Item -Force -Path `$PidFile -Value `$pid;
try {
    `$null = New-Item -Force -Path `$LockFile;
    Set-Location '$ScriptDir';
    & '$PythonExe' '$ScriptPath' --apply 2>&1 | Out-File -FilePath '$LogDir\scheduled.log' -Append;
} finally {
    Remove-Item -Force `$LockFile -ErrorAction SilentlyContinue;
    Remove-Item -Force `$PidFile -ErrorAction SilentlyContinue;
}
"
"@

# Trigger: every 4 hours, starting at 8 AM
$Trigger = New-ScheduledTaskTrigger -Daily -At 08:00AM -RepetitionInterval (New-TimeSpan -Hours 4) -RepetitionDuration (New-TimeSpan -Days 365)

# Run whether user is logged in or not
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

# Register the task
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -RunLevel Limited -Force

Write-Host "Task '$TaskName' created successfully."
Write-Host "It will run '$PythonExe main.py --apply' every 4 hours starting at 8:00 AM."
