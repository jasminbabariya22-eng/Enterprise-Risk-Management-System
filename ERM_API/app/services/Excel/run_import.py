import logging
import sys
from pathlib import Path

ROOT_DIR = r"D:\ESM"
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.core.config import settings
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.services.Excel.excel_parser import load_excel, to_flat_dataframe
from app.services.Excel.db_import import run_import


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("risk_import")


def main(excel_path: str, dry_run: bool = False, debug: bool = False):
    if debug:
        logging.getLogger("risk_import").setLevel(logging.DEBUG)

    logger.info("Reading %s", excel_path)
    registers = load_excel(excel_path)
    logger.info(
        "Parsed %d risk registers / %d descriptions / %d treatments",
        len(registers),
        sum(len(r.descriptions) for r in registers),
        sum(len(d.treatments) for r in registers for d in r.descriptions),
    )

    if dry_run:
        preview = to_flat_dataframe(registers)
        out = Path(excel_path).with_suffix(".preview.csv")
        preview.to_csv(out, index=False)
        logger.info("Dry run only -- wrote preview to %s", out)
        return

    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    logger.info("Database connected")

    try:
        result = run_import(db, registers)
        logger.info(
            "Done: %d users, %d registers, %d descriptions, %d treatments",
            len(result["user_map"]), len(result["risk_register_map"]),
            len(result["description_map"]), len(result["treatment_map"]),
        )
    finally:
        db.close()


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else r"D:\ESM\app\services\Excel\Final_Tempelate.xlsx"
    dry = "--dry-run" in sys.argv
    dbg = "--debug" in sys.argv
    main(path, dry_run=dry, debug=dbg)