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
import pandas as pd

# --- 1. LOGIN / SIGN UP / REAL EMAIL RESET & HISTORY FUNCTIONS ---
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
    try:
        c.execute('ALTER TABLE users ADD COLUMN reset_code TEXT')
    except sqlite3.OperationalError:
        pass
        
    # Πίνακας ιστορικού scraping ανά χρήστη
    c.execute('''
        CREATE TABLE IF NOT EXISTS scrape_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT,
            url TEXT,
            title TEXT,
            h1_count INTEGER,
            h2_count INTEGER,
            links_count INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
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

def save_scrape_history(email, url, title, h1_c, h2_c, links_c):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute('INSERT INTO scrape_history (email, url, title, h1_count, h2_count, links_count) VALUES (?, ?, ?, ?, ?, ?)',
              (email, url, title, h1_c, h2_c, links_c))
    conn.commit()
    conn.close()

def get_user_history(email):
    conn = sqlite3.connect("users.db")
    df = pd.read_sql_query('SELECT url, title, h1_count, h2_count, links_count, timestamp FROM scrape_history WHERE email = ? ORDER BY timestamp DESC', conn, params=(email,))
    conn.close()
    return df

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
    st.title("SwiftScrape - Authentication Portal")
    st.markdown("Please log in with your email, create a new account, or request a password reset.")
    
    tab_login, tab_signup, tab_reset = st.tabs(["Login", "Sign Up", "Password Reset"])
    
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
            new_pass = st.text_input("Password (min. 6 chars, letters & numbers)", type="password")
            submit_signup = st.form_submit_button("Sign Up")
            
            if submit_signup:
                if new_email and new_user and new_pass:
                    if len(new_pass) < 6:
                        st.error("Password must be at least 6 characters long.")
                    elif not any(char.isalpha() for char in new_pass) or not any(char.isdigit() for char in new_pass):
                        st.error("Password must contain both letters and numbers.")
                    else:
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
            st.markdown(f"Verification code sent to **{st.session_state['reset_email_target']}**. Enter the code and choose your new password (min. 6 chars, letters & numbers).")
            with st.form("reset_confirm_form"):
                code_input = st.text_input("6-Digit Verification Code")
                new_custom_pass = st.text_input("New Custom Password", type="password")
                confirm_custom_pass = st.text_input("Confirm New Password", type="password")
                submit_update = st.form_submit_button("Update Password")
                
                if submit_update:
                    if code_input and new_custom_pass and confirm_custom_pass:
                        if len(new_custom_pass) < 6:
                            st.error("Password must be at least 6 characters long.")
                        elif not any(char.isalpha() for char in new_custom_pass) or not any(char.isdigit() for char in new_custom_pass):
                            st.error("Password must contain both letters and numbers.")
                        elif new_custom_pass != confirm_custom_pass:
                            st.error("New passwords do not match.")
                        else:
                            target_email = st.session_state["reset_email_target"]
                            if verify_and_update_password(target_email, code_input, new_custom_pass):
                                st.success("Password successfully updated! You can now log in.")
                                st.session_state["reset_stage"] = 1
                                st.session_state["reset_email_target"] = ""
                                time.sleep(1.5)
                                st.rerun()
                            else:
                                st.error("Invalid verification code. Please try again.")
                    else:
                        st.warning("Please fill in all fields.")
            
            col_resend, col_cancel = st.columns(2)
            with col_resend:
                if st.button("Resend Code"):
                    target_email = st.session_state["reset_email_target"]
                    otp = ''.join(random.choices(string.digits, k=6))
                    set_reset_code(target_email, otp)
                    success, message = send_email_via_smtp(target_email, otp)
                    if success:
                        st.success("A new verification code has been resent to your email!")
                    else:
                        st.error(message)
            with col_cancel:
                if st.button("Cancel / Restart Reset"):
                    st.session_state["reset_stage"] = 1
                    st.session_state["reset_email_target"] = ""
                    st.rerun()
                    
    st.stop()

# --- SIDEBAR: USER INFO & BOT/SCRAPING ADVANCED CONTROLS ---
st.sidebar.title("SwiftScrape Pro")
username_val = st.session_state.get('username', 'Guest')
email_val = st.session_state.get('email', '')
st.sidebar.success(f"User: {username_val}\n({email_val})")
if st.sidebar.button("Log Out"):
    st.session_state["logged_in"] = False
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader("Bot & Scraping Controls")
request_delay = st.sidebar.slider("Request Delay (sec)", 0.0, 5.0, 1.0, help="Delay between requests to avoid getting banned.")
max_links_limit = st.sidebar.slider("Max Links to Parse", 10, 200, 50, help="Limit for extracted links.")
custom_user_agent = st.sidebar.selectbox("User-Agent Mode", [
    "Standard Desktop (Chrome)", 
    "Mobile Bot (iPhone Safari)", 
    "Googlebot Crawler"
])

st.sidebar.markdown("---")
st.sidebar.markdown("### Pro Plan - €10/month")
st.sidebar.markdown("Unlimited Scrapes\nPriority Proxy Routing\nFull CSV/TXT Exports")
stripe_payment_link = "https://buy.stripe.com/00w6oH1x2ckx24t3Jk2go04"
st.sidebar.markdown("---")
st.sidebar.link_button("Pay €10 / Month Now", stripe_payment_link, use_container_width=True)

# --- MAIN APP INTERFACE ---
st.title("SwiftScrape Enterprise Intelligence")
st.markdown("Extract titles, headings, links, emails, and media assets instantly with advanced bot controls.")

# Tabs για Scraping και Ιστορικό Χρήστη
main_app_tab, history_tab = st.tabs(["🚀 Scrape Engine", "📊 My Scrape History"])

with main_app_tab:
    col_input1, col_input2 = st.columns([4, 1])
    with col_input1:
        url = st.text_input("Target URL:", "https://news.ycombinator.com", label_visibility="collapsed", placeholder="Enter website URL")
    with col_input2:
        scrape_btn = st.button("Start Scrape", use_container_width=True)

    if scrape_btn:
        if not url.startswith("http"):
            st.error("Please enter a valid URL starting with 'http://' or 'https://'.")
        else:
            with st.spinner("Executing deep web extraction with bot configurations..."):
                try:
                    ua_dict = {
                        "Standard Desktop (Chrome)": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                        "Mobile Bot (iPhone Safari)": 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)',
                        "Googlebot Crawler": 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'
                    }
                    headers = {'User-Agent': ua_dict.get(custom_user_agent, ua_dict["Standard Desktop (Chrome)"])}
                    
                    if request_delay > 0:
                        time.sleep(request_delay)
                    
                    response = requests.get(url, headers=headers, timeout=10)
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.text, 'html.parser')
                        
                        page_title = soup.title.string if soup.title else "No Title Found"
                        h1_tags = [h1.get_text().strip() for h1 in soup.find_all('h1')]
                        h2_tags = [h2.get_text().strip() for h2 in soup.find_all('h2')]
                        links = [a['href'] for a in soup.find_all('a', href=True)]
                        images = [img.get('src') for img in soup.find_all('img', src=True)]
                        emails = set(re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", response.text))
                        
                        # Αποθήκευση στη βάση δεδομένων για τον τρέχοντα χρήστη
                        save_scrape_history(email_val, url, page_title, len(h1_tags), len(h2_tags), len(links))
                        
                        st.success("Extraction completed successfully and saved to your history!")
                        
                        m1, m2, m3, m4 = st.columns(4)
                        m1.metric("H1 Headings", len(h1_tags))
                        m2.metric("H2 Headings", len(h2_tags))
                        m3.metric("Total Links", len(links))
                        m4.metric("Media Assets", len(images))
                        
                        st.markdown("---")
                        
                        tab1, tab2, tab3, tab4 = st.tabs(["Overview", "Emails", "Media", "Links"])
                        
                        with tab1:
                            st.subheader("Page Title")
                            st.info(page_title)
                            st.subheader("Export Report")
                            
                            report_text = f"URL: {url}\nTitle: {page_title}\nEmails: {list(emails)}\nTotal Links: {len(links)}\nTotal Images: {len(images)}"
                            st.download_button(
                                label="Download Full Report (TXT)",
                                data=report_text,
                                file_name="swiftscrape_report.txt",
                                mime="text/plain"
                            )
                            
                            # Δημιουργία CSV για εξαγωγή σε Excel
                            df_export = pd.DataFrame([{
                                "URL": url,
                                "Title": page_title,
                                "H1_Count": len(h1_tags),
                                "H2_Count": len(h2_tags),
                                "Links_Count": len(links),
                                "Images_Count": len(images)
                            }])
                            csv_data = df_export.to_csv(index=False).encode('utf-8')
                            st.download_button(
                                label="Download Report (CSV / Excel)",
                                data=csv_data,
                                file_name="swiftscrape_report.csv",
                                mime="text/csv"
                            )
                        with tab2:
                            st.subheader("Discovered Emails")
                            if emails:
                                st.write(list(emails))
                            else:
                                st.write("No emails detected on this page.")
                        with tab3:
                            st.subheader("Visual Media Assets")
                            st.write(f"Total images found: {len(images)}")
                            if images:
                                img_cols = st.columns(min(len(images), 3) if len(images) > 0 else 1)
                                for idx, img_src in enumerate(images[:6]):
                                    try:
                                        full_img_url = urljoin(url, img_src)
                                        with img_cols[idx % len(img_cols)]:
                                            st.image(full_img_url, width=120, caption=f"Asset {idx+1}")
                                    except:
                                        pass
                        with tab4:
                            st.subheader("Extracted Hyperlinks")
                            for link in links[:max_links_limit]:
                                full_link = urljoin(url, link)
                                st.markdown(f"- [{full_link}]({full_link})")
                    else:
                        st.error(f"Failed to fetch URL. Status code: {response.status_code}")
                except Exception as e:
                    st.error(f"An error occurred: {e}")

with history_tab:
    st.subheader("Your Past Scrapes")
    st.markdown("Here is the history of all the URLs you have scraped with your account.")
    user_hist_df = get_user_history(email_val)
    if not user_hist_df.empty:
        st.dataframe(user_hist_df, use_container_width=True)
        
        # Επιλογή λήψης όλου του ιστορικού σε CSV
        csv_history = user_hist_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download Full History (CSV)",
            data=csv_history,
            file_name="my_scrape_history.csv",
            mime="text/csv"
        )
    else:
        st.info("No scraping history found yet. Run your first scrape from the 'Scrape Engine' tab!")
