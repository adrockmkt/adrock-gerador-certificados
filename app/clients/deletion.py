import re
import shutil
from pathlib import Path

from sqlalchemy import delete, func, select

from app.models import Certificate, CsvImport, Event, GenerationBatch, Participant


_CSV_KEY = re.compile(r"^[0-9a-f]{32}\.csv$")


def deletion_summary(db, event_ids):
    if not event_ids:
        return {"events": 0, "imports": 0, "participants": 0, "batches": 0, "certificates": 0}
    batch_ids = select(GenerationBatch.id).where(GenerationBatch.event_id.in_(event_ids))
    return {
        "events": len(event_ids),
        "imports": db.scalar(select(func.count()).select_from(CsvImport).where(CsvImport.event_id.in_(event_ids))),
        "participants": db.scalar(select(func.count()).select_from(Participant).where(Participant.event_id.in_(event_ids))),
        "batches": db.scalar(select(func.count()).select_from(GenerationBatch).where(GenerationBatch.event_id.in_(event_ids))),
        "certificates": db.scalar(select(func.count()).select_from(Certificate).where(Certificate.batch_id.in_(batch_ids))),
    }


def delete_events(db, event_ids):
    """Delete event-owned rows in FK order; caller commits the transaction."""
    if not event_ids:
        return [], []
    batch_ids = db.scalars(select(GenerationBatch.id).where(GenerationBatch.event_id.in_(event_ids))).all()
    csv_keys = db.scalars(select(CsvImport.file_key).where(CsvImport.event_id.in_(event_ids))).all()
    if batch_ids:
        db.execute(delete(Certificate).where(Certificate.batch_id.in_(batch_ids)))
    db.execute(delete(GenerationBatch).where(GenerationBatch.event_id.in_(event_ids)))
    db.execute(delete(Participant).where(Participant.event_id.in_(event_ids)))
    db.execute(delete(CsvImport).where(CsvImport.event_id.in_(event_ids)))
    db.execute(delete(Event).where(Event.id.in_(event_ids)))
    return batch_ids, csv_keys


def remove_private_files(storage_dir, batch_ids, csv_keys):
    """Remove only app-generated paths, never shared PDF templates."""
    storage = Path(storage_dir).resolve()
    for key in csv_keys:
        if not _CSV_KEY.fullmatch(key):
            raise ValueError("Chave de importação inválida; limpeza interrompida.")
        path = storage / key
        if not path.resolve().is_relative_to(storage):
            raise ValueError("Caminho de importação fora do armazenamento privado.")
        path.unlink(missing_ok=True)
    for batch_id in batch_ids:
        path = storage / "generated" / str(batch_id)
        if not path.resolve().is_relative_to(storage):
            raise ValueError("Caminho de lote fora do armazenamento privado.")
        if path.exists():
            shutil.rmtree(path)
