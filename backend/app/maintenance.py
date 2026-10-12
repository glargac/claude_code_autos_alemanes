"""Tareas de mantenimiento puntuales. Uso (desde backend/, con el entorno virtual):

    python -m app.maintenance purge-damaged [--dry-run]

purge-damaged: quita de la base los anuncios de kleinanzeigen marcados como "Beschädigtes Fahrzeug" que se
guardaron antes de que la búsqueda los excluyera. No toca los que tienen seguimiento (estado, notas o cita).
"""
import argparse
import asyncio

from sqlalchemy import select

from .database import SessionLocal, ensure_columns
from .models import Car
from .scrapers.kleinanzeigen import KleinanzeigenScraper
from .services.dedupe import apply_duplicates
from .services.scope import has_followup
from .services.settings_store import get_setting
from .services.sync import rescore_all


async def purge_damaged(dry_run: bool = False) -> dict:
    ensure_columns()
    with SessionLocal() as db:
        scraper = KleinanzeigenScraper()
        damaged = await scraper.damaged_ids(get_setting(db, "search"))
        rows = db.scalars(select(Car).where(Car.source == "kleinanzeigen", Car.external_id.in_(damaged))).all()
        protected = [c for c in rows if has_followup(c)]
        to_delete = [c for c in rows if not has_followup(c)]
        if not dry_run:
            for car in to_delete:
                db.delete(car)
            db.commit()
            apply_duplicates(db)
            rescore_all(db)
        return {
            "dañados_en_kleinanzeigen": len(damaged),
            "en_tu_base": len(rows),
            "borrados" if not dry_run else "se_borrarían": len(to_delete),
            "protegidos_por_seguimiento": [(c.id, c.titel[:50]) for c in protected],
            "avisos": scraper.warnings,
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("task", choices=["purge-damaged"])
    parser.add_argument("--dry-run", action="store_true", help="solo cuenta, no borra")
    args = parser.parse_args()
    print(asyncio.run(purge_damaged(args.dry_run)))
