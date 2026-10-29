import os
import sys
import sqlite3

class DummyContext:
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def __getattr__(self, name): return lambda *a, **kw: DummyContext()

class DummyQuery(dict):
    def get(self, key, default=None): return self.get(key, default)
    def __getattr__(self, name): return self.get(name)
    def __setattr__(self, name, val): self[name] = val
    def __contains__(self, key): return key in self.keys()
    def __delitem__(self, key): super().__delitem__(key)

class DummyST:
    def __init__(self):
        self.query_params = DummyQuery()
    def container(self, *args, **kwargs): return DummyContext()
    def columns(self, *args, **kwargs): return [DummyContext() for _ in args[0]] if isinstance(args[0], (list, tuple)) else [DummyContext()] * args[0]
    def tabs(self, *args, **kwargs): return [DummyContext() for _ in args[0]]
    def form(self, *args, **kwargs): return DummyContext()
    def __getattr__(self, name): return lambda *a, **kw: DummyContext()
    def error(self, msg): print('ST ERROR:', msg)
    def stop(self): pass
    def rerun(self): pass
    def markdown(self, body, **kwargs):
        if 'iframe' in body:
            print('RENDERED PDF IFRAME WITH FILE DATA')
    def button(self, label, *args, **kwargs):
        if 'Back' in label:
            return True
        return False

st = DummyST()
sys.modules['streamlit'] = st

conn = sqlite3.connect('C:/KT_Vault_V3/data/kt_vault_v3.db')
doc_id = conn.execute("SELECT d.id FROM documents d JOIN requirements r ON d.requirement_id = r.id WHERE r.name = 'Travel Insurance'").fetchone()[0]
conn.close()

st.query_params['doc_id'] = doc_id
st.query_params['page'] = 'document_review'

with open('pages/document_review.py', 'r', encoding='utf-8') as f:
    exec(f.read(), {'__name__': '__main__', 'st': st, 'os': os})

print('Successfully rendered doc:', doc_id)
print('doc_id in query params after clicking Back:', 'doc_id' in st.query_params)
