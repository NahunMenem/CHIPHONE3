from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime
import pytz
from app.deps import get_db
from app.routers.utils import get_current_user

router = APIRouter(prefix="/caja", tags=["Caja"])

@router.get("/")
def caja(
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    argentina_tz = pytz.timezone("America/Argentina/Buenos_Aires")
    hoy = datetime.now(argentina_tz).date()

    fecha_desde = fecha_desde or hoy.strftime("%Y-%m-%d")
    fecha_hasta = fecha_hasta or hoy.strftime("%Y-%m-%d")

    ventas = db.execute(text("""
        SELECT 
            v.tipo_pago,
            (v.cantidad *
             CASE
                WHEN v.tipo_precio = 'revendedor' THEN p.precio_revendedor
                ELSE p.precio
             END) AS total
        FROM ventas_sj v
        JOIN productos_sj p ON v.producto_id = p.id
        WHERE DATE(v.fecha) BETWEEN :d AND :h
    """), {"d": fecha_desde, "h": fecha_hasta}).mappings().all()

    reparaciones = db.execute(text("""
        SELECT tipo_pago, (cantidad * precio) AS total
        FROM reparaciones_sj
        WHERE DATE(fecha) BETWEEN :d AND :h
    """), {"d": fecha_desde, "h": fecha_hasta}).mappings().all()

    egresos = db.execute(text("""
        SELECT tipo_pago, monto
        FROM egresos_sj
        WHERE DATE(fecha) BETWEEN :d AND :h
    """), {"d": fecha_desde, "h": fecha_hasta}).mappings().all()

    total_ingresos = {}
    for v in ventas:
        total_ingresos[v["tipo_pago"]] = total_ingresos.get(v["tipo_pago"], 0) + v["total"]

    for r in reparaciones:
        total_ingresos[r["tipo_pago"]] = total_ingresos.get(r["tipo_pago"], 0) + r["total"]

    total_egresos = {}
    for e in egresos:
        total_egresos[e["tipo_pago"]] = total_egresos.get(e["tipo_pago"], 0) + e["monto"]

    neto_por_pago = {}
    for tipo, total in total_ingresos.items():
        neto_por_pago[tipo] = total - total_egresos.get(tipo, 0)

    return {
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "neto_por_pago": neto_por_pago
    }
