import streamlit as st

from giftx import APP_NAME
from giftx.storage import NewerVersion
from giftx.ui import common


def group_selector(store):
    groups = dict(store.list_groups())
    pending = st.session_state.pop("_select_group", None)
    if pending in groups:
        st.session_state["group_id"] = pending
    elif st.session_state.get("group_id") not in groups:
        st.session_state.pop("group_id", None)
    st.sidebar.selectbox(
        "Group", options=list(groups), format_func=lambda gid: groups[gid], key="group_id"
    )


def sidebar():
    """Mode switch and group selector, shared by every page in the tab."""
    st.sidebar.radio(
        "Mode", ["practice", "real"], key="mode", format_func=str.capitalize
    )
    try:
        store = common.store()
    except NewerVersion as err:
        common.banner()
        st.error(str(err))
        st.stop()
    group_selector(store)


def main():
    st.set_page_config(page_title=APP_NAME)
    sidebar()
    page = st.navigation(common.pages())
    page.run()
