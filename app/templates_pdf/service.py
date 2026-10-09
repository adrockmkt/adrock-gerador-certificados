import hashlib
import io
import uuid
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError
from reportlab.lib.pagesizes import A4, landscape

from app.models import PdfTemplate


def store_template(app, name, uploaded):
    name = name.strip()
    if not name or len(name) > 200:
        raise ValueError("Informe um nome de template com até 200 caracteres.")
    if not uploaded or not uploaded.filename or not uploaded.filename.lower().endswith(".pdf"):
        raise ValueError("Selecione um arquivo PDF.")
    data = uploaded.stream.read(app.config["MAX_CONTENT_LENGTH"] + 1)
    if len(data) > app.config["MAX_CONTENT_LENGTH"] or not data.startswith(b"%PDF-"):
        raise ValueError("Arquivo PDF inválido ou acima do limite de tamanho.")
    try:
        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise ValueError("O PDF não pode ter senha.")
        if len(reader.pages) != 1:
            raise ValueError("O template deve ter exatamente uma página.")
        page = reader.pages[0]
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        rotation = int(page.get("/Rotate", 0)) % 360
        if not (50 <= width <= 2000 and 50 <= height <= 2000) or rotation != 0:
            raise ValueError("Dimensões ou rotação do PDF não suportadas.")
    except (PdfReadError, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, ValueError):
            raise
        raise ValueError("Não foi possível ler o PDF.") from exc

    working_data = data
    normalized = False
    if width < 300 or height < 200:
        target_width, target_height = landscape(A4)
        if abs(width / height - target_width / target_height) > 0.03:
            raise ValueError("PDF muito pequeno. Exporte novamente em A4 horizontal.")
        writer = PdfWriter()
        writer.add_page(page)
        writer.pages[0].scale_to(target_width, target_height)
        output = io.BytesIO()
        writer.write(output)
        working_data = output.getvalue()
        width, height = target_width, target_height
        normalized = True

    storage = Path(app.config["PRIVATE_STORAGE_DIR"])
    storage.mkdir(parents=True, exist_ok=True)
    file_key = uuid.uuid4().hex + ".pdf"
    path = storage / file_key
    source_path = storage / file_key.replace(".pdf", ".source.pdf") if normalized else None
    try:
        path.write_bytes(working_data)
        if source_path:
            source_path.write_bytes(data)
        with app.extensions["db_sessionmaker"]() as db:
            template = PdfTemplate(
                name=name,
                file_key=file_key,
                sha256=hashlib.sha256(data).hexdigest(),
                page_width_pt=width,
                page_height_pt=height,
                rotation=rotation,
            )
            db.add(template)
            db.commit()
            return template.id
    except Exception:
        path.unlink(missing_ok=True)
        if source_path:
            source_path.unlink(missing_ok=True)
        raise

