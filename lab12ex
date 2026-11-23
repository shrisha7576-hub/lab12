"""
ISOM3400 Business Applications Development in Python
Wikipedia Article Extractor - Streamlit skeleton UI

Skeleton only: renders the layout with placeholders. No scraping yet.
Run with:  streamlit run app.py
"""

import streamlit as st

# Must be the first Streamlit call in the script.
st.set_page_config(page_title="Wikipedia Extractor", layout="wide")

# ----------------------------------------------------------------------------
# Session state defaults (only set if the key is not already present)
# ----------------------------------------------------------------------------
DEFAULTS = {
    "topic": None,
    "article": None,
    "titles": [],
    "selected": [],
    "sections": [],
    "saved_path": None,
    "pending_overwrite": None,
    "pending_filename": None,
    "downloaded_filenames": [],
}
for key, default in DEFAULTS.items():
    if key not in st.session_state:
        # Copy lists so each session gets its own list object.
        st.session_state[key] = list(default) if isinstance(default, list) else default

# ----------------------------------------------------------------------------
# Sidebar
# ----------------------------------------------------------------------------
with st.sidebar:
    st.header("Wikipedia Extractor")
    if st.button("Start Over"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

# ----------------------------------------------------------------------------
# Main area
# ----------------------------------------------------------------------------
st.title("Wikipedia Article Extractor")

with st.form("topic_form"):
    topic_input = st.text_input("Enter a topic")
    submitted = st.form_submit_button("Search")

# Placeholder sections (empty for now)
article_info_area = st.container()      # article title, URL, section count
section_select_area = st.container()    # section multiselect
extract_area = st.container()           # Extract button
preview_area = st.container()           # report preview
download_area = st.container()          # download button

# ----------------------------------------------------------------------------
# Debug
# ----------------------------------------------------------------------------
st.write(st.session_state)
