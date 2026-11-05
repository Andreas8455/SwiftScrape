import sqlite3
import hashlib
import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import time
import stripe 
from urllib.parse import urljoin
import smtplib
from email.mime.text import MIMEText
import random
import string

# --- 1. LOGIN / SIGN UP / REAL EMAIL RESET FUNCTIONS ---
def init_db():
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            username TEXT,
            password TEXT,
            reset_code TEXT
        )
    ''')
    conn.commit()
    conn.close()

def make_hash(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_user(email, password):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute('SELECT password, username FROM users WHERE email = ?', (email,))
    data = c.fetchone()
    conn.close()
    if data and data[0] == make_hash(password):
        return data[1]
    return None

def add_user(email, username, password):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    try:
        c.execute('INSERT INTO users(email, username, password) VALUES (?, ?, ?)', (email, username, make_hash(password)))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False

def set_reset_code(email, code):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute('UPDATE users SET reset_code = ? WHERE email = ?', (code, email))
    conn.commit()
    conn.close()

def verify_and_update_password(email, code, new_password):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute('SELECT reset_code FROM users WHERE email = ?', (email,))
    row = c.fetchone()
    if row and row[0] == code:
        c.execute('UPDATE users SET password = ?, reset_code = NULL WHERE email = ?', (make_hash(new_password), email))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

def send_email_via_smtp(to_email, otp_code):
    try:
        sender_email = st.secrets["email"]["sender"]
        sender_password = st.secrets["email"]["password"]
    except Exception:
        return False, "Email secrets are not configured in Streamlit Cloud."

    subject = "SwiftScrape - Password Reset Verification Code"
    body = f"""Hello,

You requested a password reset for your SwiftScrape account.
Your verification code is: {otp_code}

Enter this code along with your desired new password in the app.

Best regards,
The SwiftScrape Team
"""

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = sender_email
    msg['To'] = to_email

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, to_email, msg.as_string())
        return True, "Verification code sent successfully!"
    except Exception as e:
        return False, f"Email sending error: {e}"

init_db()

# --- 2. PAGE CONFIGURATION ---
st.set_page_config(page_title="SwiftScrape SaaS Pro", page_icon="", layout="wide")

# --- CUSTOM CSS STYLING ---
st.markdown("""
    <style>
    .main {
        background-color: #0e1117;
    }
    .stButton>button {
        width: 100%;
        border-radius: 8px;
        font-weight: 600;
        background-color: #ff4b4b;
        color: white;
    }
    .stButton>button:hover {
        background-color: #ff2b2b;
    }
    div.stLinkButton > a {
        width: 100%;
        border-radius: 8px;
        font-weight: 600;
        background-color: #ff4b4b !important;
        color: white !important;
        text-align: center;
    }
    div.stLinkButton > a:hover {
        background-color: #ff2b2b !important;
        color: white !important;
    }
    </style>
""", unsafe_allow_html=True)

# --- SESSION STATE ---
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if "reset_stage" not in st.session_state:
    st.session_state["reset_stage"] = 1

if "reset_email_target" not in st.session_state:
    st.session_state["reset_email_target"] = ""

# --- AUTH LOGIN / SIGN UP / RESET PORTAL ---
if not st.session_state["logged_in"]:
    st.title("🔐 SwiftScrape - Authentication Portal")
    st.markdown("Please log in with your email, create a new account, or request a password reset.")
    
    tab_login, tab_signup, tab_reset = st.tabs(["🔑 Login", "📝 Sign Up", "🔄 Password Reset"])
    
    with tab_login:
        st.subheader("Sign In to Application")
        with st.form("login_form"):
            email_l = st.text_input("Email")
            pl = st.text_input("Password", type="password")
            submit_login = st.form_submit_button("Log In")
            
            if submit_login:
                uname = check_user(email_l, pl)
                if uname:
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = uname
                    st.session_state["email"] = email_l
                    st.success(f"Welcome back, {uname}!")
                    st.rerun()
                else:
                    st.error("Incorrect email or password.")
                    
    with tab_signup:
        st.subheader("Create a New Account")
        with st.form("signup_form"):
            new_email = st.text_input("Email (Unique)")
            new_user = st.text_input("Username")
            new_pass = st.text_input("Password", type="password")
            submit_signup = st.form_submit_button("Sign Up")
            
            if submit_signup:
                if new_email and new_user and new_pass:
                    if add_user(new_email, new_user, new_pass):
                        st.success("Account created successfully! Please go to the 'Login' tab.")
                    else:
                        st.error("This email is already registered. Try another one.")
                else:
                    st.warning("Please fill in all fields.")
                    
    with tab_reset:
        st.subheader("Reset Your Password")
        
        if st.session_state["reset_stage"] == 1:
            st.markdown("Enter your email address to receive a verification code.")
            with st.form("reset_request_form"):
                reset_email = st.text_input("Account Email")
                submit_code_req = st.form_submit_button("Send Verification Code")
                
                if submit_code_req:
                    if reset_email:
                        conn = sqlite3.connect("users.db")
                        c = conn.cursor()
                        c.execute('SELECT email FROM users WHERE email = ?', (reset_email,))
                        exists = c.fetchone()
                        conn.close()
                        
                        if exists:
                            otp = ''.join(random.choices(string.digits, k=6))
                            set_reset_code(reset_email, otp)
                            success, message = send_email_via_smtp(reset_email, otp)
                            if success:
                                st.session_state["reset_email_target"] = reset_email
                                st.session_state["reset_stage"] = 2
                                st.success("Verification code sent to your email! Please check your inbox.")
                                st.rerun()
                            else:
                                st.error(message)
                        else:
                            st.error("Email not found in our database.")
                    else:
                        st.warning("Please enter your email address.")
        else:
