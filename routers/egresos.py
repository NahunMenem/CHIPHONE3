from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.deps import get_db
from app.routers.utils import get_current_user
from pydantic import BaseModel

router = APIRouter(prefix="/egresos", tags=["Egresos"])

class EgresoIn(BaseModel):
    fecha: str
    monto: float
    descripcion: str
    tipo_pago: str

@router.post("/")
def crear_egreso(
    data: EgresoIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    db.execute(text("""
        INSERT INTO egresos_sj (fecha, monto, descripcion, tipo_pago)
        VALUES (:f, :m, :d, :tp)
    """), {
        "f": data.fecha,
        "m": data.monto,
        "d": data.descripcion,
        "tp": data.tipo_pago
    })
    db.commit()
    return {"message": "Egreso registrado"}

@router.get("/")
def listar_egresos(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    egresos = db.execute(text("""
        SELECT id, fecha, monto, descripcion, tipo_pago
        FROM egresos_sj
        ORDER BY fecha DESC
    """)).mappings().all()

    return egresos


@router.delete("/{egreso_id}")
def eliminar_egreso(
    egreso_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    eliminado = db.execute(
        text("DELETE FROM egresos_sj WHERE id = :id"),
        {"id": egreso_id}
    ).rowcount

    if not eliminado:
        raise HTTPException(status_code=404, detail="Egreso no encontrado")

    db.commit()
    return {"message": "Egreso eliminado"}
