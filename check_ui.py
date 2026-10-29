with open('ui_helpers.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
for i, line in enumerate(lines):
    if 'Staff Member' in line:
        for j in range(max(0, i-5), min(len(lines), i+5)):
            print(f"{j}: {lines[j].encode('ascii', 'ignore').decode('ascii').rstrip()}")
