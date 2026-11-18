"""Send page: the draw, the masked draw table, and sending (confirm, progress, status, actions)."""

import random
from datetime import datetime, timezone

import streamlit as st

from giftx import paths, pipeline
from giftx.draw import DrawImpossible, make_draw
from giftx.people import check_group
from giftx.storage import StorageError
from giftx.ui import common

HIDDEN = "match hidden"


def now_utc():
    return datetime.now(timezone.utc)


def local_time(stamp):
    if not stamp:
        return ""
    return datetime.fromisoformat(stamp).astimezone().strftime("%b %d, %I:%M %p")


def status_text(record):
    status = record.status
    if status == "pending":
        return "waiting"
    if status == "sending":
        return "sending now"
    if status == "sent":
        if record.mode == "practice":
            return "written to a practice file"
        return f"sent {local_time(record.finished_at)} to {record.to_address}"
    if status == "failed":
        return f"failed: {record.error}"
    return (
        f"This may or may not have gone to {record.to_address}. Check your Sent folder."
        if record.mode == "real"
        else f"unknown: {record.error}"
    )


# ------------------------------------------------------------------ draw

def do_draw(store, gid, people):
    partner_of = {p.id: p.partner_id for p in people if p.partner_id is not None}
    try:
        assignment = make_draw([p.id for p in people], partner_of, random.SystemRandom())
        store.save_draw(gid, assignment, now_utc())
    except DrawImpossible as err:
        st.error(err.message)
        return
    except StorageError as err:
        st.error(str(err))
        return
    common.flash("Draw done. Everyone has a match; the matches stay hidden.")
    st.rerun()


def draw_section(store, gid, people, draw_id, locked, givers):
    st.subheader("Draw")
    problems = check_group(people)
    if problems:
        st.write("Fix these on the People page before drawing:")
        for problem in problems:
            st.error(problem.message)
    if locked:
        st.info("The draw is locked because emails have started going out.")
    label = "Draw again" if draw_id is not None else "Draw"
    if st.button(label, key="draw", type="primary", disabled=bool(problems) or locked):
        do_draw(store, gid, people)
    if not givers:
        st.write("No draw yet.")
        return
    # off in every new tab; recipients are read from the database only while it is on
    reveal = st.toggle("Reveal the matches", key=f"reveal_{gid}",
                       help="Shows who buys for whom on this screen. Off again in every new tab.")
    if reveal:
        names = {p.id: p.name for p in people}
        matches = store.get_assignments(draw_id)
        rows = [{"Giver": name, "Buys for": names[matches[pid]]} for pid, name in givers]
    else:
        rows = [{"Giver": name, "Buys for": HIDDEN} for _, name in givers]
    st.dataframe(rows, hide_index=True, width="stretch")


# ------------------------------------------------------------------ sending

def to_send(store, gid, draw_id, mode, locked, people):
    """[(giver name, current address)] that "Send all unsent" would email."""
    if mode == "real" and locked:
        emails = {p.id: p.email for p in people}
        return [(r.giver_name, emails[r.giver_id]) for r in store.sendable(draw_id, "real")]
    _, _, givers = store.draw_status(gid)
    emails = {p.id: p.email for p in people}
    return [(name, emails[pid]) for pid, name in givers]


def summary_message(summary, mode):
    if summary.stopped_at:
        status = "may or may not have gone" if summary.unknown else "failed"
        return "warning", (
            f"Stopped at {summary.stopped_at}: {status}. Press Send all unsent to continue."
        )
    if mode == "practice":
        return "success", (
            f"Wrote {summary.sent} practice emails (nothing was sent). They're in {paths.practice_root()}."
        )
    return "success", f"Sent {summary.sent} emails."


def run(store, gid, draw_id, mode, sender, only=None):
    """Prepare records if needed and run the pipeline; flash the result and rerun."""
    rng = random.SystemRandom()
    try:
        if only is None:
            if mode == "practice":
                pipeline.prepare_practice(store, gid, rng)
            else:
                pipeline.prepare_real(store, gid, rng)
        bar = st.progress(0.0, text="Sending…")

        def progress(done, total):
            bar.progress(done / total if total else 1.0, text=f"{done} of {total}")

        summary = pipeline.run_sends(store, draw_id, mode, sender, now_utc, progress, only)
    except pipeline.MissingImage as err:
        st.error(f"The picture for {err.giver_name} is missing.")
        return
    except StorageError as err:
        st.error(str(err))
        return
    kind, message = summary_message(summary, mode)
    common.flash(message, kind)
    st.rerun()


