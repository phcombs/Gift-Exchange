"""Send page. M3: the draw button and the masked draw table. Sending arrives in M5."""

import random
from datetime import datetime, timezone

import streamlit as st

from giftx.draw import DrawImpossible, make_draw
from giftx.people import check_group
from giftx.storage import StorageError
from giftx.ui import common

HIDDEN = "match hidden"


def do_draw(store, gid, people):
    partner_of = {p.id: p.partner_id for p in people if p.partner_id is not None}
    try:
        assignment = make_draw([p.id for p in people], partner_of, random.SystemRandom())
        store.save_draw(gid, assignment, datetime.now(timezone.utc))
    except DrawImpossible as err:
        st.error(err.message)
        return
    except StorageError as err:
        st.error(str(err))
        return
    common.flash("Draw done. Everyone has a match; the matches stay hidden.")
    st.rerun()


def page():
    common.banner()
    common.show_flash()
    store = common.store()
    gid = common.group_id()
    if gid is None:
        st.write("Create a group on the People page first.")
        return

    people = store.list_people(gid)
    problems = check_group(people)
    draw_id, locked_at, givers = store.draw_status(gid)
    locked = locked_at is not None

    st.subheader("Draw")
    if problems:
        st.write("Fix these on the People page before drawing:")
        for problem in problems:
            st.error(problem.message)
    if locked:
        st.info("The draw is locked because emails have started going out.")
    label = "Draw again" if draw_id is not None else "Draw"
    if st.button(label, key="draw", type="primary", disabled=bool(problems) or locked):
        do_draw(store, gid, people)

    if givers:
        # recipients are never read here: the table shows givers only
        st.dataframe(
            [{"Giver": name, "Buys for": HIDDEN} for _, name in givers],
            hide_index=True,
            width="stretch",
        )
    else:
        st.write("No draw yet.")
