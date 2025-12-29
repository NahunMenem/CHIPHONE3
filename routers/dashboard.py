from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.deps import get_db
from app.routers.utils import get_current_user

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

@router.get("/")
def dashboard(
    fecha_desde: str,
    fecha_hasta: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    total_ventas_productos = db.execute(text("""
        SELECT SUM(
            v.cantidad *
            CASE
                WHEN v.tipo_precio = 'revendedor' THEN p.precio_revendedor
                ELSE p.precio
            END
        )
        FROM ventas_sj v
        LEFT JOIN productos_sj p ON v.producto_id = p.id
        WHERE DATE(v.fecha) BETWEEN :d AND :h
    """), {"d": fecha_desde, "h": fecha_hasta}).scalar() or 0

    total_ventas_reparaciones = db.execute(text("""
        SELECT SUM(precio)
        FROM reparaciones_sj
        WHERE DATE(fecha) BETWEEN :d AND :h
    """), {"d": fecha_desde, "h": fecha_hasta}).scalar() or 0

    total_ventas = total_ventas_productos + total_ventas_reparaciones

    total_egresos = db.execute(text("""
        SELECT SUM(monto)
        FROM egresos_sj
        WHERE DATE(fecha) BETWEEN :d AND :h
    """), {"d": fecha_desde, "h": fecha_hasta}).scalar() or 0

    total_costo = db.execute(text("""
        SELECT SUM(v.cantidad * p.precio_costo)
        FROM ventas_sj v
        JOIN productos_sj p ON v.producto_id = p.id
        WHERE DATE(v.fecha) BETWEEN :d AND :h
    """), {"d": fecha_desde, "h": fecha_hasta}).scalar() or 0

    ganancia = total_ventas - total_egresos - total_costo

    distribucion = db.execute(text("""
        SELECT 'Productos' AS tipo, SUM(
            v.cantidad *
            CASE
                WHEN v.tipo_precio = 'revendedor' THEN p.precio_revendedor
                ELSE p.precio
            END
        )
        FROM ventas_sj v
        LEFT JOIN productos_sj p ON v.producto_id = p.id
        WHERE DATE(v.fecha) BETWEEN :d AND :h
        UNION ALL
        SELECT 'Reparaciones', SUM(precio)
        FROM reparaciones_sj
        WHERE DATE(fecha) BETWEEN :d AND :h
    """), {"d": fecha_desde, "h": fecha_hasta}).mappings().all()

    return {
        "total_ventas": total_ventas,
        "total_ventas_productos": total_ventas_productos,
        "total_ventas_reparaciones": total_ventas_reparaciones,
        "total_egresos": total_egresos,
        "total_costo": total_costo,
        "ganancia": ganancia,
        "distribucion": distribucion
    }
