# Elevated Administrator Script: Apply Machine-Wide Windows Inactivity Lock Policy
# Run as Administrator in PowerShell:
# powershell -ExecutionPolicy Bypass -File .\apply_machine_inactivity_lock.ps1

Write-Host "Applying Windows Machine Inactivity Lock Policy (10 minutes / 600 seconds)..."

# 1. Enforce HKLM InactivityTimeoutSecs
Set-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" -Name InactivityTimeoutSecs -Value 600 -Type DWord

# 2. Enforce screen saver security policy in default user profile
Set-ItemProperty -Path "Registry::HKEY_USERS\.DEFAULT\Control Panel\Desktop" -Name ScreenSaveActive -Value "1"
Set-ItemProperty -Path "Registry::HKEY_USERS\.DEFAULT\Control Panel\Desktop" -Name ScreenSaveTimeOut -Value "600"
Set-ItemProperty -Path "Registry::HKEY_USERS\.DEFAULT\Control Panel\Desktop" -Name ScreenSaverIsSecure -Value "1"

Write-Host "Machine-wide policy applied successfully. All interactive sessions will lock after 10 minutes of inactivity."
