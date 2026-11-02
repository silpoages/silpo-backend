from functools import cache
from pathlib import Path
from string import Template

TEMPLATES_DIR = Path(__file__).parent

CHECK_ICON = (
    '<svg width="22" height="17" viewBox="0 0 22 17" fill="none" aria-hidden="true">'
    '<path d="M1.5625 9.0625L7.8125 15.3125L20.3125 1.5625" stroke="#FFFFFF" '
    'stroke-width="3.125" stroke-linecap="round" stroke-linejoin="round"/></svg>'
)
INFO_ICON = (
    '<svg width="28" height="28" viewBox="0 0 16 16" fill="none" aria-hidden="true">'
    '<circle cx="8" cy="8" r="6.6" stroke="#3F6B57" stroke-width="1.2"/>'
    '<path d="M8 7.2V11" stroke="#3F6B57" stroke-width="1.2" stroke-linecap="round"/>'
    '<circle cx="8" cy="4.9" r="0.8" fill="#3F6B57"/></svg>'
)


@cache
def _load(name: str) -> Template:
    return Template((TEMPLATES_DIR / name).read_text(encoding="utf-8"))


def render_email_confirmation_page(*, confirmed: bool) -> str:
    # Only fixed strings go into the page, so nothing here needs HTML escaping.
    if confirmed:
        values = {
            "badge": f'<div class="badge badge--confirmed">{CHECK_ICON}</div>',
            "title": "E-mail confirmado",
            "message": ("Tudo certo com o seu cadastro."),
            "hint": "Você já pode <strong>fechar esta página</strong>.",
        }
    else:
        values = {
            "badge": f'<div class="badge badge--invalid">{INFO_ICON}</div>',
            "title": "Link inválido",
            "message": "Este link de confirmação expirou ou já foi usado.",
            "hint": (
                "Se você já confirmou seu e-mail, é só <strong>entrar no app Silpo</strong>. "
                "Se não, peça um novo e-mail de confirmação pelo app."
            ),
        }
    return _load("email_confirmation.html").substitute(values)
