from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from tempfile import NamedTemporaryFile
import shutil
import os

from app.core.database import get_db
from app.core.response import success_response, error_response
from app.core.dependencies import get_current_user
from app.services.Excel.excel_parser import load_excel
from app.services.Excel.db_import import run_import
from app.services.Excel.validation import validate_excel_file

router = APIRouter(prefix="/excel", tags=["Excel Import"])


@router.post("/import")
async def import_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
    # current_user = Depends(get_current_user)
):
    # Validate file extension
    if not file.filename.endswith(".xlsx"):
        raise HTTPException(
            status_code=400,
            detail="Only .xlsx files are allowed."
        )

    temp_path = None

    try:
        with NamedTemporaryFile(delete=False, suffix=".xlsx") as temp:      # Save uploaded file
            shutil.copyfileobj(file.file, temp)
            temp_path = temp.name

        # Validate first
        val_result = validate_excel_file(db, temp_path)
        if not val_result["success"]:
            return JSONResponse(
                status_code=400,
                content=val_result
            )

        registers = load_excel(temp_path)              # Load excel rows

        result = run_import(db, registers)         # Import into DB

        return {
            "success": True,
            "message": "Excel imported successfully.",
            "summary": {
                "users": len(result["user_map"]),
                "risk_registers": len(result["risk_register_map"]),
                "risk_descriptions": len(result["description_map"]),
                "risk_treatments": len(result["treatment_map"]),
            }
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)