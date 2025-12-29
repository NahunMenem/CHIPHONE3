from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.deps import get_db
from app.routers.utils import get_current_user

router = APIRouter(prefix="/productos", tags=["Productos"])

@router.get("/mas_vendidos")
def productos_mas_vendidos(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    productos = db.execute(text("""
        SELECT nombre, precio, cantidad_vendida
        FROM productos_sj
        ORDER BY cantidad_vendida DESC
        LIMIT 5
    """)).fetchall()

    total_ventas = db.execute(
        text("SELECT SUM(cantidad_vendida) FROM productos_sj")
    ).scalar() or 0

    resultado = []
    for nombre, precio, cantidad in productos:
        porcentaje = (cantidad / total_ventas * 100) if total_ventas else 0
        resultado.append({
            "nombre": nombre,
            "precio": precio,
            "cantidad_vendida": cantidad,
            "porcentaje": round(porcentaje, 2)
        })

    return {
        "total_ventas": total_ventas,
        "productos": resultado
    }


@router.get("/por_agotarse")
def productos_por_agotarse(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    productos = db.execute(text("""
        SELECT id, nombre, codigo_barras, stock, precio, precio_costo
        FROM productos_sj
        WHERE stock <= 2
        ORDER BY stock ASC
    """)).mappings().all()

    return productos
