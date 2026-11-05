import sqlite3
import hashlib
import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import time
import stripe 
from urllib.parse import urljoin

# --- 1. LOGIN / SIGN UP DATABASE & FUNCTIONS ---
def init_db():
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    # Το username είναι PRIMARY KEY, άρα δεν επιτρέπονται διπλά ονόματα χρηστών!
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT
        )
    ''')
    conn.commit()
    conn.close()

def make_hash(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_user(username, password):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute('SELECT password FROM users WHERE username = ?', (username,))
    data = c.fetchone()
    conn.close()
    if data and data[0] == make_hash(password):
        return True
    return False

def add_user(username, password):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    try:
        c.execute('INSERT INTO users(username, password) VALUES (?, ?)', (username, make_hash(password)))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        # Αν υπάρχει ήδη το username, η SQLite πετάει IntegrityError και το πιάνουμε εδώ
        conn.close()
        return False

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

# --- AUTH LOGIN / SIGN UP PORTAL ---
if not st.session_state["logged_in"]:
    st.title("🔐 SwiftScrape - Portal Syndesis & Eggrafis")
    st.markdown("Παρακαλώ συνδεθείτε ή δημιουργήστε νέο λογαριασμό για να προχωρήσετε στην εφαρμογή.")
    
    tab_login, tab_signup = st.tabs(["🔑 Σύνδεση (Login)", "📝 Εγγραφή (Sign Up)"])
    
    with tab_login:
        st.subheader("Είσοδος στην Εφαρμογή")
        with st.form("login_form"):
            ul = st.text_input("Username")
            pl = st.text_input("Password", type="password")
            submit_login = st.form_submit_button("Log In")
            
            if submit_login:
                if check_user(ul, pl):
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = ul
                    st.success(f"Καλώς ήρθες, {ul}!")
                    st.rerun()
                else:
                    st.error("Λάθος όνομα χρήστη ή κωδικός πρόσβασης.")
                    
    with tab_signup:
        st.subheader("Δημιουργία Νέου Λογαριασμού")
        with st.form("signup_form"):
            new_user = st.text_input("Επιλέξτε Username")
            new_pass = st.text_input("Επιλέξτε Password", type="password")
            submit_signup = st.form_submit_button("Sign Up")
            
            if submit_signup:
                if new_user and new_pass:
                    if add_user(new_user, new_pass):
                        st.success("Ο λογαριασμός δημιουργήθηκε επιτυχώς! Πηγαίνετε στο tab 'Σύνδεση'.")
                    else:
                        st.error("Το Username υπάρχει ήδη. Δοκιμάστε άλλο.")
                else:
                    st.warning("Παρακαλώ συμπληρώστε όλα τα πεδία.")
                    
    st.stop()

# --- SIDEBAR: USER INFO & BOT/SCRAPING ADVANCED CONTROLS ---
st.sidebar.title("SwiftScrape Pro")
username_val = st.session_state.get('username', 'Guest')
st.sidebar.success(f"Συνδεδεμένος: {username_val}")
if st.sidebar.button("Log Out"):
    st.session_state["logged_in"] = False
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader("🤖 Bot & Scraping Controls")
request_delay = st.sidebar.slider("Request Delay (sec)", 0.0, 5.0, 1.0, help="Καθυστέρηση μεταξύ αιτημάτων για αποφυγή ban.")
max_links_limit = st.sidebar.slider("Max Links to Parse", 10, 200, 50, help="Όριο εξαγωγής συνδέσμων.")
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
                    
                    st.success("Extraction completed successfully with custom bot parameters!")
                    
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
