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
        pins = store.list_pins(gid)
        assignment = make_draw([p.id for p in people], partner_of, random.SystemRandom(), pins)
        store.save_draw(gid, assignment, now_utc())
    except DrawImpossible as err:
        st.error(err.message)
        return
    except StorageError as err:
        st.error(str(err))
        return
    fixed = f" {len(pins)} fixed, the rest drawn at random." if pins else ""
    common.flash(f"Draw done.{fixed} The matches stay hidden.")
    st.rerun()


def change_and_rerun(store, gid, action, message):
    """Run a pin or match change; flash the message (and the draw-cleared notice if it cleared one)."""
    had_draw = store.draw_status(gid)[0] is not None
    try:
        action()
    except StorageError as err:
        st.error(str(err))
        return
    if had_draw and store.draw_status(gid)[0] is None:
        common.flash(common.DRAW_CLEARED, "warning")
    common.flash(message)
    st.rerun()


def fixed_matches(store, gid, people, locked):
    """Pins: "A buys for B" chosen before the draw; everyone else is drawn around them."""
    pins = store.list_pins(gid)
    names = {p.id: p.name for p in people}
    partner = {p.id: p.partner_id for p in people}
    label = f"Fixed matches ({len(pins)})" if pins else "Fixed matches (optional)"
    with st.expander(label):
        st.caption(
            "Choose who buys for whom before drawing; everyone else is drawn at random around these. "
            "Changing them clears the current draw."
        )
        for giver, recipient in sorted(pins.items(), key=lambda kv: names[kv[0]].casefold()):
            left, right = st.columns([4, 1])
            note = " (their partner)" if partner.get(giver) == recipient else ""
            left.write(f"{names[giver]} buys for {names[recipient]}{note}")
            if right.button("Remove", key=f"pin_remove_{giver}", disabled=locked):
                change_and_rerun(store, gid, lambda g=giver: store.remove_pin(g),
                                 f"{names[giver]} is drawn at random again.")
        if locked or len(people) < 2:
            return
        free_givers = [p.id for p in people if p.id not in pins]
        free_recipients = [p.id for p in people if p.id not in set(pins.values())]
        left, right = st.columns(2)
        giver = left.selectbox("Giver", free_givers, format_func=names.get, index=None,
                               placeholder="Choose", key="pin_giver")
        options = [r for r in free_recipients if r != giver]
        recipient = right.selectbox("Buys for", options, format_func=names.get, index=None,
                                    placeholder="Choose", key="pin_recipient")
        if giver is not None and recipient is not None and partner.get(giver) == recipient:
            st.caption(f"{names[giver]} and {names[recipient]} are a couple; a fixed match allows it.")
        if st.button("Fix this match", key="pin_add", disabled=giver is None or recipient is None):
            change_and_rerun(store, gid, lambda: store.set_pin(giver, recipient),
                             f"Fixed: {names[giver]} buys for {names[recipient]}.")


def change_match(store, gid, people, matches):
    """After a draw (unlocked, revealed): give one giver a different recipient by swapping with the
    giver who had that recipient, so everyone still gives once and receives once."""
    names = {p.id: p.name for p in people}
    st.markdown("**Change a match**")
    st.caption("The person who had the new recipient gets this giver's old one instead.")
    left, right = st.columns(2)
    giver = left.selectbox("Giver", sorted(matches, key=lambda g: names[g].casefold()),
                           format_func=names.get, index=None, placeholder="Choose", key="swap_giver")
    options = [r for r in sorted(names, key=lambda i: names[i].casefold())
               if giver is not None and r not in (giver, matches[giver])]
    recipient = right.selectbox("Now buys for", options, format_func=names.get, index=None,
                                placeholder="Choose", key="swap_recipient")
    if st.button("Change", key="swap_go", disabled=giver is None or recipient is None):
        other = next(g for g, r in matches.items() if r == recipient)
        old = matches[giver]
        if other == old:
            st.error(f"That would leave {names[other]} buying for themselves. Pick someone else.")
            return
        updated = {**matches, giver: recipient, other: old}
        change_and_rerun(
            store, gid, lambda: store.update_assignment(gid, updated),
            f"{names[giver]} now buys for {names[recipient]}; {names[other]} now buys for {names[old]}.",
        )


def saved_draws(store, gid, draw_id, locked):
    """Save the current draw under a name; restore or delete saved ones. Never shows matches."""
    snapshots = store.list_snapshots(gid)
    label = f"Saved draws ({len(snapshots)})" if snapshots else "Saved draws"
    with st.expander(label):
        st.caption(
            "Keep a draw you like, then try other things. Restoring brings it back exactly, as long as "
            "the group has the same people. Saved draws never show who buys for whom."
        )
        if draw_id is not None:
            left, right = st.columns([3, 1])
            name = left.text_input("Name", key="snap_name", placeholder="e.g. Good one",
                                   label_visibility="collapsed")
            if right.button("Save this draw", key="snap_save"):
                try:
                    store.save_snapshot(gid, name, now_utc())
                except StorageError as err:
                    st.error(str(err))
                else:
                    common.flash(f"Saved the draw as {name.strip()}.")
                    st.rerun()
        for sid, name, created_at, usable in snapshots:
            left, mid, right = st.columns([3, 1, 1])
            note = "" if usable else " (people changed since; can't restore)"
            left.write(f"**{name}**, saved {local_time(created_at)}{note}")
            if mid.button("Restore", key=f"snap_restore_{sid}", disabled=locked or not usable):
                try:
                    store.restore_snapshot(sid, now_utc())
                except StorageError as err:
                    st.error(str(err))
                else:
                    common.flash(f"Restored the saved draw {name}. The matches stay hidden.")
                    st.rerun()
            if right.button("Delete", key=f"snap_delete_{sid}"):
                store.delete_snapshot(sid)
                common.flash(f"Deleted the saved draw {name}.")
                st.rerun()
        if not snapshots and draw_id is None:
            st.write("No saved draws yet. Draw first, then save it here.")


def draw_section(store, gid, people, draw_id, locked, givers):
    st.subheader("Draw")
    problems = check_group(people)
    if problems:
        st.write("Fix these on the People page before drawing:")
        for problem in problems:
            st.error(problem.message)
    if locked:
        st.info("The draw is locked because emails have started going out.")
    fixed_matches(store, gid, people, locked)
    label = "Draw again" if draw_id is not None else "Draw"
    if st.button(label, key="draw", type="primary", disabled=bool(problems) or locked):
        do_draw(store, gid, people)
    saved_draws(store, gid, draw_id, locked)
    if not givers:
        st.write("No draw yet.")
        return
    # off in every new tab; recipients are read from the database only while it is on
    reveal = st.toggle("Reveal the matches", key=f"reveal_{gid}",
                       help="Shows who buys for whom on this screen. Off again in every new tab.")
    if not reveal:
        st.dataframe([{"Giver": name, "Buys for": HIDDEN} for _, name in givers],
                     hide_index=True, width="stretch")
        return
    names = {p.id: p.name for p in people}
    matches = store.get_assignments(draw_id)
    st.dataframe([{"Giver": name, "Buys for": names[matches[pid]]} for pid, name in givers],
                 hide_index=True, width="stretch")
    if not locked:
        change_match(store, gid, people, matches)


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
