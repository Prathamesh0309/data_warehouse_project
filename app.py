import time
import streamlit as st
import datetime
from datetime import timedelta
from db import init_db, authenticate_user, create_user, list_events, add_event, register_user_for_event, record_payment, event_stats, get_saved_cards,decrypt_data,add_saved_card, delete_event,get_user_registrations

# Initialize DB (creates DB and tables if missing). Make sure environment variables are set if not using defaults.
init_db()

# st.markdown("""
#     <style>
#     .stApp {
#         background: linear-gradient(135deg, #4a90e2, #d94f4f);
#         background-size: cover;
#     }
#     </style>
# """, unsafe_allow_html=True)


st.set_page_config(page_title="Events Portal", layout="centered")
# --- Helpers ---

def require_login():
    if 'user' not in st.session_state:
        st.session_state['user'] = None


require_login()


def show_login():
    st.title("UofA Events Registration Portal")

    # Initialize page state
    if "page" not in st.session_state:
        st.session_state.page = "login"
    

    if "load_state" not in st.session_state:
        st.session_state.load_state = False

    # ---------- LOGIN PAGE ----------
    if st.session_state.page == "login":
        st.header("Sign in")
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        if st.button("Sign in"):
            user = authenticate_user(email, password)  # backend uses email
            if user:
                st.session_state.user = user
                st.success(f"Signed in as {user['email']}")
                st.rerun()
            else:
                st.warning("Invalid email or password")
                # st.toast("Authentication failed", icon="⚠️")

        st.markdown("---")
        if st.button("Create a new account"):
            st.session_state.page = "signup"
            st.rerun()
            

    # ---------- SIGN-UP PAGE ----------
    elif st.session_state.page == "signup":
        st.header("Sign up")
        cols = st.columns(2)
        with cols[0]:
            first_name = st.text_input("First name", key="signup_first_name")
            phone = st.text_input("Phone", key="signup_phone")
            password = st.text_input("Password", type="password", key="signup_password")
        with cols[1]:
            last_name = st.text_input("Last name", key="signup_last_name")
            email = st.text_input("Email", key="signup_email")
        user_role = st.selectbox("Role", ["user", "admin"], index=0, key="signup_role")

        if st.button("Create account"):
            
            # Basic validations
            if not first_name or not last_name or not phone or not email or not password:
                st.error("All fields are required.")    

            # Email format check
            elif "@" not in email or "." not in email:
                st.error("Invalid email format.")
                

            # Phone must be digits and 10 characters
            elif not phone.isdigit() or len(phone) != 10:
                st.error("Phone number must be exactly 10 digits.")
                
            
            # Password minimum length
            elif len(password) < 6:
                st.error("Password must be at least 6 characters long.")
                
            else:
                try:
                    create_user(first_name, last_name, phone, email, password, user_role)
                    st.success("Account created. Please sign in.")
                    st.session_state.page = "login"
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to create user: {e}")

        st.markdown("---")
        if st.button("Back to login"):
            st.session_state.page = "login"
            st.rerun()
            


def logout():
    st.session_state.user = None
    st.success("Logged out successfully.")
    st.rerun()
    


# --- Pages ---

if not st.session_state.user:
    show_login()
