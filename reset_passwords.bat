@echo off
title KT Vault V3 - Local Password Reset
cd /d C:\KT_Vault_V3
if exist "C:\Users\Admin\AppData\Local\Python\pythoncore-3.14-64\python.exe" (
    "C:\Users\Admin\AppData\Local\Python\pythoncore-3.14-64\python.exe" reset_vault_passwords.py
) else (
    python reset_vault_passwords.py
)
pause