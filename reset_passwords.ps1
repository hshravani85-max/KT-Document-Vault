Set-Location -Path "C:\KT_Vault_V3"
$py = "C:\Users\Admin\AppData\Local\Python\pythoncore-3.14-64\python.exe"
if (Test-Path $py) {
    & $py reset_vault_passwords.py
} else {
    python reset_vault_passwords.py
}