import streamlit as st

PRACTICE_TEXT = "Practice mode: nothing is emailed"
REAL_TEXT = "Real mode: emails are sent from your Gmail"


def mode():
    return st.session_state.get("mode", "practice")


def banner():
    if mode() == "real":
        st.warning(REAL_TEXT)
    else:
        st.info(PRACTICE_TEXT)


def setup_page():
    banner()


def people_page():
    banner()


def message_page():
    banner()


def images_page():
    banner()


def send_page():
    banner()


def pages():
    return [
        st.Page(setup_page, title="Setup", url_path="setup", default=True),
        st.Page(people_page, title="People", url_path="people"),
        st.Page(message_page, title="Message", url_path="message"),
        st.Page(images_page, title="Images", url_path="images"),
        st.Page(send_page, title="Send", url_path="send"),
    ]
