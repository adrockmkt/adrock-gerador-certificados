import re
import unicodedata


def _slug(value, fallback, limit):
    ascii_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug[:limit].rstrip("-") or fallback


def certificate_filename(event_title, first_name, last_name, participant_id):
    event = _slug(event_title, "evento", 60)
    person = _slug(f"{first_name} {last_name}", "participante", 80)
    return f"certificado-{event}-{person}-{participant_id}.pdf"


def batch_filename(event_title, batch_id):
    event = _slug(event_title, "evento", 60)
    return f"certificados-{event}-lote-{batch_id}.zip"
