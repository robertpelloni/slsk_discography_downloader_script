# Install Discography Downloader as a scheduled task
# Run: powershell -ExecutionPolicy Bypass -File install_service.ps1

$TaskName = "DiscographyDownloader"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = Join-Path $ScriptDir "venv\Scripts\python.exe"
$WatchdogPy = Join-Path $ScriptDir "watchdog.py"

# Remove existing task if present
schtasks /delete /tn $TaskName /f 2>$null

# Create action
$Action = New-ScheduledTaskAction -Execute $PythonExe -Argument "`"$WatchdogPy`"" -WorkingDirectory $ScriptDir

# Trigger: at user logon
$Trigger = New-ScheduledTaskTrigger -AtLogOn

# Settings: restart on failure, run even if not on AC power
$Settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

# Principal: run as current user with highest privileges
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -RunLevel Highest -LogonType S4U

# Register the task
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Force

if ($?) {
    Write-Host "Task '$TaskName' installed successfully." -ForegroundColor Green
    Write-Host ""
    Write-Host "To start right now:      schtasks /run /tn $TaskName"
    Write-Host "To stop:                  schtasks /end /tn $TaskName"
    Write-Host "To check status:          schtasks /query /tn $TaskName"
    Write-Host "To remove:                schtasks /delete /tn $TaskName /f"
    
    # Start it immediately
    Write-Host ""
    Write-Host "Starting task now..." -ForegroundColor Yellow
    schtasks /run /tn $TaskName
} else {
    Write-Host "Failed to install task. Try running as Administrator." -ForegroundColor Red
}

pause
