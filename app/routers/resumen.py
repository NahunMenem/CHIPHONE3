from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timedelta
from app.deps import get_db
from app.routers.utils import get_current_user

router = APIRouter(prefix="/resumen", tags=["Resumen"])


@router.get("/semanal")
def resumen_semanal(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    hoy = datetime.now()
    inicio_semana = hoy - timedelta(days=hoy.weekday())
    inicio_semana_str = inicio_semana.strftime("%Y-%m-%d")

    resumen = db.execute(text("""
        SELECT tipo_pago, SUM(total) AS total
        FROM ventas_sj
        WHERE fecha >= :inicio
        GROUP BY tipo_pago
    """), {"inicio": inicio_semana_str}).mappings().all()

    return resumen
