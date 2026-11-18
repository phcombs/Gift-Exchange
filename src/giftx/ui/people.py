"""People page: groups, people, couples, paste box, checks and the shared-address notice."""

import streamlit as st

from giftx.people import (
    check_group,
    clean_email,
    clean_name,
    email_problem,
    name_problem,
    parse_pasted,
    shared_addresses,
    shared_notice,
)
from giftx import pipeline
from giftx.storage import Locked, StorageError
from giftx.ui import common


def apply(store, gid, action, success):
    """Run a storage change; on success flash the message (plus the draw-cleared notice) and rerun."""
    before = store.draw_status(gid)[0] if gid is not None else None
    try:
        action()
    except StorageError as err:
        st.error(str(err))
        return
    if before is not None and store.draw_status(gid)[0] is None:
        common.flash(common.DRAW_CLEARED, "warning")
    if success:
        common.flash(success)
    st.rerun()


def new_group_form(store, expanded):
    with st.expander("New group", expanded=expanded):
        with st.form("new_group_form", clear_on_submit=True):
            name = st.text_input("Group name", key="new_group_name", placeholder="e.g. Smith family")
            if st.form_submit_button("Create group"):
                try:
                    gid = store.create_group(name)
                except StorageError as err:
                    st.error(str(err))
                else:
                    common.select_group_next_run(gid)
                    common.flash(f"Group {clean_name(name)} created. Add people below.")
                    st.rerun()


def people_table(people):
    if not people:
        st.write("No people in this group yet.")
        return
    names = {p.id: p.name for p in people}
    st.dataframe(
        [
            {"Name": p.name, "Email": p.email, "Partner": names.get(p.partner_id, "")}
            for p in people
        ],
        hide_index=True,
        width="stretch",
    )


def checks(people):
    for problem in check_group(people):
        st.error(problem.message)
    for names, address in shared_addresses(people):
        st.info(shared_notice(names, address))


def add_forms(store, gid, people):
    existing = [p.name for p in people]
    with st.form("add_person_form", clear_on_submit=True):
        st.markdown("**Add a person**")
        left, right = st.columns(2)
        name = left.text_input("Name", key="add_name")
        email = right.text_input("Email", key="add_email")
        if st.form_submit_button("Add person"):
            reason = name_problem(name, existing) or email_problem(email)
            if reason:
                st.error(reason)
            else:
                apply(
                    store, gid, lambda: store.add_person(gid, name, email),
                    f"Added {clean_name(name)}.",
                )

    with st.form("paste_form", clear_on_submit=True):
        st.markdown("**Paste several people**, one `name, email` per line")
        text = st.text_area(
            "People", key="paste_text", label_visibility="collapsed",
            placeholder="Ann Lee, ann@example.com\nBob Lee, bob@example.com",
        )
        if st.form_submit_button("Add these people"):
            good, bad = parse_pasted(text, existing)
            for line_no, line, reason in bad:
                common.flash(f"Line {line_no} not added ({line}): {reason}", "error")
            if good:
                apply(store, gid, lambda: store.add_people(gid, good), f"Added {len(good)} people.")
            else:
                st.rerun()


def edit_person(store, gid, people, locked):
    st.markdown("**Change or remove a person**")
    by_id = {p.id: p for p in people}
    pid = st.selectbox(
        "Person", options=list(by_id), format_func=lambda i: by_id[i].name, key="edit_pid"
    )
    if pid is None:
        return
    person = by_id[pid]
    others = [p.name for p in people if p.id != pid]
    left, right = st.columns(2)
    name = left.text_input(
        "Name", value=person.name, key=f"edit_name_{pid}", disabled=locked,
        help="Locked: only email addresses can change." if locked else None,
    )
    email = right.text_input("Email", value=person.email, key=f"edit_email_{pid}")

    save, remove, uncouple = st.columns(3)
    if save.button("Save changes", key="edit_save"):
        new_name, new_email = clean_name(name), clean_email(email)
        reason = None
        if new_name != person.name:
            reason = name_problem(new_name, others)
        if not reason and new_email != person.email:
            reason = email_problem(new_email)
        if reason:
            st.error(reason)
        else:
            def change():
                if new_email != person.email:
                    store.update_email(pid, new_email)
                if new_name != person.name:
                    store.rename_person(pid, new_name)

            apply(store, gid, change, f"Saved {new_name}.")
    if remove.button("Remove person", key="edit_delete", disabled=locked):
        apply(store, gid, lambda: store.delete_person(pid), f"Removed {person.name}.")
    if person.partner_id is not None and uncouple.button(
        "Remove partner link", key="edit_uncouple", disabled=locked
    ):
        apply(store, gid, lambda: store.clear_couple(pid), f"{person.name} no longer has a partner.")


def couples(store, gid, people, locked):
    st.markdown("**Couples** never draw each other. Each person has at most one partner.")
    by_id = {p.id: p for p in people}
    left, right = st.columns(2)
    a = left.selectbox("Person", options=list(by_id), format_func=lambda i: by_id[i].name,
                       key="couple_a", index=None, placeholder="Choose")
    b = right.selectbox("Partner", options=list(by_id), format_func=lambda i: by_id[i].name,
                        key="couple_b", index=None, placeholder="Choose")
    if st.button("Mark as couple", key="couple_set", disabled=locked or a is None or b is None):
        if a == b:
            st.error("Choose two different people.")
        else:
            apply(store, gid, lambda: store.set_couple(a, b),
                  f"{by_id[a].name} and {by_id[b].name} are a couple.")


def delete_group(store, gid, name, locked):
    with st.expander("Delete this group"):
        st.write(f"Deletes {name}, its people and its draw. This can't be undone.")
        sure = st.checkbox(f"Yes, delete {name}", key="delete_group_sure", disabled=locked)
        if st.button("Delete group", key="delete_group", disabled=locked or not sure):
            def delete():
                store.delete_group(gid)
                pipeline.clear_practice_files(gid)

            apply(store, None, delete, f"Deleted {name}.")


def page():
    common.banner()
    common.show_flash()
    store = common.store()
    groups = dict(store.list_groups())
    new_group_form(store, expanded=not groups)

    gid = common.group_id()
    if gid is None:
        st.write("Create a group to start, then add the people in it.")
        return

    name = groups[gid]
    people = store.list_people(gid)
    locked = store.draw_status(gid)[1] is not None
    st.subheader(f"{name}: {len(people)} {'person' if len(people) == 1 else 'people'}")
    if locked:
        st.warning(str(Locked()))
    people_table(people)
    checks(people)
    if not locked:
        add_forms(store, gid, people)
    if people:
        edit_person(store, gid, people, locked)
        if len(people) >= 2:
            couples(store, gid, people, locked)
    delete_group(store, gid, name, locked)
