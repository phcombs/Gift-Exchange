import streamlit as st

from giftx import account, paths
from giftx.senders import PracticeSender, SmtpSender
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


NOT_READY = "Set up your email account on the Setup page first"


@st.cache_resource
def _password_holder(settings_path):
    # one per server process and data folder: the app password typed this session (not remembered)
    return {}


def password_holder():
    return _password_holder(str(paths.email_settings_file()))


def email_ready():
    """(settings, password) when real mode can send, else None."""
    settings = account.load()
    if settings is None:
        return None
    password = settings.password or password_holder().get("password")
    return (settings, password) if password else None


def sender_for(mode):
    """The sender for this mode, or None while real mode has no email account set up."""
    if mode == "practice":
        return PracticeSender()
    ready = email_ready()
    if ready is None:
        return None
    settings, password = ready
    return SmtpSender(settings.host, settings.port, settings.security, settings.address, password)


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
    from giftx.ui import setup

    setup.page()


def people_page():
    from giftx.ui import people

    people.page()


def message_page():
    from giftx.ui import message

    message.page()


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
