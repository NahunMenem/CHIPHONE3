from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.deps import get_db
from app.routers.utils import get_current_user
import cloudinary.uploader

router = APIRouter(prefix="/stock", tags=["Stock"])

@router.get("/categorias")
def listar_categorias(db: Session = Depends(get_db)):
    return db.execute(
        text("SELECT nombre FROM categorias_sj ORDER BY nombre")
    ).scalars().all()

@router.post("/categorias")
def crear_categoria(nombre: str, db: Session = Depends(get_db)):
    db.execute(
        text("INSERT INTO categorias_sj (nombre) VALUES (:n) ON CONFLICT DO NOTHING"),
        {"n": nombre}
    )
    db.commit()
    return {"message": "Categoría creada"}

@router.delete("/categorias/{nombre}")
def eliminar_categoria(nombre: str, db: Session = Depends(get_db)):
    db.execute(
        text("DELETE FROM categorias_sj WHERE nombre = :n"),
        {"n": nombre}
    )
    db.commit()
    return {"message": "Categoría eliminada"}

@router.get("/")
def listar_productos(
    q: str | None = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    sql = """
        SELECT id, nombre, codigo_barras, stock, precio, precio_costo, foto_url,
               num, color, bateria, precio_revendedor, condicion
        FROM productos_sj
    """
    params = {}
    if q:
        sql += " WHERE nombre ILIKE :q OR codigo_barras ILIKE :q OR num ILIKE :q"
        params["q"] = f"%{q}%"

    return db.execute(text(sql), params).mappings().all()
