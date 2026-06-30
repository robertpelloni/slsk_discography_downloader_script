Start-Process -FilePath "$PSScriptRoot\venv\Scripts\pythonw.exe" `
    -ArgumentList "$PSScriptRoot\watchdog.py" `
    -WorkingDirectory $PSScriptRoot `
    -WindowStyle Hidden
