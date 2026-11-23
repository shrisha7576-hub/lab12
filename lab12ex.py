"""
ISOM3400 Business Applications Development in Python
Wikipedia Article Extractor - Streamlit UI (search, select, extract, preview)

Wires WikipediaExtractor (from wikipedia_extractor_core.py) into the UI.
The download button is not added yet.
Run with:  streamlit run app.py
"""

import re

import streamlit as st

from wikipedia_extractor_core import (
    DisambiguationError,
    WikipediaError,
    WikipediaExtractor,
    validate_topic,
)

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
    "suggestions": [],
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

# ----------------------------------------------------------------------------
# Stage 1 - Search submit handler
# ----------------------------------------------------------------------------
input_error = None
if submitted:
    topic = topic_input.strip()

    # Every new search starts from a clean slate.
    st.session_state.article = None
    st.session_state.titles = []
    st.session_state.selected = []
    st.session_state.sections = []
    st.session_state.suggestions = []

    input_error = validate_topic(topic)
    if input_error is None:
        st.session_state.topic = topic
        article = WikipediaExtractor(topic)
        with st.spinner(f"Searching Wikipedia for '{topic}'..."):
            try:
                article.fetch_and_parse()
            except DisambiguationError as exc:
                st.session_state.suggestions = list(exc.suggestions)
            except WikipediaError:
                pass  # The message is already stored in article.error
        st.session_state.article = article
        if not article.error:
            st.session_state.titles = [sec["title"] for sec in article.sections]

# Placeholder sections
article_info_area = st.container()      # article title, URL, errors
section_select_area = st.container()    # section multiselect
extract_area = st.container()           # Extract button
preview_area = st.container()           # report preview
download_area = st.container()          # download button (next step)

article = st.session_state.article

with article_info_area:
    if input_error:
        st.error(input_error)
    elif article is not None and article.error:
        st.error(article.error)
        if st.session_state.suggestions:
            st.write("Try one of these specific topics:")
            for item in st.session_state.suggestions:
                st.markdown(f"- {item}")
    elif article is not None:
        st.success(
            f"Article found: {article.article_title} "
            f"({len(st.session_state.titles)} sections available)"
        )
        st.write(article.url)

# ----------------------------------------------------------------------------
# Stage 2 - Select
# ----------------------------------------------------------------------------
if st.session_state.titles:
    with section_select_area:
        st.session_state.selected = st.multiselect(
            "Select sections to extract",
            options=st.session_state.titles,
            default=st.session_state.selected,
        )

    # ------------------------------------------------------------------------
    # Stage 3 - Extract
    # ------------------------------------------------------------------------
    with extract_area:
        if st.button("Extract"):
            if not st.session_state.selected:
                st.warning("Please select at least one section before extracting.")
            else:
                # Section ids are 1-based positions, as used in the report.
                st.session_state.sections = [
                    article.sections[st.session_state.titles.index(title)]
                    for title in st.session_state.selected
                ]

# ----------------------------------------------------------------------------
# Stage 4 - Preview
# ----------------------------------------------------------------------------
if st.session_state.sections:
    with preview_area:
        with st.container(border=True):
            for sec in st.session_state.sections:
                st.markdown(f"### {sec['id']}. {sec['title']}")
                body = re.sub(r"\n{3,}", "\n\n", "\n".join(sec["lines"]).strip())
                if body:
                    st.text(body)
                else:
                    st.caption("(no extractable content)")

# ----------------------------------------------------------------------------
# Debug
# ----------------------------------------------------------------------------
st.write(st.session_state)
