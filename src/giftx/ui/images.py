"""Images page: the shared picture library. Each email gets one picture picked at random."""

import streamlit as st

from giftx import images
from giftx.model import Problem
from giftx.ui import common

COLUMNS = 4


def uploader():
    # a new key after each upload empties the uploader
    n = st.session_state.get("_uploader_n", 0)
    files = st.file_uploader(
        "Add pictures (JPEG, PNG or GIF, up to 10 MB each)",
        type=["jpg", "jpeg", "png", "gif"], accept_multiple_files=True, key=f"uploader_{n}",
    )
    if not files:
        return
    added = 0
    for f in files:
        data = f.getvalue()
        result = images.check_image(data)
        if isinstance(result, Problem):
            common.flash(f"{f.name}: {result.message}", "error")
            continue
        images.save_image(data)
        added += 1
    if added:
        common.flash(f"Added {added} {'picture' if added == 1 else 'pictures'}.")
    st.session_state["_uploader_n"] = n + 1
    st.rerun()


def gallery(store):
    names = images.list_images()
    if not names:
        st.write("No pictures yet. Emails are sent without a picture until you add some.")
        return
    st.write(f"{len(names)} {'picture' if len(names) == 1 else 'pictures'}. "
             "Each email gets one of them at random.")
    users = store.image_users()
    for start in range(0, len(names), COLUMNS):
        for col, name in zip(st.columns(COLUMNS), names[start:start + COLUMNS]):
            with col:
                data, _ = images.read_image(name)
                st.image(data, width="stretch")
                used_by = users.get(name)
                if used_by:
                    st.caption("Used by emails for " + ", ".join(used_by))
                if st.button("Delete", key=f"img_del_{name}", disabled=bool(used_by)):
                    problem = images.delete_image(name, set(users))
                    if problem:
                        st.error(problem.message)
                    else:
                        common.flash("Picture deleted.")
                        st.rerun()


def page():
    common.banner()
    common.show_flash()
    store = common.store()
    st.subheader("Pictures")
    st.caption("One shared library for all groups. Each email shows one picture inside the message (GIFs play), at the end or wherever the message has {picture}.")
    uploader()
    gallery(store)
