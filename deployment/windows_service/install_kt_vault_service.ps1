# =====================================================================
# KHANNA TRAVELS — KT VAULT V3
# Windows Service Installer Script (Using NSSM - Non-Sucking Service Manager)
# Status: READY FOR CONFIGURATION (Run by IT Administrator)
# =====================================================================

param(
    [string]$ServiceName = "KTVaultV3",
    [string]$AppRoot = "C:\KT_Vault_V3",
    [string]$PythonExe = "C:\Users\Admin\AppData\Local\Python\pythoncore-3.14-64\python.exe",
    [string]$NssmExe = "C:\KT_Vault_V3\tools\nssm.exe"
)

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "KT VAULT V3 - WINDOWS SERVICE INSTALLATION" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Administrator Privilege Check
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error "This script requires elevated Administrator privileges. Please re-run in an elevated PowerShell session."
    exit 1
}

# 2. Path Validation
if (-not (Test-Path $AppRoot)) {
    Write-Error "AppRoot not found at: $AppRoot"
    exit 1
}
if (-not (Test-Path $PythonExe)) {
    Write-Error "Python executable not found at: $PythonExe"
    exit 1
}

# 3. NSSM Verification
if (-not (Test-Path $NssmExe)) {
    Write-Warning "NSSM executable not found at $NssmExe."
    Write-Host "Please download NSSM from https://nssm.cc/ and place nssm.exe in C:\KT_Vault_V3\tools\"
    Write-Host "Alternative manual command:"
    Write-Host "  sc.exe create $ServiceName binPath= `"$PythonExe -m streamlit run $AppRoot\app.py --server.port=8501 --server.address=127.0.0.1`" start= auto"
    exit 0
}

# 4. Service Configuration
$StreamlitArgs = "-m streamlit run `"$AppRoot\app.py`" --server.port=8501 --server.address=127.0.0.1 --server.headless=true"

Write-Host "Configuring service '$ServiceName'..."
& $NssmExe install $ServiceName $PythonExe $StreamlitArgs
& $NssmExe set $ServiceName AppDirectory $AppRoot
& $NssmExe set $ServiceName DisplayName "Khanna Travels KT Vault V3 Document Service"
& $NssmExe set $ServiceName Description "Secure Customer Travel Document Vault with AES-256-GCM and Windows DPAPI."
& $NssmExe set $ServiceName Start SERVICE_AUTO_START

# Logging
$LogDir = Join-Path $AppRoot "logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
& $NssmExe set $ServiceName AppStdout "$LogDir\service_stdout.log"
& $NssmExe set $ServiceName AppStderr "$LogDir\service_stderr.log"

# Recovery options: restart on crash
& $NssmExe set $ServiceName AppRestartDelay 5000

Write-Host "Service '$ServiceName' installed successfully." -ForegroundColor Green
Write-Host "To start: Start-Service $ServiceName"
Write-Host "To verify: & '$PythonExe' '$AppRoot\deployment\health_check.py'"
