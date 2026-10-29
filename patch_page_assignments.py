import os
import glob
import re

files_to_patch = glob.glob("pages/*.py")

for filepath in files_to_patch:
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # We want to replace lines like:
    # st.query_params.page = "customer_workspace"
    # with:
    # st.session_state['nav_page'] = "customer_workspace"
    # st.query_params.page = "customer_workspace"
    
    # Only replace if st.session_state['nav_page'] is not already there!
    # Pattern looks for optional whitespace, then st.query_params.page = <value>
    
    def replacer(match):
        indent = match.group(1)
        assignment = match.group(2) # e.g. "customer_workspace"
        
        # Build the replacement
        return f"{indent}st.session_state['nav_page'] = {assignment}\n{indent}st.query_params.page = {assignment}"
    
    # Negative lookbehind to ensure we don't double patch
    # But negative lookbehind with variable length is hard in python regex.
    # Let's just do a simple replace and fix the ones that need it.
    
    lines = content.split('\n')
    new_lines = []
    for i, line in enumerate(lines):
        if 'st.query_params.page =' in line and 'st.session_state' not in line:
            m = re.match(r'^(\s*)st\.query_params\.page\s*=\s*(.+)$', line)
            if m:
                indent = m.group(1)
                val = m.group(2)
                new_lines.append(f"{indent}st.session_state['nav_page'] = {val}")
                new_lines.append(line)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)
            
    new_content = '\n'.join(new_lines)
    
    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Patched {filepath}")

print("Done patching page assignments.")
