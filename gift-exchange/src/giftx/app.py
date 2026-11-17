import streamlit as st

from giftx import APP_NAME
from giftx.ui import common


def main():
    st.set_page_config(page_title=APP_NAME)
    st.sidebar.radio(
        "Mode", ["practice", "real"], key="mode", format_func=str.capitalize
    )
    st.sidebar.selectbox("Group", options=[], key="group_id")
    page = st.navigation(common.pages())
    page.run()
