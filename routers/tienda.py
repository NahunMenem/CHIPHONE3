from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.deps import get_db

router = APIRouter(prefix="/tienda", tags=["Tienda"])

@router.get("/")
def tienda(categoria: str | None = None, db: Session = Depends(get_db)):
    if categoria:
        productos = db.execute(text("""
            SELECT *
            FROM productos_sj
            WHERE categoria = :c AND foto_url IS NOT NULL AND stock > 0
            ORDER BY nombre
        """), {"c": categoria}).mappings().all()
    else:
        productos = db.execute(text("""
            SELECT *
            FROM productos_sj
            WHERE foto_url IS NOT NULL AND stock > 0
            ORDER BY nombre
        """)).mappings().all()

    categorias = db.execute(
        text("SELECT DISTINCT categoria FROM productos_sj WHERE categoria IS NOT NULL ORDER BY categoria")
    ).scalars().all()

    return {
        "productos": productos,
        "categorias": categorias,
        "categoria_seleccionada": categoria
    }
