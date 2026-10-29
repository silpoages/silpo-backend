import enum


class EmailProvider(enum.StrEnum):
    # RESEND needs a verified sending domain to reach anyone but the Resend account owner;
    # SMTP lets a developer send through their own mailbox (e.g. Gmail with an app password).
    RESEND = "resend"
    SMTP = "smtp"
