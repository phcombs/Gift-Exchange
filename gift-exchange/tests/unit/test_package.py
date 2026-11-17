import giftx


def test_app_name():
    assert giftx.APP_NAME == "Gift Exchange"


def test_schema_version():
    assert giftx.SCHEMA_VERSION == 1
