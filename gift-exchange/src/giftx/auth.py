# Import rule: callers write "from giftx import auth" and call auth.sign_in(...),
# never "from giftx.auth import sign_in", so a patched function is the one called.


def sign_in(timeout=120):
    raise NotImplementedError("sign-in arrives in a later milestone")
