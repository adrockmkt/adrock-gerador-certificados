import csv
import io
import re
import unicodedata


MAX_ROWS = 500
MAX_COLUMNS = 50


def parse_csv(data):
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("O CSV deve estar em UTF-8.") from exc
    if not text.strip() or "\x00" in text:
        raise ValueError("CSV vazio ou inválido.")
    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;")
    except csv.Error:
        dialect = csv.excel
    try:
        rows = list(csv.reader(io.StringIO(text, newline=""), dialect, strict=True))
    except csv.Error as exc:
        raise ValueError("Não foi possível ler a estrutura do CSV.") from exc
    if not rows or len(rows) <= 1 or len(rows) - 1 > MAX_ROWS:
        raise ValueError(f"O CSV deve ter de 1 a {MAX_ROWS} linhas de dados.")
    headers = [value.strip() for value in rows[0]]
    if not headers or len(headers) > MAX_COLUMNS or any(not header for header in headers) or len(set(headers)) != len(headers):
        raise ValueError("Cabeçalho inválido ou com colunas repetidas.")
    return headers, rows[1:]


def review_rows(headers, rows, first_col, last_col):
    if first_col not in headers or last_col not in headers or first_col == last_col:
        raise ValueError("Mapeie colunas diferentes para nome e sobrenome.")
    first_index = headers.index(first_col)
    last_index = headers.index(last_col)
    valid = []
    invalid = []
    seen = set()
    duplicates = 0
    for source_row, row in enumerate(rows, start=2):
        if len(row) != len(headers):
            invalid.append((source_row, "Número de colunas diferente do cabeçalho"))
            continue
        first = _clean(row[first_index])
        last = _clean(row[last_index])
        if not first or not last or len(first) > 200 or len(last) > 200:
            invalid.append((source_row, "Nome ou sobrenome vazio ou extenso demais"))
            continue
        full_key = f"{first} {last}".casefold()
        if full_key in seen:
            duplicates += 1
        seen.add(full_key)
        valid.append((source_row, first, last))
    return valid, invalid, duplicates


def _clean(value):
    return unicodedata.normalize("NFC", re.sub(r"\s+", " ", value).strip())

