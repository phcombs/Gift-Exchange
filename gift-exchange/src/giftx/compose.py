"""Message templates. M3 adds only the defaults new groups start with; M4 adds the rest."""

DEFAULT_SUBJECT = "Gift exchange: your match, {giver}"
DEFAULT_BODY = (
    "Hi {giver},\n\n"
    "This email tells you who you are buying a gift for in this year's gift exchange. The name is "
    "further down, so it does not show up in inbox or Sent-folder previews where someone else might "
    "see it. Scroll down when you are ready to read it.\n\n\n\n\n"
    "You are buying a gift for {recipient}.\n\n"
    "Please keep it a secret!"
)
