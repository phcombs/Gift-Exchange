"""The Sender protocol and the practice sender, which writes emails to files instead of sending them."""

from typing import Protocol

from giftx import paths
from giftx.model import Outgoing, Rejected, Sent, Unknown


class Sender(Protocol):
    def send(self, msg: Outgoing) -> "Sent | Rejected | Unknown": ...


class PracticeSender:
    """Writes practice/<msg.key>.eml in the data folder. Never contacts anything."""

    @staticmethod
    def path_for(key):
        return paths.practice_root() / f"{key}.eml"

    def send(self, msg):
        path = self.path_for(msg.key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "xb") as f:  # never overwrite an earlier practice email
                f.write(msg.raw)
        except OSError as err:
            return Rejected(f"could not write the practice file ({type(err).__name__})")
        return Sent()