else:
    user = st.session_state.user
    st.sidebar.write(f"Logged in as: {user['first_name']} {user['last_name']}")
    if st.sidebar.button("Logout"):
        logout()
        st.sidebar.markdown("---")
    with st.sidebar.expander("My Saved Cards"):
        cards = get_saved_cards(user['user_id'])
        if cards:
            for c in cards:
                st.write(f"{c['card_holder_name']} (****{c['card_number_decrypted'][-4:]})")
        else:
            st.info("No saved cards yet.")
    
    if st.session_state.get('confirmation'):
        st.success(st.session_state['confirmation'])
        time.sleep(3)
        st.session_state.pop('confirmation') 
        st.rerun()

    #Admin/Organizer Dashboard
    if user['user_role'] in ['Admin', 'Organizer']:
        st.title("Admin Dashboard")
        tab = st.tabs(["Stats & Events", "Add Event"])

        # --- Stats & Events Tab ---
        with tab[0]:
            st.header("Events & Stats")
            events = list_events()
            if not events:
                st.info("No events yet. Add one from 'Add Event' tab.")
            for ev in events:
                col1, col2 = st.columns([3,1])
                with col1:
                    
                    st.markdown(f"### {ev['title']}")
                    st.markdown(f"<p style='color: gray'>{ev['description']}</p>", unsafe_allow_html=True)
                    formatted_date = ev['event_date'].strftime("%d %b %Y")
                    st.write("📅 Date:", formatted_date)
                    st.write("📍 Location:", ev.get('location', 'N/A'))
                    st.write("💵 Price:", f"${ev['price']:.2f}")
                    st.markdown('--------')
                with col2: 
                    stats = event_stats(ev['id'])
                    st.metric("Registrations", stats['registrations'])
                    st.metric("Revenue", f"${stats['revenue']:.2f}")

                    if st.button("🗑️ Delete", key=f"del_{ev['id']}"):
                        st.session_state['confirm_delete'] = ev['id']

                # Confirmation dialog
                if st.session_state.get('confirm_delete') == ev['id']:
                    st.warning(f"Are you sure you want to delete **{ev['title']}**?")
                    col_c1, col_c2 = st.columns(2)
                    with col_c1:
                        if st.button("✅ Yes, delete", key=f"yes_{ev['id']}"):
                            delete_event(ev['id'])
                            st.success(f"Event **{ev['title']}** deleted successfully!")
                            st.session_state.pop('confirm_delete', None)
                            st.rerun()
                    with col_c2:
                        if st.button("❌ Cancel", key=f"cancel_{ev['id']}"):
                            st.session_state.pop('confirm_delete', None)
                            st.info("Delete cancelled.")

        # --- Add Event Tab ---
        with tab[1]:
            st.header("Add Event")
            with st.form("add_event_form"):
                title = st.text_input("Title")
                description = st.text_area("Description")
                date = st.date_input("Event date", value=datetime.date.today())
                event_time = st.time_input("Event time", value=datetime.datetime.now().time())
                location = st.text_input("Location")
                event_type = st.selectbox("Event Type", ["Conference", "Workshop", "Seminar", "Meetup","Technical Talk", 'Health & Wellness', 'Cultural', 'Sports', 'Other'])
                price = st.number_input("Price", min_value=0.0, value=0.0, format="%.2f")
                submitted = st.form_submit_button("Add event")
                if submitted:
                    if not title or not description or not location or not date or not event_time:
                        st.error("All fields are required.")
                    dt = datetime.datetime.combine(date, event_time)
                    add_event(title, description, dt, event_time, location, event_type, user['user_id'],price)
                    st.success("Event added")
                    st.rerun()

    # --- User Dashboard ---
    else:
        tab_events, tab_regs = st.tabs(["Events", "My Registrations"])
        with tab_events:
            if not st.session_state.get('show_payment', False):
                st.title("Events")
                events = list_events()
                if not events:
                    st.info("No events currently available.")
                for ev in events:
                    st.markdown("---")
                    st.markdown(f"### {ev['title']}")
                    st.markdown(f"<p style='color: gray'>{ev['description']}</p>", unsafe_allow_html=True)
                    st.write("📍 Location:", ev.get('location', 'N/A'))
                    formatted_date = ev['event_date'].strftime("%d %b %Y")  
                    st.write("📅 Date:", formatted_date)
                    if isinstance(ev['event_time'], timedelta):
                        total_seconds = int(ev['event_time'].total_seconds())
                        hrs = (total_seconds // 3600) % 24
                        mins = (total_seconds % 3600) // 60
                        event_time = datetime.datetime.strptime(f"{hrs}:{mins}", "%H:%M").time()
                    st.write("🕒 Time:", event_time.strftime("%I:%M %p"))
                    st.write("💵 Price:", f"${ev['price']:.2f}")

                    # Expander for registration
                    with st.expander("Register for this event"):
                        name = st.text_input("Full name", key=f"name_{ev['id']}")
                        contact_email = st.text_input("Contact email", key=f"email_{ev['id']}")
                        if st.button("Proceed to payment", key=f"pay_{ev['id']}"):
                            if not name or not contact_email:
                                st.error("Provide name and email")
                            else:
                                # create registration
                                registration_id = register_user_for_event(user['user_id'], ev['id'])
                                if float(ev['price']) == 0.0:
                                    record_payment(user['user_id'],registration_id)
                                    st.success("Event registered successfully!")
                                else:
                                    # redirect to dummy payment page
                                    st.session_state['registration_id'] = registration_id
                                    st.session_state['payment_amount'] = float(ev['price'])
                                    st.session_state['show_payment'] = True
                                    st.session_state['current_event'] = ev
                                    st.success("Registration info saved. Proceed to payment below.")
                                    st.rerun()
                        
            # --- Payment Section ---
            elif st.session_state.get('show_payment'):
                st.markdown("---")
                ev = st.session_state['current_event']
                amt = st.session_state.get('payment_amount', 0.0)
                st.header(f"Payment for {ev['title']}")
                st.write(f"Amount: ${amt:.2f}")

                # Optional: cancel button to go back
                if st.button("Cancel Payment"):
                    for key in ['registration_id', 'payment_amount', 'show_payment', 'current_event']:
                        st.session_state.pop(key, None)
                    st.rerun()

                saved_cards = get_saved_cards(user['user_id'])

                # Saved Cards Section
                if not saved_cards:
                    st.warning("No saved cards found. Please add a new one.")
                    with st.form("add_card_form"):
                        card_holder = st.text_input("Cardholder Name")
                        card_number = st.text_input("Card Number", type="password")
                        cvv = st.text_input("CVV", type="password")
                        expiry_date = st.text_input("Expiry Date (MM/YY)")
                        save_card = st.checkbox("Save this card for future use", value=True)
                        submitted = st.form_submit_button("Pay")
                        
                        # Process payment
                        if submitted:
                            if not card_holder or not card_number or not cvv:
                                st.error("Please fill all fields.")
                            else:
                                reg_id = st.session_state['registration_id']
                                if save_card:
                                    add_saved_card(user['user_id'], card_holder, card_number, cvv, expiry_date)
                                    saved_cards = get_saved_cards(user['user_id'])
                                    card_id = saved_cards[-1]['card_id']
                                    payment_type = 'Saved'
                                else:
                                    card_id = None
                                    payment_type = 'OneTime'

                                record_payment(user['user_id'], reg_id, card_id, amt, payment_type)
                                st.session_state['confirmation'] = f"Payment ({payment_type}) successful! You are registered."
                                for key in ['registration_id', 'payment_amount', 'show_payment', 'current_event']:
                                    st.session_state.pop(key, None)
                                st.rerun()
                else:
                    st.subheader("Choose a saved card")
                    card_options = [f"{c['card_holder_name']} (****{c['card_number_decrypted'][-4:]})" for c in saved_cards]
                    card_choice = st.selectbox("Select a card", card_options)
                    selected_card = saved_cards[card_options.index(card_choice)]

                    with st.form("payment_form"):
                        use_new = st.checkbox("Use a different card")
                        if use_new:
                            card_holder = st.text_input("Cardholder Name")
                            card_number = st.text_input("Card Number", type="password")
                            cvv = st.text_input("CVV", type="password")
                            expiry_date = st.text_input("Expiry Date (MM/YY)")
                            save_card = st.checkbox("Save this new card for future use", value=False)
                        else:
                            card_holder = selected_card['card_holder_name']
                            card_number = selected_card['card_number_decrypted']
                            cvv = decrypt_data(selected_card['cvv_encrypted'])
                            expiry_date = selected_card['expiry_date']
                            save_card = False

                        submitted = st.form_submit_button("Pay")

                        if submitted:
                            reg_id = st.session_state['registration_id']
                            if use_new and save_card:
                                add_saved_card(user['user_id'], card_holder, card_number, cvv, expiry_date)
                                new_card_id = get_saved_cards(user['user_id'])[-1]['card_id']
                                payment_type = 'Saved'
                            elif use_new:
                                new_card_id = None
                                payment_type = 'OneTime'
                            else:
                                new_card_id = selected_card['card_id']
                                payment_type = 'Saved'

                            record_payment(user['user_id'], reg_id, new_card_id, amt, payment_type)
                            st.session_state['confirmation'] = f"Payment ({payment_type}) successful! You are registered."
                            for key in ['registration_id', 'payment_amount', 'show_payment', 'current_event']:
                                st.session_state.pop(key, None)
                            st.rerun()
        with tab_regs:
            st.title("My Registered Events")

            # Fetch user registrations
            registrations = get_user_registrations(user['user_id'])

            if not registrations:
                st.info("You have not registered for any events yet.")
            else:
                for reg in registrations:
                    st.markdown(f"### {reg['title']}")
                    st.markdown(f"<p style='color: gray'>{ev['description']}</p>", unsafe_allow_html=True)
                    formatted_date = reg['event_date'].strftime("%d %b %Y")  
                    st.write("📅 Date:", formatted_date)
                    if isinstance(ev['event_time'], timedelta):
                        total_seconds = int(ev['event_time'].total_seconds())
                        hrs = (total_seconds // 3600) % 24
                        mins = (total_seconds % 3600) // 60
                        event_time = datetime.datetime.strptime(f"{hrs}:{mins}", "%H:%M").time()
                    st.write("🕒 Time:", event_time.strftime("%I:%M %p"))
                    st.write("💵 Price:", f"${reg['price']:.2f}")
                    st.write("📝 Registration Status:", reg['registration_status'])
                    st.write("💳 Payment Status:", reg['payment_status'])
                    st.markdown("---")



    st.sidebar.markdown("---")
    st.sidebar.write("App powered by Streamlit")
