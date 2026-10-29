import re

with open('app.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Add file-based tracing to see what's really happening
tracer = """
import time
import json

with open('nav_trace.log', 'a') as f:
    f.write(f"\\n--- {time.time()} ---\\n")
    f.write(f"Query Params: {dict(st.query_params)}\\n")
    
    # Dump session state safely
    safe_state = {}
    for k, v in st.session_state.items():
        if isinstance(v, (str, int, float, bool)):
            safe_state[k] = v
    f.write(f"Session State: {json.dumps(safe_state)}\\n")
"""

# Put it right after init_db()
text = text.replace("init_db()", "init_db()\n" + tracer)

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(text)

print("Tracer added.")
