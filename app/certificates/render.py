import io
import re
import unicodedata
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


FONT_FILES = {
    ("Helvetica", "regular"): None,
    ("Montserrat", "regular"): "montserrat/Montserrat-Regular.ttf",
    ("Montserrat", "semibold"): "montserrat/Montserrat-SemiBold.ttf",
    ("Lato", "regular"): "lato/Lato-Regular.ttf",
    ("Lato", "semibold"): "lato/Lato-SemiBold.ttf",
    ("Poppins", "regular"): "poppins/Poppins-Regular.ttf",
    ("Poppins", "semibold"): "poppins/Poppins-SemiBold.ttf",
}
FONT_NAMES = {
    ("Helvetica", "regular"): "Helvetica",
    ("Montserrat", "regular"): "AdRockMontserratRegular",
    ("Montserrat", "semibold"): "AdRockMontserratSemiBold",
    ("Lato", "regular"): "AdRockLatoRegular",
    ("Lato", "semibold"): "AdRockLatoSemiBold",
    ("Poppins", "regular"): "AdRockPoppinsRegular",
    ("Poppins", "semibold"): "AdRockPoppinsSemiBold",
}


def font_name(family, weight):
    key = (family, weight)
    if key not in FONT_NAMES:
        raise ValueError("Fonte ou variante não disponível.")
    name = FONT_NAMES[key]
    filename = FONT_FILES[key]
    if filename and name not in pdfmetrics.getRegisteredFontNames():
        path = Path(__file__).resolve().parents[1] / "static" / "fonts" / filename
        pdfmetrics.registerFont(TTFont(name, str(path)))
    return name


def fit_font_size(text, family, weight, preferred, minimum, width):
    name = font_name(family, weight)
    text_width_at_one = pdfmetrics.stringWidth(text, name, 1)
    size = min(float(preferred), float(width) / text_width_at_one) if text_width_at_one else float(preferred)
    if size + 1e-9 >= float(minimum):
        return size
    raise ValueError("O texto não cabe na largura mínima configurada.")


def _layout_lines(text, field, name):
    preferred = float(field["font_size_pt"])
    minimum = float(field["min_font_size_pt"])
    width = float(field["width_pt"])
    height = float(field.get("height_pt", preferred * 2.5))
    ascent, descent = pdfmetrics.getAscentDescent(name, 1)
    glyph_height = max(ascent - descent, 0.1)

    def size_for(lines):
        widest = max(pdfmetrics.stringWidth(line, name, 1) for line in lines)
        width_limit = width / widest if widest else preferred
        height_limit = height / (glyph_height + (len(lines) - 1) * 1.15)
        return min(preferred, width_limit, height_limit)

    single_size = size_for([text])
    best_lines = None
    best_size = 0.0
    best_score = 0.0
    best_balance = float("inf")
    if field.get("max_lines", 1) == 2:
        words = text.split(" ")
        for split in range(1, len(words)):
            lines = [" ".join(words[:split]), " ".join(words[split:])]
            size = size_for(lines)
            widest = max(pdfmetrics.stringWidth(line, name, 1) for line in lines)
            ends_with_particle = words[split - 1].casefold() in {"de", "da", "do", "das", "dos", "e"}
            score = size * (0.9 if ends_with_particle else 1)
            if score > best_score + 1e-9 or (abs(score - best_score) <= 1e-9 and widest < best_balance):
                best_lines, best_size, best_score, best_balance = lines, size, score, widest

    if single_size + 1e-9 >= minimum and (single_size >= preferred * 0.65 or best_size <= single_size * 1.15):
        return [text], single_size
    if best_lines and best_size + 1e-9 >= minimum:
        return best_lines, best_size
    if single_size + 1e-9 >= minimum:
        return [text], single_size
    raise ValueError("O nome não cabe na área configurada, mesmo em duas linhas.")


def render_certificate(original_pdf, fields, first_name, last_name):
    first = _clean_name(first_name)
    last = _clean_name(last_name)
    if not first or not last:
        raise ValueError("Nome e sobrenome são obrigatórios.")
    values = {"nome": first, "sobrenome": last, "nome_completo": f"{first} {last}"}
    base = PdfReader(io.BytesIO(original_pdf), strict=True)
    if base.is_encrypted or len(base.pages) != 1:
        raise ValueError("Template PDF inválido.")
    page = base.pages[0]
    width = float(page.mediabox.width)
    height = float(page.mediabox.height)
    overlay_bytes = io.BytesIO()
    overlay = canvas.Canvas(overlay_bytes, pagesize=(width, height))
    for field in fields:
        text = values[field["key"]]
        name = font_name(field["font_family"], field["font_weight"])
        lines, size = _layout_lines(text, field, name)
        overlay.setFillColor(HexColor(field["color"]))
        overlay.setFont(name, size)
        line_height = size * 1.15
        for index, line in enumerate(lines):
            text_width = pdfmetrics.stringWidth(line, name, size)
            x = field["x_pt"]
            if field["align"] == "center":
                x += (field["width_pt"] - text_width) / 2
            elif field["align"] == "right":
                x += field["width_pt"] - text_width
            y = field["y_pt"] + ((len(lines) - 1) / 2 - index) * line_height
            overlay.drawString(x, y, line)
    overlay.showPage()
    overlay.save()
    overlay_bytes.seek(0)
    writer = PdfWriter()
    writer.append(base)
    writer.pages[0].merge_page(PdfReader(overlay_bytes).pages[0])
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _clean_name(value):
    if not isinstance(value, str) or len(value) > 200:
        raise ValueError("Nome inválido.")
    return unicodedata.normalize("NFC", re.sub(r"\s+", " ", value).strip())
