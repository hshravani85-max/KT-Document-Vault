import re

with open("pages/document_review.py", "r", encoding="utf-8") as f:
    content = f.read()

history_block = '''
    st.write("### Verification History")
    conn = database.get_connection()
    hist = conn.execute("SELECT * FROM document_history WHERE document_id = ? ORDER BY timestamp DESC", (d['id'],)).fetchall()
    conn.close()
    if hist:
        for h in hist:
            st.markdown(f"<small>**{h['timestamp'][:19]}** - {h['event_type']} - Actor: {h['actor']} - Reason: {h['reason']}</small>", unsafe_allow_html=True)
    else:
        st.write("<small>No history available.</small>", unsafe_allow_html=True)

    if status == 'Verified':
        if st.session_state.get(f'reopen_mode_{doc_id}'):
            st.warning("You are requesting to reopen a VERIFIED document. This will invalidate its current verification and recalculate trip readiness.")
            reason = st.text_input("Mandatory Correction Reason (Required)")
            cr1, cr2 = st.columns(2)
            if cr1.button("Cancel", key=f"cancel_reopen_{doc_id}"):
                st.session_state[f'reopen_mode_{doc_id}'] = False
                st.rerun()
            if cr2.button("Confirm Reopen", key=f"confirm_reopen_{doc_id}"):
                if not reason.strip():
                    st.error("Correction reason is required.")
                else:
                    try:
                        import services
                        services.reopen_document(doc_id, reason, st.session_state.get('session_token'))
                        st.session_state[f'reopen_mode_{doc_id}'] = False
                        st.success("Document reopened successfully.")
                        st.rerun()
                    except PermissionError as e:
                        st.error(str(e))
                    except Exception as e:
                        st.error(f"Error reopening: {str(e)}")
        else:
            if st.button("Reopen for Review", key=f"reopen_btn_{doc_id}"):
                st.session_state[f'reopen_mode_{doc_id}'] = True
                st.rerun()
'''

if "### Verification History" not in content:
    new_content = content.replace('    st.write("### Extracted Information")', history_block + '\n    st.write("### Extracted Information")')
    with open("pages/document_review.py", "w", encoding="utf-8") as f:
        f.write(new_content)
    print("Restored Verification History block with keys.")
else:
    print("Verification History already exists.")
