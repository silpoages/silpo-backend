import enum


class PasswordResetMethod(enum.StrEnum):
    # LINK: long token sent as a link to the web app's reset page.
    # CODE: 6-digit code typed into the mobile app; short, so it's tied to the account's email
    # and only allows a few wrong guesses (see PasswordResetService).
    LINK = "LINK"
    CODE = "CODE"
