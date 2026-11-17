import inspect

from google_auth_oauthlib.flow import InstalledAppFlow


def test_run_local_server_has_timeout_seconds():
    params = inspect.signature(InstalledAppFlow.run_local_server).parameters
    assert "timeout_seconds" in params
