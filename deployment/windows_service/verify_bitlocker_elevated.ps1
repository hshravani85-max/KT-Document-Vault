# Elevated Read-Only BitLocker Verification Script for KT Vault V3
# Run in an Elevated (Run as Administrator) PowerShell window:
# powershell -ExecutionPolicy Bypass -File .\verify_bitlocker_elevated.ps1

Write-Host "======================================================================"
Write-Host "KHANNA TRAVELS - KT VAULT V3: ELEVATED BITLOCKER STATUS AUDIT"
Write-Host "======================================================================"

$bde = manage-bde -status C:
Write-Host ($bde | Out-String)

$isEncrypted = ($bde -match "Percentage Encrypted:\s+100(\.\d+)?%") -or ($bde -match "Protection On")
$protectionOn = ($bde -match "Protection Status:\s+Protection On")

Write-Host "--- SUMMARY ---"
Write-Host "Encryption 100% Completed: $isEncrypted"
Write-Host "Protection Active (On):    $protectionOn"

if (-not $protectionOn) {
    Write-Host "`n[ACTION REQUIRED] BitLocker is NOT currently protecting Drive C:."
    Write-Host "To enable BitLocker with TPM and standard recovery protector, execute:"
    Write-Host "  manage-bde -on C: -used"
} else {
    Write-Host "`n[PASS] BitLocker is ACTIVE and protecting Drive C:."
}
Write-Host "======================================================================"
