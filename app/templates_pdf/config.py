import math
import re


FIELD_KEYS = {"nome", "sobrenome", "nome_completo"}
ALIGNMENTS = {"left", "center", "right"}
COLORS = re.compile(r"^#[0-9A-Fa-f]{6}$")
FIELD_IDS = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def validate_fields(fields, page_width, page_height):
    if not isinstance(fields, list) or not 1 <= len(fields) <= 20:
        raise ValueError("Configure de 1 a 20 campos.")
    normalized = []
    used_ids = set()
    for item in fields:
        if not isinstance(item, dict):
            raise ValueError("Campo inválido.")
        field_id = item.get("id")
        if not isinstance(field_id, str) or not FIELD_IDS.fullmatch(field_id) or field_id in used_ids:
            raise ValueError("Identificador de campo inválido ou duplicado.")
        used_ids.add(field_id)
        if item.get("key") not in FIELD_KEYS:
            raise ValueError("Selecione um campo dinâmico válido.")
        x = _number(item.get("x_pt"), "posição X")
        y = _number(item.get("y_pt"), "posição Y")
        width = _number(item.get("width_pt"), "largura")
        size = _number(item.get("font_size_pt"), "tamanho da fonte")
        min_size = _number(item.get("min_font_size_pt"), "tamanho mínimo da fonte")
        height = _number(item.get("height_pt", size * 2.5), "altura")
        max_lines = item.get("max_lines", 1)
        if not (0 <= x < page_width and 0 <= y <= page_height and 1 <= width <= page_width - x):
            raise ValueError("O campo deve permanecer dentro da página PDF.")
        if not (6 <= min_size <= size <= 72):
            raise ValueError("Tamanho de fonte inválido.")
        if isinstance(max_lines, bool) or max_lines not in (1, 2):
            raise ValueError("O campo deve ter uma ou duas linhas.")
        if not (height >= min_size * (2.6 if max_lines == 2 else 1.5)
                and height / 2 <= y <= page_height - height / 2):
            raise ValueError("A altura do campo deve caber na página e acomodar as linhas.")
        color = item.get("color")
        if not isinstance(color, str) or not COLORS.fullmatch(color):
            raise ValueError("A cor deve estar no formato hexadecimal #RRGGBB.")
        if item.get("align") not in ALIGNMENTS:
            raise ValueError("Alinhamento inválido.")
        family = item.get("font_family")
        weight = item.get("font_weight")
        if (family, weight) not in {("Helvetica", "regular"),
                                    ("Montserrat", "regular"), ("Montserrat", "semibold"),
                                    ("Lato", "regular"), ("Lato", "semibold"),
                                    ("Poppins", "regular"), ("Poppins", "semibold")}:
            raise ValueError("Fonte não disponível nesta etapa.")
        normalized.append({
            "id": field_id, "key": item["key"], "x_pt": x, "y_pt": y,
            "width_pt": width, "font_family": family, "font_weight": weight,
            "font_size_pt": size, "min_font_size_pt": min_size,
            "height_pt": height, "max_lines": max_lines,
            "color": color.upper(), "align": item["align"],
        })
    return normalized


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"Valor inválido para {label}.")
    return float(value)
