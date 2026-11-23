"""
ISOM3400 Business Applications Development in Python
Wikipedia Article Extractor - Streamlit UI (search, select, extract, preview, download)

Wires WikipediaExtractor (from wikipedia_extractor_core.py) into the UI.
Run with:  streamlit run lab12ex.py
"""

import re

import streamlit as st

from wikipedia_extractor_core import (
    DisambiguationError,
    WikipediaError,
    WikipediaExtractor,
    format_txt,
    numbered_filename,
    safe_filename,
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
        st.session_state[key] = list(default) if isinstance(default, list) else default

# Robustness guard: reset stale state if article is missing while titles/sections exist
if st.session_state.article is None and (st.session_state.titles or st.session_state.sections):
    st.session_state.titles = []
    st.session_state.selected = []
    st.session_state.sections = []
    st.session_state.downloaded_filenames = []
    st.rerun()

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

with st.expander("How to use this app"):
    st.markdown(
        "1. Enter a topic in the search box and click **Search**.\n"
        "2. Select one or more sections from the multiselect.\n"
        "3. Click **Extract** to preview the selected content.\n"
        "4. Click **Download .txt** to save the report to your device."
    )

# Progress indicator
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.caption(f"{'✅' if st.session_state.topic else '⬜'} Search")
with col2:
    st.caption(f"{'✅' if st.session_state.titles else '⬜'} Select")
with col3:
    st.caption(f"{'✅' if st.session_state.sections else '⬜'} Extract")
with col4:
    st.caption(f"{'✅' if st.session_state.downloaded_filenames else '⬜'} Download")

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
        extractor = WikipediaExtractor(topic)
        with st.spinner(f"Searching Wikipedia for '{topic}'..."):
            try:
                extractor.fetch_and_parse()
            except DisambiguationError as exc:
                st.session_state.suggestions = list(exc.suggestions)
            except WikipediaError:
                pass  # Error message is already stored in extractor.error
        st.session_state.article = extractor
        if not extractor.error:
            st.session_state.titles = [sec["title"] for sec in extractor.sections]

# Placeholder sections
article_info_area = st.container()      # article title, URL, errors
section_select_area = st.container()    # section multiselect
extract_area = st.container()           # Extract button
preview_area = st.container()           # report preview
download_area = st.container()          # download button

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
# Stage 2 & 3 - Select and Extract
# ----------------------------------------------------------------------------
if article is not None and not article.error and st.session_state.titles:
    if len(st.session_state.titles) <= 1:
        st.warning("No usable sections found to extract for this topic.")
    else:
        with section_select_area:
            st.session_state.selected = st.multiselect(
                "Select sections to extract",
                options=st.session_state.titles,
                default=st.session_state.selected,
            )

        with extract_area:
            if st.button("Extract"):
                if not st.session_state.selected:
                    st.warning("Please select at least one section before extracting.")
                else:
                    st.session_state.sections = [
                        article.sections[st.session_state.titles.index(title)]
                        for title in st.session_state.selected
                    ]

# ----------------------------------------------------------------------------
# Stage 4 - Preview
# ----------------------------------------------------------------------------
if st.session_state.sections and article is not None and not article.error:
    with preview_area:
        with st.container(border=True):
            for sec in st.session_state.sections:
                st.markdown(f"### {sec['id']}. {sec['title']}")
                body = re.sub(r"\n{3,}", "\n\n", "\n".join(sec["lines"]).strip())
                if body:
                    st.text(body)
                else:
                    st.caption("(no extractable content)")

    # ------------------------------------------------------------------------
    # Download flow (in-memory string + session collision check)
    # ------------------------------------------------------------------------
    with download_area:
        base_name = safe_filename(article.article_title)
        has_collision = base_name in st.session_state.downloaded_filenames
        if has_collision:
            st.warning(
                "You already downloaded a file with this name in this session. "
                "Downloading again will add (2) to the name."
            )
        final_filename = numbered_filename(
            base_name, st.session_state.downloaded_filenames
        )
        report_content = format_txt(
            article.article_title,
            article.url,
            st.session_state.sections,
        )

        def _record_download(fname=final_filename):
            st.session_state.downloaded_filenames.append(fname)
            st.session_state.saved_path = fname

        st.download_button(
            label="Download .txt",
            data=report_content,
            file_name=final_filename,
            mime="text/plain",
            key="download_btn",
            on_click=_record_download,
        )

st.caption("Content from Wikipedia, CC BY-SA 4.0.")

# ----------------------------------------------------------------------------
# Debug
# ----------------------------------------------------------------------------
st.write(st.session_state)
