import re

with open('services.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if "user = if not session_token: raise PermissionError('Unauthenticated'); auth_services.require_role(session_token, ['Staff', 'Supervisor', 'Admin'])" in line:
        new_lines.append("    if not session_token: raise PermissionError('Unauthenticated')\n")
        new_lines.append("    user = auth_services.require_role(session_token, ['Staff', 'Supervisor', 'Admin'])\n")
    elif "if not session_token: raise PermissionError('Unauthenticated'); auth_services.require_role(session_token, ['Staff', 'Supervisor', 'Admin'])" in line:
        new_lines.append("    if not session_token: raise PermissionError('Unauthenticated')\n")
        new_lines.append("    auth_services.require_role(session_token, ['Staff', 'Supervisor', 'Admin'])\n")
    else:
        new_lines.append(line)

with open('services.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("services.py correctly fixed.")
