"""Setup page: the email account real mode sends from, and where the data lives."""

from dataclasses import replace

import streamlit as st

from giftx import account, paths, senders
from giftx.account import PRESETS, SECURITY, EmailSettings
from giftx.ui import common

INTRO = (
    "Practice mode needs no setup. To send real email, the app signs in to **your own email account** "
    "with an **app password**: a separate password your provider creates for one app, which you can "
    "revoke at any time. Emails go out from your address, as if you sent them yourself."
)


def status(settings, ready):
    if ready:
        where = "remembered on this computer" if settings.password else "kept until the app stops"
        st.success(f"Real mode is ready: emails go out from {settings.address} (app password {where}).")
    elif settings:
        st.write(f"Saved for {settings.address}. Enter the app password again to use real mode.")
    else:
        st.write("Real mode isn't set up yet.")


def account_form(saved):
    provider_keys = list(PRESETS)
    current = saved.provider if saved else "gmail"
    provider = st.selectbox(
        "Email provider", provider_keys, index=provider_keys.index(current),
        format_func=lambda k: PRESETS[k].label, key="acct_provider",
    )
    preset = PRESETS[provider]
    st.caption(preset.help)

    host, port, security = preset.host, preset.port, preset.security
    if provider == "other":
        same = saved is not None and saved.provider == "other"
        left, mid, right = st.columns([3, 1, 2])
        host = left.text_input("SMTP server", value=saved.host if same else "", key="acct_host",
                               placeholder="smtp.example.com")
        port = mid.number_input("Port", 1, 65535, value=saved.port if same else 587, key="acct_port")
        security = right.selectbox(
            "Security", list(SECURITY), format_func=SECURITY.get, key="acct_security",
            index=list(SECURITY).index(saved.security if same else "starttls"),
        )

    address = st.text_input(
        "Your email address", value=saved.address if saved else "", key="acct_address",
        placeholder="you@example.com",
    )
    password = st.text_input("App password", type="password", key="acct_password")
    remember = st.checkbox(
        "Remember the app password on this computer",
        value=bool(saved and saved.password), key="acct_remember",
        help="Saved in your data folder, never in the app's folder or git. Leave unticked to type it "
             "each time you start the app.",
    )
    settings = EmailSettings(provider, host, int(port), security, address.strip(), None)
    return settings, account.clean_password(password), remember


def page():
    common.banner()
    common.show_flash()

    st.subheader("Email account (real mode)")
    st.markdown(INTRO)
    saved = account.load()
    status(saved, common.email_ready() is not None)

    settings, password, remember = account_form(saved)
    save, forget = st.columns(2)
    if save.button("Save and test the connection", key="acct_save", type="primary"):
        problem = account.settings_problem(settings)
        if not problem and not password:
            problem = "Enter the app password."
        if problem:
            st.error(problem)
        else:
            with st.spinner("Signing in to your email server…"):
                problem = senders.login_problem(
                    settings.host, settings.port, settings.security, settings.address, password
                )
            if problem:
                st.error(problem)
            else:
                account.save(replace(settings, password=password), remember)
                common.password_holder()["password"] = password
                common.flash("Signed in. Real mode is ready.")
                st.rerun()
    if saved and forget.button("Forget this account", key="acct_forget"):
        account.forget()
        common.password_holder().pop("password", None)
        common.flash("The email account and app password were removed from this computer.")
        st.rerun()

    st.subheader("Data folder")
    st.write("Names, addresses, draws and settings are stored here, outside the app's folder:")
    st.code(str(paths.data_dir()), language=None)
