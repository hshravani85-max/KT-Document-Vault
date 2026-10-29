with open('pages/document_review.py', 'r', encoding='utf-8') as f:
    content = f.read()

import re

# We will just replace everything from "c1, c2, c3 = st.columns(3)" to the end of the action block
match = re.search(r'c1, c2, c3 = st\.columns\(3\).*?(?=st\.markdown)', content, re.DOTALL)

if match:
    new_buttons = """c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("Verify Document", type="primary", use_container_width=True):
                conn = database.get_connection()
                conn.execute("UPDATE documents SET status = 'Verified' WHERE id = ?", (d['id'],))
                if d.get('trip_id'):
                    conn.execute("INSERT INTO activity (trip_id, description) VALUES (?, ?)", (d['trip_id'], f"Document {d['requirement_name']} Verified"))
                else:
                    conn.execute("INSERT INTO activity (customer_id, description) VALUES (?, ?)", (d['customer_id'], f"Document {d['requirement_name']} Verified"))
                conn.commit()
                conn.close()
                st.rerun()
                
        with c2:
            with st.popover("Reject", use_container_width=True):
                reason = st.selectbox("Reason for Rejection", ["Wrong traveller", "Unreadable", "Incorrect document", "Expired", "Incomplete", "Other"])
                if st.button("Confirm Reject"):
                    conn = database.get_connection()
                    conn.execute("UPDATE documents SET status = 'Rejected' WHERE id = ?", (d['id'],))
                    if d.get('trip_id'):
                        conn.execute("INSERT INTO activity (trip_id, description) VALUES (?, ?)", (d['trip_id'], f"Document {d['requirement_name']} Rejected: {reason}"))
                    else:
                        conn.execute("INSERT INTO activity (customer_id, description) VALUES (?, ?)", (d['customer_id'], f"Document {d['requirement_name']} Rejected: {reason}"))
                    conn.commit()
                    conn.close()
                    st.rerun()
                    
        with c3:
            with st.popover("Request Re-upload", use_container_width=True):
                re_reason = st.selectbox("Reason for Re-upload", ["Unreadable / Blurry", "Missing Pages", "Wrong Document", "Other"])
                if st.button("Confirm Request"):
                    conn = database.get_connection()
                    conn.execute("UPDATE documents SET status = 'Re-upload Required' WHERE id = ?", (d['id'],))
                    if d.get('trip_id'):
                        conn.execute("INSERT INTO activity (trip_id, description) VALUES (?, ?)", (d['trip_id'], f"Re-upload requested for {d['requirement_name']}: {re_reason}"))
                    else:
                        conn.execute("INSERT INTO activity (customer_id, description) VALUES (?, ?)", (d['customer_id'], f"Re-upload requested for {d['requirement_name']}: {re_reason}"))
                    conn.commit()
                    conn.close()
                    st.rerun()
                    
        """
    content = content.replace(match.group(0), new_buttons)
    with open('pages/document_review.py', 'w', encoding='utf-8') as f:
        f.write(content)
