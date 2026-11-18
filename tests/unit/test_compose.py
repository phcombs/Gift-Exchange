from email import message_from_bytes
from email.policy import default

import pytest

from giftx import compose
from giftx.compose import (
    DEFAULT_BODY,
    DEFAULT_SUBJECT,
    build_email,
    check_template,
    fill,
    preview,
    refusals,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 32


def parse(raw):
    return message_from_bytes(raw, policy=default)


def codes(problems):
    return sorted(p.code for p in problems)


def test_defaults_pass_and_read_as_chosen():
    assert check_template(DEFAULT_SUBJECT, DEFAULT_BODY) == []
    assert DEFAULT_SUBJECT == "Christmas Gift Exchange"
    assert DEFAULT_BODY == "Hi {giver}, happy Festivus.\n\n\n\n\n\nYou are buying a gift for {recipient}."


def test_recipient_in_subject_is_refused():
    problems = check_template("For {giver}: {recipient}", DEFAULT_BODY)
    assert codes(refusals(problems)) == ["recipient_in_subject"]


def test_body_without_giver_is_refused():
    assert codes(refusals(check_template("Hi", "You buy for {recipient}"))) == ["no_giver"]


def test_body_without_recipient_only_warns():
    problems = check_template("Hi {giver}", "Hello {giver}")
    assert codes(problems) == ["no_recipient"]
    assert refusals(problems) == []


def test_blank_subject_is_refused():
    assert codes(refusals(check_template("  ", DEFAULT_BODY))) == ["blank_subject"]


def test_fill_is_literal_and_leaves_stray_braces():
    template = "{ {{name}} {} {giver}->{recipient} {GIVER} {giver"
    assert fill(template, "Ann", "Bob") == "{ {{name}} {} Ann->Bob {GIVER} {giver"


def test_fill_does_not_reinterpret_a_name_that_looks_like_a_placeholder():
    assert fill("{giver} / {recipient}", "{recipient}", "Bob") == "{recipient} / Bob"


def test_preview_uses_made_up_names():
    assert preview("Hi {giver}", "{giver} buys for {recipient}") == ("Hi Alex", "Alex buys for Sam")


@pytest.mark.parametrize(
    "giver,recipient",
    [("Smith, Jr., John", "Zoë O'Brien"), ("Renée", "José Núñez"), ("{", "{{name}} {}")],
)
def test_email_text_matches_input_for_awkward_names(giver, recipient):
    subject = fill("Your match, {giver} {", giver, recipient)
    body = fill("Hi {giver},\n\n{{x}} You buy for {recipient}. {}\n", giver, recipient)
    msg = parse(build_email("ann@example.com", subject, body))
    assert msg["Subject"] == subject
    assert msg.get_content() == body
    assert msg["To"] == "ann@example.com"


def test_plain_text_utf8_and_no_from_header():
    msg = parse(build_email("ann@example.com", "Hi Zoë", "Ünïcode body\n"))
    assert msg.get_content_type() == "text/plain"
    assert msg.get_content_charset() == "utf-8"
    assert msg["From"] is None
    assert not msg.is_multipart()


def test_no_image_means_plain_text_only():
    msg = parse(build_email("a@example.com", "s", "b\n{picture}"))
    assert compose.inline_images(msg) == []
    assert not msg.is_multipart()
    assert msg.get_content() == "b\n"  # the placeholder is dropped


@pytest.mark.parametrize("ext,subtype", [("png", "png"), ("jpg", "jpeg"), ("gif", "gif")])
def test_image_is_shown_inline_in_the_html_version(ext, subtype):
    msg = parse(build_email("a@example.com", "s", "Hi <Ann> & co\n\nbody\n", (PNG, ext)))
    ((name, ctype, data, cid),) = compose.inline_images(msg)
    assert (name, ctype, data) == (f"picture.{ext}", f"image/{subtype}", PNG)
    assert list(msg.iter_attachments()) == []  # inline, not an attachment
    html = msg.get_body(("html",)).get_content()
    assert f'src="cid:{cid[1:-1]}"' in html
    assert html.index("body") < html.index("<img")  # at the end without a placeholder
    assert "Hi &lt;Ann&gt; &amp; co<br>" in html  # text escaped, line breaks kept
    assert msg.get_body(("plain",)).get_content() == "Hi <Ann> & co\n\nbody\n"
    assert msg["From"] is None


def test_picture_placeholder_sets_where_the_picture_goes():
    msg = parse(build_email("a@example.com", "s", "Top\n{picture}\nYou buy for Sam.\n", (PNG, "gif")))
    html = msg.get_body(("html",)).get_content()
    assert html.index("Top") < html.index("<img") < html.index("You buy for Sam.")
    assert msg.get_body(("plain",)).get_content() == "Top\n\nYou buy for Sam.\n"


def test_preview_marks_the_picture():
    assert compose.preview_text("a {picture} b") == "a [picture] b"


def test_unknown_image_type_is_refused():
    with pytest.raises(ValueError):
        build_email("a@example.com", "s", "b", (b"x", "bmp"))


def test_compose_reads_no_storage():
    import inspect

    source = inspect.getsource(compose)
    assert "storage" not in source and "sqlite" not in source


def test_default_body_ends_with_the_match():
    assert DEFAULT_BODY.endswith("You are buying a gift for {recipient}.")
    assert "secret" not in DEFAULT_BODY
