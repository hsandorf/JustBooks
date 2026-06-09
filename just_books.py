import pandas as pd
import streamlit as st
import datetime
import os
from PIL import Image
import gspread
from google.oauth2.service_account import Credentials

# ── Page styling ───────────────────────────────────────────────────────────────

st.markdown("""
   <style>
 [data-testid="stImage"] img {
    width: 150px;
    height: 220px;
    object-fit: contain;
    background-color: white;
    </style>
""", unsafe_allow_html=True)


st.title("First 100 Never Judge Reads")
st.write("**THIS APP WORKS BEST IN LANDSCAPE MODE ** Click on the book you enjoyed more, or indicate if you haven't read one or either. "
        "Books you've marked as unread will be removed from your future matchups. "
         f"Your choices will help us create a ranked list of our first 100 reads!")

# ── Google Sheets connection ──────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

import json
creds_dict = json.loads(st.secrets["gcp_service_account"])
creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)

@st.cache_resource
def get_worksheet():
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)

    gc = gspread.authorize(creds)
    return gc.open('100 Books').sheet1

@st.cache_data
def load_data():
    rows = get_worksheet().get_all_records()
    df = pd.DataFrame(rows)
    return df

@st.cache_data
def load_image(path):
    import os
    full_path = os.path.join(os.path.dirname(__file__), path)
    return Image.open(full_path)


df = load_data()

df["date_read"] = pd.to_datetime(df["date_read"], errors='coerce').dt.strftime("%b %Y")

# ── Constants ─────────────────────────────────────────────────────────────────
MAX_MATCHES = 100

# ── Name gate — don't show matchups until name is entered ─────────────────────
if "user_name" not in st.session_state:
    st.session_state.user_name = ""

if not st.session_state.user_name:
    name = st.text_input("Please enter your name. Doesn't have to be your actual name (if you'd rather be anonymous), just something to identify your votes in the results.")
    if st.button("Start"):
        if name.strip():
            st.session_state.user_name = name.strip()
            st.rerun()
        else:
            st.warning("Please enter your name first.")
    st.stop()

# ── Session state initialisation ──────────────────────────────────────────────
if "unread_books" not in st.session_state:
    st.session_state.unread_books = set()

if "seen_books" not in st.session_state:
    st.session_state.seen_books = set()

if "queue" not in st.session_state:
    st.session_state.queue = df.sample(frac=1).reset_index(drop=True)

if "match_count" not in st.session_state:
    st.session_state.match_count = 0

if "results" not in st.session_state:
    st.session_state.results = []

if "last_winner" not in st.session_state:
    st.session_state.last_winner = None

# ── Queue helper ──────────────────────────────────────────────────────────────
def get_next_pair():
    # Strip any unread books from the queue
    st.session_state.queue = st.session_state.queue[
        ~st.session_state.queue["title"].isin(st.session_state.unread_books)
    ].reset_index(drop=True)

    # Refill from read books only if queue is running low
    while len(st.session_state.queue) < 2:
        read_books = df[~df["title"].isin(st.session_state.unread_books)]
        new_batch = read_books.sample(frac=1).reset_index(drop=True)
        st.session_state.queue = pd.concat(
            [st.session_state.queue, new_batch]
        ).reset_index(drop=True)

    book1 = st.session_state.queue.iloc[0]
    book2 = st.session_state.queue.iloc[1]
    st.session_state.queue = st.session_state.queue.iloc[2:].reset_index(drop=True)

    st.session_state.seen_books.add(book1["title"])
    st.session_state.seen_books.add(book2["title"])

    return book1, book2

# ── Result recorder ───────────────────────────────────────────────────────────
def record_result(book1, book2, winner, book1_unread=False, book2_unread=False):
    st.session_state.results.append({
        "user_name":     st.session_state.user_name,
        "book_a":        book1["title"],
        "book_b":        book2["title"],
        "winner":        winner,
        "book_a_unread": book1_unread,
        "book_b_unread": book2_unread,
        "timestamp":     datetime.datetime.now()
    })
    st.session_state.match_count += 1

