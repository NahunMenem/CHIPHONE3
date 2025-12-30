from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.deps import get_db
from app.routers.utils import get_current_user
from pydantic import BaseModel
from datetime import datetime
import pytz

router = APIRouter(
    prefix="/ventas",
    tags=["Ventas"]
)


class ItemVenta(BaseModel):
    producto_id: int | None
    nombre: str
    cantidad: int
    precio: float
    tipo_precio: str

class VentaIn(BaseModel):
    items: list[ItemVenta]
    tipo_pago: str
    dni_cliente: str
    tipo_precio_global: str = "venta"


@router.post("/registrar")
def registrar_venta(
    data: VentaIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    if not data.items:
        raise HTTPException(status_code=400, detail="Carrito vacío")

    argentina_tz = pytz.timezone("America/Argentina/Buenos_Aires")
    fecha = datetime.now(argentina_tz)

    for item in data.items:
        if item.producto_id:
            prod = db.execute(
                text("""
                    SELECT stock, precio, precio_revendedor
                    FROM productos_sj
                    WHERE id = :id
                """),
                {"id": item.producto_id}
            ).mappings().first()

            if not prod or prod["stock"] < item.cantidad:
                raise HTTPException(
                    status_code=400,
                    detail=f"Stock insuficiente para {item.nombre}"
                )

            precio = (
                prod["precio_revendedor"]
                if data.tipo_precio_global == "revendedor" and prod["precio_revendedor"]
                else prod["precio"]
            )

            db.execute(text("""
                INSERT INTO ventas_sj
                (producto_id, cantidad, fecha, nombre_manual, tipo_pago, dni_cliente, tipo_precio)
                VALUES (:pid, :cant, :fecha, :nombre, :tp, :dni, :tipo_precio)
            """), {
                "pid": item.producto_id,
                "cant": item.cantidad,
                "fecha": fecha,
                "nombre": item.nombre,
                "tp": data.tipo_pago,
                "dni": data.dni_cliente,
                "tipo_precio": data.tipo_precio_global
            })

            db.execute(text("""
                UPDATE productos_sj
                SET stock = stock - :cant
                WHERE id = :id
            """), {
                "cant": item.cantidad,
                "id": item.producto_id
            })

        else:
            db.execute(text("""
                INSERT INTO reparaciones_sj
                (nombre_servicio, precio, cantidad, tipo_pago, dni_cliente, fecha)
                VALUES (:n, :p, :c, :tp, :dni, :f)
            """), {
                "n": item.nombre,
                "p": item.precio,
                "c": item.cantidad,
                "tp": data.tipo_pago,
                "dni": data.dni_cliente,
                "f": fecha
            })

    db.commit()

    return {"message": "Venta registrada con éxito"}


@router.post("/carrito/precios_actualizados")
def precios_actualizados(
    carrito: list[dict],
    tipo_precio: str = Query("venta"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    nuevos_items = []

    for item in carrito:
        if item.get("id"):
            datos = db.execute(
                text("""
                    SELECT precio, precio_revendedor
                    FROM productos_sj
                    WHERE id = :id
                """),
                {"id": item["id"]}
            ).mappings().first()

            if not datos:
                continue

            precio = (
                datos["precio"]
                if tipo_precio == "venta"
                else datos["precio_revendedor"]
            )

            nuevos_items.append({
                "nombre": item["nombre"],
                "cantidad": item["cantidad"],
                "precio": float(precio)
            })
        else:
            nuevos_items.append(item)

    return nuevos_items


@router.get("/ultimas")
def ultimas_ventas(
    fecha_desde: str,
    fecha_hasta: str,
    exportar: bool = False,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    ventas = db.execute(text("""
        SELECT 
            v.id AS venta_id,
            p.nombre AS nombre_producto,
            p.num AS num,
            v.cantidad,
            CASE
                WHEN v.tipo_precio = 'revendedor' THEN p.precio_revendedor
                ELSE p.precio
            END AS precio_unitario,
            v.cantidad *
            CASE
                WHEN v.tipo_precio = 'revendedor' THEN p.precio_revendedor
                ELSE p.precio
            END AS total,
            v.fecha,
            v.tipo_pago,
            v.dni_cliente,
            v.tipo_precio
        FROM ventas_sj v
        LEFT JOIN productos_sj p ON v.producto_id = p.id
        WHERE DATE(v.fecha) BETWEEN :desde AND :hasta
        ORDER BY v.fecha DESC
    """), {
        "desde": fecha_desde,
        "hasta": fecha_hasta
    }).mappings().all()

    reparaciones = db.execute(text("""
        SELECT 
            id AS reparacion_id,
            nombre_servicio,
            cantidad,
            precio AS precio_unitario,
            (cantidad * precio) AS total,
            fecha,
            tipo_pago
        FROM reparaciones_sj
        WHERE DATE(fecha) BETWEEN :desde AND :hasta
        ORDER BY fecha DESC
    """), {
        "desde": fecha_desde,
        "hasta": fecha_hasta
    }).mappings().all()

    if exportar:
        wb = Workbook()
        ws = wb.active
        ws.title = "Ventas"

        ws.append([
            "ID Venta", "Producto", "Cantidad", "Núm",
            "Precio Unitario", "Total", "Fecha",
            "Tipo de Pago", "DNI Cliente", "Tipo Precio"
        ])

        for v in ventas:
            ws.append([
                v["venta_id"],
                v["nombre_producto"],
                v["cantidad"],
                v["num"] or "",
                v["precio_unitario"] or 0,
                v["total"] or 0,
                v["fecha"].strftime("%Y-%m-%d %H:%M:%S") if v["fecha"] else "",
                v["tipo_pago"],
                v["dni_cliente"] or "",
                v["tipo_precio"]
            ])

        output = BytesIO()
        wb.save(output)
        output.seek(0)

        return Response(
            content=output.read(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition":
                f"attachment; filename=ventas_{fecha_desde}_a_{fecha_hasta}.xlsx"
            }
        )

    return {
        "ventas": ventas,
        "reparaciones": reparaciones
    }

@router.delete("/anular/{venta_id}")
def anular_venta(
    venta_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    venta = db.execute(
        text("SELECT id FROM ventas_sj WHERE id = :id"),
        {"id": venta_id}
    ).first()

    if not venta:
        raise HTTPException(status_code=404, detail="Venta no encontrada")

    try:
        db.execute(
            text("DELETE FROM ventas_sj WHERE id = :id"),
            {"id": venta_id}
        )
        db.commit()
        return {"success": True, "message": "Venta eliminada correctamente"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/anular_reparacion/{reparacion_id}")
def anular_reparacion(
    reparacion_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    reparacion = db.execute(
        text("SELECT id FROM reparaciones_sj WHERE id = :id"),
        {"id": reparacion_id}
    ).first()

    if not reparacion:
        raise HTTPException(status_code=404, detail="Reparación no encontrada")

    try:
        db.execute(
            text("DELETE FROM reparaciones_sj WHERE id = :id"),
            {"id": reparacion_id}
        )
        db.commit()
        return {"success": True, "message": "Reparación eliminada correctamente"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
