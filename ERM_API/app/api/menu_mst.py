from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.response import success_response, error_response

from app.models.menu_mst import Menu

router = APIRouter(prefix="/menu_map", 
                   tags=["Menu_Map"],
                   dependencies=[Depends(get_current_user)]
                   )


# Get ALL the records from the menu table
@router.get("/menus")
def get_all_menus(db: Session = Depends(get_db)):

    try:
        menus = db.query(Menu).filter(Menu.is_deleted == 0).all()

        response = []
        for menu in menus:
            response.append({
                "menu_id": menu.menu_id,
                "menu_name": menu.menu_name
            })

        return success_response(response)
    
    except Exception as e:
        return error_response(str(e), 400)
