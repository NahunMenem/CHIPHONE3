from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.deps import get_db
from app.routers.utils import get_current_user
from pydantic import BaseModel
from datetime import datetime

router = APIRouter(prefix="/mercaderia_fallada", tags=["Mercadería fallada"])

@router.get("/buscar")
def buscar_producto(
    q: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    return db.execute(text("""
        SELECT id, nombre, codigo_barras, stock, precio, precio_costo
        FROM productos_sj
        WHERE nombre ILIKE :q OR codigo_barras ILIKE :q
    """), {"q": f"%{q}%"}).mappings().all()

class FalladaIn(BaseModel):
    producto_id: int
    cantidad: int
    descripcion: str

@router.post("/")
def registrar_fallada(
    data: FalladaIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    prod = db.execute(
        text("SELECT stock FROM productos_sj WHERE id = :id"),
        {"id": data.producto_id}
    ).scalar()

    if prod is None or prod < data.cantidad:
        raise HTTPException(status_code=400, detail="Stock insuficiente")

    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    db.execute(text("""
        INSERT INTO mercaderia_fallada (producto_id, cantidad, fecha, descripcion)
        VALUES (:pid, :c, :f, :d)
    """), {
        "pid": data.producto_id,
        "c": data.cantidad,
        "f": fecha,
        "d": data.descripcion
    })

    db.execute(text("""
        UPDATE productos_sj
        SET stock = stock - :c
        WHERE id = :id
    """), {
        "c": data.cantidad,
        "id": data.producto_id
    })

    db.commit()
    return {"message": "Mercadería fallada registrada"}

@router.get("/")
def historial_fallada(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    return db.execute(text("""
        SELECT mf.id, p.nombre, mf.cantidad, mf.fecha, mf.descripcion
        FROM mercaderia_fallada mf
        JOIN productos_sj p ON mf.producto_id = p.id
        ORDER BY mf.fecha DESC
    """)).mappings().all()