def confirm_panel(store, gid, group_name, draw_id, mode, sender, rows):
    with st.container(border=True):
        st.markdown(
            f"**{mode.capitalize()} send for {group_name}: {len(rows)} "
            f"{'email' if len(rows) == 1 else 'emails'}**"
        )
        if mode == "practice":
            st.caption("Practice: each email is written to a file in your data folder. Nothing is sent.")
        else:
            ready = common.email_ready()
            if ready:
                st.caption(f"Real: these emails go out from {ready[0].address} now.")
        st.dataframe(
            [{"Giver": name, "Address": address} for name, address in rows],
            hide_index=True,
            width="stretch",
        )
        go, cancel = st.columns(2)
        if go.button("Confirm and send", key="confirm_go", type="primary"):
            st.session_state.pop("confirm_send", None)
            run(store, gid, draw_id, mode, sender)
        if cancel.button("Cancel", key="confirm_cancel"):
            st.session_state.pop("confirm_send", None)
            st.rerun()


def status_table(records):
    st.dataframe(
        [{"Giver": r.giver_name, "Status": status_text(r)} for r in records],
        hide_index=True,
        width="stretch",
    )


def person_actions(store, gid, draw_id, sender, records):
    """Real mode: "Send again" and "It went" for one person."""
    actionable = {r.id: r for r in records if r.status in ("sent", "failed", "unknown")}
    if not actionable:
        return
    st.markdown("**One person**")
    rid = st.selectbox(
        "Person", options=list(actionable), format_func=lambda i: actionable[i].giver_name,
        key="action_record",
    )
    record = actionable[rid]
    went, again = st.columns(2)
    if record.status == "unknown" and went.button("It went", key="action_went"):
        store.mark_went(rid)
        common.flash(f"Marked {record.giver_name} as sent.")
        st.rerun()
    sure = True
    if record.status == "sent":
        sure = st.checkbox(
            f"Yes, send {record.giver_name} another email", key=f"action_sure_{rid}"
        )
    if again.button("Send again", key="action_again", disabled=sender is None or not sure):
        if store.reset_to_pending(rid):
            run(store, gid, draw_id, "real", sender, only=rid)


def new_exchange(store, gid):
    with st.expander("Start a new exchange"):
        sent = sum(
            1 for r in store.status_rows(store.draw_status(gid)[0], "real") if r.status == "sent"
        )
        st.write(
            f"{sent} {'email has' if sent == 1 else 'emails have'} already gone out. This deletes the "
            "draw and every send record and practice file. People, couples and the message are kept."
        )
        sure = st.checkbox("Yes, start a new exchange", key="new_exchange_sure")
        if st.button("Start a new exchange", key="new_exchange", disabled=not sure):
            store.discard_draw(gid)
            pipeline.clear_practice_files(gid)
            common.flash("The draw was deleted. Draw again when you're ready.")
            st.rerun()


def send_section(store, gid, group_name, people, draw_id, locked):
    mode = common.mode()
    sender = common.sender_for(mode)
    st.subheader("Send")
    if sender is None:
        st.caption(common.NOT_READY)
    rows = to_send(store, gid, draw_id, mode, locked, people)
    if mode == "real" and locked and not rows:
        st.success("Everyone has been sent their email.")
    if st.button("Send all unsent", key="send_all", disabled=sender is None or not rows):
        st.session_state["confirm_send"] = (draw_id, mode)
    if st.session_state.get("confirm_send") == (draw_id, mode) and sender is not None and rows:
        confirm_panel(store, gid, group_name, draw_id, mode, sender, rows)

    records = store.status_rows(draw_id, mode)
    if records:
        status_table(records)
        if mode == "real":
            person_actions(store, gid, draw_id, sender, records)
    new_exchange(store, gid)


def page():
    common.banner()
    common.show_flash()
    store = common.store()
    gid = common.group_id()
    if gid is None:
        st.write("Create a group on the People page first.")
        return

    people = store.list_people(gid)
    draw_id, locked_at, givers = store.draw_status(gid)
    locked = locked_at is not None
    draw_section(store, gid, people, draw_id, locked, givers)
    if draw_id is not None:
        group_name = dict(store.list_groups())[gid]
        send_section(store, gid, group_name, people, draw_id, locked)
