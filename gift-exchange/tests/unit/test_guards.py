import os
import socket
from pathlib import Path

import pytest

from giftx import auth, gmail


def test_connect_is_blocked():
    s = socket.socket()
    try:
        with pytest.raises(pytest.fail.Exception):
            s.connect(("127.0.0.1", 9))
    finally:
        s.close()


def test_connect_ex_is_blocked():
    s = socket.socket()
    try:
        with pytest.raises(pytest.fail.Exception):
            s.connect_ex(("127.0.0.1", 9))
    finally:
        s.close()


def test_create_connection_is_blocked():
    with pytest.raises(pytest.fail.Exception):
        socket.create_connection(("127.0.0.1", 9))


def test_gmail_sender_is_blocked():
    with pytest.raises(pytest.fail.Exception):
        gmail.GmailSender(object())


def test_sign_in_is_blocked():
    with pytest.raises(pytest.fail.Exception):
        auth.sign_in()


def test_data_dir_is_inside_tmp_path(tmp_path):
    data = Path(os.environ["GIFTX_DATA_DIR"])
    assert tmp_path in data.parents


def test_guard_exception_is_not_an_exception_subclass():
    assert not issubclass(pytest.fail.Exception, Exception)
