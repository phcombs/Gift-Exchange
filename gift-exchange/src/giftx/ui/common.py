import streamlit as st

from giftx import paths
from giftx.storage import Storage

PRACTICE_TEXT = "Practice mode: nothing is emailed"
REAL_TEXT = "Real mode: emails are sent from your Gmail"
DRAW_CLEARED = "The draw was cleared because the group changed. Draw again."


def mode():
    return st.session_state.get("mode", "practice")


def banner():
    if mode() == "real":
        st.warning(REAL_TEXT)
    else:
        st.info(PRACTICE_TEXT)


def store():
    """Open the database in the data folder (created on first use). Raises NewerVersion."""
    paths.data_dir()
    return Storage(paths.db_path())


def group_id():
    return st.session_state.get("group_id")


def select_group_next_run(gid):
    # the selector widget already exists in this run, so its value is set before the next one
    st.session_state["_select_group"] = gid


def flash(message, kind="success"):
    """Show a message after the next rerun."""
    st.session_state.setdefault("_flash", []).append((kind, message))


def show_flash():
    for kind, message in st.session_state.pop("_flash", []):
        getattr(st, kind)(message)


def setup_page():
    banner()


def people_page():
    from giftx.ui import people

    people.page()


def message_page():
    banner()


def images_page():
    banner()


def send_page():
    from giftx.ui import send

    send.page()


def pages():
    return [
        st.Page(setup_page, title="Setup", url_path="setup", default=True),
        st.Page(people_page, title="People", url_path="people"),
        st.Page(message_page, title="Message", url_path="message"),
        st.Page(images_page, title="Images", url_path="images"),
        st.Page(send_page, title="Send", url_path="send"),
    ]
