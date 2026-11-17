from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[2] / "streamlit_app.py")

PRACTICE = "Practice mode: nothing is emailed"
REAL = "Real mode: emails are sent from your Gmail"


def load():
    at = AppTest.from_file(APP)
    at.run(timeout=30)
    assert not at.exception
    return at


def test_practice_banner_on_first_load():
    at = load()
    assert [i.value for i in at.info] == [PRACTICE]
    assert len(at.warning) == 0


def test_real_banner_after_switching_mode():
    at = load()
    at.sidebar.radio(key="mode").set_value("real").run(timeout=30)
    assert not at.exception
    assert [w.value for w in at.warning] == [REAL]
    assert len(at.info) == 0


def test_group_selector_is_empty():
    at = load()
    group = at.sidebar.selectbox(key="group_id")
    assert list(group.options) == []
    assert group.value is None
    assert at.session_state["group_id"] is None


def test_mode_defaults_to_practice():
    at = load()
    assert at.sidebar.radio(key="mode").value == "practice"


def test_main_area_holds_only_the_banner():
    at = load()
    assert len(at.main.children) == 1
    assert len(at.info) == 1