# ── Save results to CSV ───────────────────────────────────────────────────────
def save_results():
    results_df = pd.DataFrame(st.session_state.results)
    
    gc = gspread.authorize(creds)
    workbook = gc.open('100 Books')
    
    try:
        winners_sheet = workbook.worksheet('Winners')
    except gspread.exceptions.WorksheetNotFound:
        winners_sheet = workbook.add_worksheet(title='Winners', rows=5000, cols=10)
        winners_sheet.append_row(list(results_df.columns))
    
    # One API call for all rows instead of one per row
    all_rows = [[str(v) for v in row.values] for _, row in results_df.iterrows()]
    winners_sheet.append_rows(all_rows)

# ── Check if session is complete ──────────────────────────────────────────────
if st.session_state.match_count >= MAX_MATCHES:
    save_results()
    st.success(f"You've completed {MAX_MATCHES} matchups, {st.session_state.user_name}! Thanks for voting.")
    st.stop()

# ── Get current pair ──────────────────────────────────────────────────────────
if "current_pair" not in st.session_state:
    st.session_state.current_pair = get_next_pair()

book1, book2 = st.session_state.current_pair

# ── Progress + last result feedback ──────────────────────────────────────────
st.caption(f"Match {st.session_state.match_count + 1} of {MAX_MATCHES}")

if st.session_state.last_winner and st.session_state.last_winner != "Neither":
    st.success(f"You chose **{st.session_state.last_winner}**!")
elif st.session_state.last_winner == "Neither":
    st.info("Skipped — one or both book unread.")

# ── Matchup display ───────────────────────────────────────────────────────────
col1, col2, col3 = st.columns([1,1,2], gap="small")

with col1:

    st.image(load_image(book1["image_path"]), width=150)
    st.caption(book1["title"])
    st.caption(f'Read: {book1["date_read"]}')
    st.caption(book1["author"])
    
with col2:

    st.image(load_image(book2["image_path"]), width=150)
    st.caption(book2["title"])
    st.caption(f'Read: {book2["date_read"]}')
    st.caption(book2["author"])
   

st.write("") # vertical spacing
#st.write("")


with col3:

   st.subheader("Which Book Do You Rank Higher?")
    # --- MAIN VOTE BUTTONS (big decision) ---
   if st.button(f"{book1['title']}", use_container_width=True):
      record_result(book1, book2, winner=book1["title"])
      st.session_state.last_winner = book1["title"]
      st.session_state.current_pair = get_next_pair()
      st.rerun()
   
   if st.button(f"{book2['title']}", use_container_width=True):
      record_result(book1, book2, winner=book2["title"])
      st.session_state.last_winner = book2["title"]
      st.session_state.current_pair = get_next_pair()
      st.rerun()
   
   st.divider()
   
   # --- SECONDARY OPTIONS (unread handling) ---
   st.subheader("Haven't read either? No worries! Select Below")
   # --- BOTH UNREAD ---
   if st.button("Haven’t read either", use_container_width=True):
      st.session_state.unread_books.update([
      book1["title"],
      book2["title"]
      ])
      record_result(
      book1,
      book2,
      winner=None,
      book1_unread=True,
      book2_unread=True
      )
      st.session_state.last_winner = "Neither"
      st.session_state.current_pair = get_next_pair()
      st.rerun()
   
   col_a, col_b = st.columns(2)
   
   with col_a:
      if st.button(f"Haven’t read {book1['title']}", use_container_width=True):
      st.session_state.unread_books.add(book1["title"])
      record_result(
      book1,
      book2,
      winner=None,
      book1_unread=True
      )
      st.session_state.last_winner = "Neither"
      st.session_state.current_pair = get_next_pair()
      st.rerun()
      
   with col_b:
      if st.button(f"Haven’t read {book2['title']}", use_container_width=True):
      st.session_state.unread_books.add(book2["title"])
      record_result(
      book1,
      book2,
      winner=None,
      book2_unread=True
      )
      st.session_state.last_winner = "Neither"
      st.session_state.current_pair = get_next_pair()
      st.rerun()





##not running? python -m streamlit run just_books.py
