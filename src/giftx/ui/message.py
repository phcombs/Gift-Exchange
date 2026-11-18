"""Message page: subject, body, preview with made-up names, and a test send."""

from datetime import datetime, timezone

import streamlit as st

import random

from giftx import compose, images, paths, pipeline
from giftx.model import Sent, Unknown
from giftx.people import clean_email, email_problem
from giftx.ui import common

HELP = (
    "Use **{giver}** for the person receiving the email and **{recipient}** for the person they buy for. "
    "{giver} is required, {recipient} can't be in the subject. Keep {recipient} well down the body so "
    "it stays out of Gmail's inbox preview. If you've added pictures, each email shows one inside the "
    "message: at the end, or wherever you put **{picture}**."
)


def now_utc():
    return datetime.now(timezone.utc)


def editor(store, gid):
    saved_subject, saved_body = store.get_message(gid)
    st.markdown(HELP)
    subject_key, body_key = f"msg_subject_{gid}", f"msg_body_{gid}"
    if st.session_state.pop("_msg_reset", None) == gid:
        # set before the widgets exist; Streamlit refuses changes after that
        st.session_state[subject_key] = compose.DEFAULT_SUBJECT
        st.session_state[body_key] = compose.DEFAULT_BODY
    st.session_state.setdefault(subject_key, saved_subject)
    st.session_state.setdefault(body_key, saved_body)
    subject = st.text_input("Subject", key=subject_key)
    body = st.text_area("Message", height=300, key=body_key)

    problems = compose.check_template(subject, body)
    refused = compose.refusals(problems)
    changed = (subject, body) != (saved_subject, saved_body)

    save, reset = st.columns(2)
    if save.button("Save message", key="msg_save", type="primary", disabled=not changed):
        if refused:
            for p in refused:
                st.error(p.message)
        else:
            store.set_message(gid, subject, body)
            for p in problems:  # only warnings remain
                common.flash(p.message, "warning")
            common.flash("Message saved.")
            st.rerun()
    if reset.button("Back to the default message", key="msg_default"):
        st.session_state["_msg_reset"] = gid
        st.rerun()
    if changed:
        st.caption("Unsaved changes.")
    return subject, body, refused


def show_preview(subject, body):
    st.subheader("Preview")
    st.caption(f"Filled in with made-up names: {compose.PREVIEW_GIVER} buys for {compose.PREVIEW_RECIPIENT}.")
    p_subject, p_body = compose.preview(subject, body)
    pictures = images.list_images()
    with st.container(border=True):
        st.text(f"Subject: {p_subject}")
        st.text(compose.preview_text(p_body))
        if pictures and compose.PICTURE not in body:
            st.text("[picture]")
    if pictures:
        st.caption(
            ("[picture] marks where your picture appears." if len(pictures) == 1 else
             f"[picture] marks where one of your {len(pictures)} pictures appears.")
            + " Send a test email to see it."
        )


def test_send(subject, body, refused):
    st.subheader("Test send")
    st.caption(
        f"Sends the preview (with {compose.PREVIEW_GIVER} and {compose.PREVIEW_RECIPIENT}) to one "
        "address you type. It never uses the draw."
    )
    to = st.text_input("Send test to", key="test_to", placeholder="you@example.com")
    mode = common.mode()
    sender = common.sender_for(mode)
    if sender is None:
        st.caption(common.NOT_READY)
    if st.button("Send test email", key="test_send", disabled=sender is None):
        reason = email_problem(to)
        if reason:
            st.error(reason)
            return
        if refused:
            st.error("Fix the message first: " + " ".join(p.message for p in refused))
            return
        with st.spinner("Sending…" if mode == "real" else "Writing…"):
            picture = images.pick(random.SystemRandom())  # one random picture, like a real email
            result = pipeline.test_send(sender, clean_email(to), subject, body, picture, now_utc)
        if isinstance(result, Sent):
            if mode == "real":
                st.success(f"Test email sent to {clean_email(to)}.")
            else:
                st.success(
                    "Practice email written (nothing was sent). It's in "
                    f"{paths.practice_test_dir()}"
                )
        elif isinstance(result, Unknown):
            st.warning(f"The test email may or may not have gone: {result.reason}. Check your Sent folder.")
        else:
            st.error(f"The test email failed: {result.reason}")

def page():
    common.banner()
    common.show_flash()
    store = common.store()
    gid = common.group_id()
    if gid is None:
        st.write("Create a group on the People page first. Each group has its own message.")
        return
    subject, body, refused = editor(store, gid)
    show_preview(subject, body)
    test_send(subject, body, refused)
