from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timedelta
import unicodedata
from app.deps import get_db
from app.routers.utils import get_current_user
from pydantic import BaseModel

router = APIRouter(prefix="/reparaciones", tags=["Reparaciones"])

def normalizar(texto: str):
    return unicodedata.normalize("NFKD", texto)\
        .encode("ASCII", "ignore")\
        .decode()\
        .lower()\
        .strip()

class ReparacionIn(BaseModel):
    tipo_reparacion: str
    marca: str
    modelo: str
    tecnico: str
    monto: float
    nombre_cliente: str
    telefono: str
    nro_orden: str


@router.post("/")
def crear_reparacion(
    data: ReparacionIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    fecha = datetime.now().date()
    hora = datetime.now().strftime("%H:%M:%S")

    db.execute(text("""
        INSERT INTO equipos_sj (
            tipo_reparacion, marca, modelo, tecnico, monto,
            nombre_cliente, telefono, nro_orden, fecha, hora, estado
        ) VALUES (
            :tr, :ma, :mo, :te, :m, :nc, :tel, :nro, :f, :h, 'Por Reparar'
        )
    """), {
        "tr": data.tipo_reparacion,
        "ma": data.marca,
        "mo": data.modelo,
        "te": data.tecnico,
        "m": data.monto,
        "nc": data.nombre_cliente,
        "tel": data.telefono,
        "nro": data.nro_orden,
        "f": fecha,
        "h": hora
    })

    db.commit()
    return {"message": "Reparación registrada"}

@router.get("/")
def resumen_reparaciones(
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    fecha_desde = fecha_desde or (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    fecha_hasta = fecha_hasta or datetime.now().strftime("%Y-%m-%d")

    equipos = db.execute(text("""
        SELECT * FROM equipos_sj
        WHERE fecha BETWEEN :d AND :h
        ORDER BY nro_orden DESC
    """), {"d": fecha_desde, "h": fecha_hasta}).mappings().all()

    tecnicos = db.execute(text("""
        SELECT tecnico, COUNT(*) AS cantidad
        FROM equipos_sj
        WHERE fecha BETWEEN :d AND :h
        GROUP BY tecnico
    """), {"d": fecha_desde, "h": fecha_hasta}).mappings().all()

    estados_raw = db.execute(text("""
        SELECT estado, COUNT(*) AS cantidad
        FROM equipos_sj
        WHERE fecha BETWEEN :d AND :h
        GROUP BY estado
    """), {"d": fecha_desde, "h": fecha_hasta}).mappings().all()

    estados = {
        "por_reparar": 0,
        "en_reparacion": 0,
        "listo": 0,
        "retirado": 0,
        "no_salio": 0
    }

    for e in estados_raw:
        estado = normalizar(e["estado"])
        estados[estado] = estados.get(estado, 0) + e["cantidad"]

    estados["total"] = sum(v for k, v in estados.items())

    return {
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "equipos": equipos,
        "equipos_por_tecnico": tecnicos,
        "estados": estados
    }

class EstadoIn(BaseModel):
    nro_orden: str
    estado: str

@router.put("/estado")
def actualizar_estado(
    data: EstadoIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    actualizado = db.execute(text("""
        UPDATE equipos_sj
        SET estado = :estado
        WHERE nro_orden = :nro
    """), {
        "estado": data.estado,
        "nro": data.nro_orden
    }).rowcount

    if not actualizado:
        raise HTTPException(status_code=404, detail="Orden no encontrada")

    db.commit()
    return {"success": True}
