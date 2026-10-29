with open('pages/smart_intake.py', 'r', encoding='utf-8') as f:
    si = f.read()

# Fix create_customer
si = si.replace("services.create_customer(c_name.strip(, st.session_state.get('session_token')), mobile=c_mob.strip() if c_mob.strip() else None, email=c_em.strip() if c_em.strip() else None, customer_type=c_type)",
                "services.create_customer(c_name.strip(), mobile=c_mob.strip() if c_mob.strip() else None, email=c_em.strip() if c_em.strip() else None, customer_type=c_type, session_token=st.session_state.get('session_token'))")
                
# Fix add_traveller
si = si.replace("services.add_traveller(\n                            customer_id=c_id,\n                            full_name=name.strip(, st.session_state.get('session_token')),\n                            traveller_type=ttype\n                        )",
                "services.add_traveller(\n                            customer_id=c_id,\n                            full_name=name.strip(),\n                            traveller_type=ttype,\n                            session_token=st.session_state.get('session_token')\n                        )")
# Just in case the formatting doesn't exactly match:
si = si.replace("full_name=name.strip(, st.session_state.get('session_token'))", "full_name=name.strip(), session_token=st.session_state.get('session_token')")

# Fix create_trip
si = si.replace("services.create_trip(c_id, t_name.strip(, st.session_state.get('session_token')), t_dest.strip(), s_str, e_str, \"Holiday\", \"International Package\", \"Operations\", t_ids)",
                "services.create_trip(c_id, t_name.strip(), t_dest.strip(), s_str, e_str, \"Holiday\", \"International Package\", \"Operations\", t_ids, session_token=st.session_state.get('session_token'))")

with open('pages/smart_intake.py', 'w', encoding='utf-8') as f:
    f.write(si)
print("smart_intake.py syntax fixed.")
