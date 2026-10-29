import re

with open('pages/document_review.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update verification handling
old_verify_action = """        if c1.button("Verify Document", type="primary"):
            verify_document(d['id'])
            # Add activity
            conn = database.get_connection()"""

new_verify_action = """        if c1.button("Verify Document", type="primary"):
            try:
                verify_document(d['id'])
                # Add activity
                conn = database.get_connection()
            except Exception as e:
                st.error(str(e))
                st.stop()
            conn = database.get_connection()"""

content = content.replace(old_verify_action, new_verify_action)


# 2. Add Reopen action and Verification History
# Right after: st.markdown(f"**Status:** {render_badge(status)}", unsafe_allow_html=True)
status_block = "        st.markdown(f\"**Status:** {render_badge(status)}\", unsafe_allow_html=True)"
reopen_and_history = """
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
            if cr1.button("Cancel"):
                st.session_state[f'reopen_mode_{doc_id}'] = False
                st.rerun()
            if cr2.button("Confirm Reopen"):
                if not reason.strip():
                    st.error("Correction reason is required.")
                else:
                    try:
                        import services
                        services.reopen_document(doc_id, reason, 'Staff Member (Demo)')
                        st.session_state[f'reopen_mode_{doc_id}'] = False
                        st.success("Document reopened successfully.")
                        st.rerun()
                    except PermissionError as e:
                        st.error(str(e))
                    except Exception as e:
                        st.error(f"Error reopening: {str(e)}")
        else:
            if st.button("Reopen for Review"):
                st.session_state[f'reopen_mode_{doc_id}'] = True
                st.rerun()
"""

# Find the exact string in content
if "st.markdown(f\"**Status:** {render_badge(status)}\", unsafe_allow_html=True)" in content:
    content = content.replace(
        "st.markdown(f\"**Status:** {render_badge(status)}\", unsafe_allow_html=True)",
        "st.markdown(f\"**Status:** {render_badge(status)}\", unsafe_allow_html=True)\n" + reopen_and_history
    )
else:
    print("Could not find status badge injection point!")

# For Verified status block, add history there as well
old_verified_block = "        st.markdown('</div>', unsafe_allow_html=True)"
new_verified_block = "        st.markdown('</div>', unsafe_allow_html=True)\n" + reopen_and_history

content = content.replace(old_verified_block, new_verified_block)


with open('pages/document_review.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("document_review.py patched for verification UI.")
