# main.py
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi import UploadFile, File, HTTPException

import psycopg2
from psycopg2.extras import DictCursor
from datetime import datetime, timedelta
import pytz
import os

import cloudinary
import cloudinary.uploader

# =====================================================
# CONFIG
# =====================================================

import cloudinary
import cloudinary.uploader
import os

cloudinary.config(secure=True)

print("☁️ CLOUDINARY_URL:", os.getenv("CLOUDINARY_URL"))




from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
import os

app = FastAPI(title="Backend SJ")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://chiphone3.vercel.app",  # ✅ FRONT REAL
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", "change-me"),
    same_site="none",     # ✅ necesario para cross-site
    https_only=True,      # ✅ Railway es HTTPS
)



# =====================================================
# DB
# =====================================================

def get_db():
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError("Falta DATABASE_URL")
    conn = psycopg2.connect(dsn, cursor_factory=DictCursor, sslmode="require")
    try:
        yield conn
    finally:
        conn.close()

# =====================================================
# INIT TABLES
# =====================================================

def crear_tabla_usuarios():
    conn = psycopg2.connect(os.getenv("DATABASE_URL"), cursor_factory=DictCursor, sslmode="require")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user'
        )
    """)
    conn.commit()
    conn.close()

def crear_tabla_equipos():
    conn = psycopg2.connect(os.getenv("DATABASE_URL"), cursor_factory=DictCursor, sslmode="require")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS equipos_sj (
            id SERIAL PRIMARY KEY,
            tipo_reparacion TEXT NOT NULL,
            marca TEXT NOT NULL,
            modelo TEXT NOT NULL,
            tecnico TEXT NOT NULL,
            monto REAL NOT NULL,
            nombre_cliente TEXT NOT NULL,
            telefono TEXT NOT NULL,
            nro_orden TEXT NOT NULL,
            fecha TEXT NOT NULL,
            hora TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

crear_tabla_usuarios()
crear_tabla_equipos()

# =====================================================
# AUTH HELPERS
# =====================================================

def require_login(request: Request):
    if "username" not in request.session:
        raise HTTPException(status_code=401, detail="No autenticado")
    return request.session["username"]

# =====================================================
# AUTH
# =====================================================

@app.post("/login")
def login(data: dict, request: Request, db=Depends(get_db)):
    username = data.get("username")
    password = data.get("password")

    cur = db.cursor()
    cur.execute("SELECT * FROM usuarios WHERE username=%s", (username,))
    user = cur.fetchone()

    if not user or user["password"] != password:
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    request.session["username"] = user["username"]
    request.session["role"] = user["role"]

    return {"ok": True, "username": user["username"], "role": user["role"]}

@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}

@app.get("/me")
def me(username=Depends(require_login), request: Request = None):
    return {
        "username": request.session.get("username"),
        "role": request.session.get("role"),
    }

# =====================================================
# CARRITO
# =====================================================

@app.post("/carrito/agregar")
def agregar_carrito(data: dict, request: Request, db=Depends(get_db)):
    if "carrito" not in request.session:
        request.session["carrito"] = []

    producto_id = data["producto_id"]
    cantidad = int(data.get("cantidad", 1))
    tipo_precio = data.get("tipo_precio", "venta")

    cur = db.cursor(cursor_factory=DictCursor)
    cur.execute("""
        SELECT id, nombre, stock, precio, precio_revendedor
        FROM productos_sj
        WHERE id = %s
    """, (producto_id,))
    producto = cur.fetchone()

    if not producto:
        raise HTTPException(404, "Producto no encontrado")

    if producto["stock"] < cantidad:
        raise HTTPException(400, "Stock insuficiente")

    precio_usado = (
        float(producto["precio_revendedor"])
        if tipo_precio == "revendedor" and producto["precio_revendedor"]
        else float(producto["precio"])
    )

    request.session["carrito"].append({
        "id": producto["id"],
        "nombre": producto["nombre"],
        "precio": precio_usado,
        "cantidad": cantidad,
        "tipo_precio": tipo_precio
    })

    return {"ok": True}



@app.post("/carrito/agregar-manual")
def agregar_manual(data: dict, request: Request):
    if "carrito" not in request.session:
        request.session["carrito"] = []

    request.session["carrito"].append({
        "id": None,
        "nombre": data["nombre"],
        "precio": float(data["precio"]),
        "cantidad": int(data["cantidad"]),
        "tipo_precio": "manual"
    })

    return {"ok": True}


@app.post("/carrito/vaciar")
def vaciar_carrito(request: Request):
    request.session.pop("carrito", None)
    return {"ok": True}


@app.get("/carrito")
def ver_carrito(request: Request):
    carrito = request.session.get("carrito", [])
    total = sum(i["precio"] * i["cantidad"] for i in carrito)
    return {"items": carrito, "total": total}

@app.post("/ventas/registrar")
def registrar_venta(data: dict, request: Request, db=Depends(get_db)):
    carrito = request.session.get("carrito", [])

    if not carrito:
        raise HTTPException(400, "Carrito vacío")

    tipo_pago = data["tipo_pago"]
    dni_cliente = data["dni_cliente"]

    tz = pytz.timezone("America/Argentina/Buenos_Aires")
    fecha_actual = datetime.now(tz)

    cur = db.cursor(cursor_factory=DictCursor)

    for item in carrito:
        producto_id = item["id"]
        nombre = item["nombre"]
        cantidad = int(item["cantidad"])

        if producto_id:
            # producto normal
            cur.execute("""
                SELECT precio, precio_revendedor, stock
                FROM productos_sj
                WHERE id = %s
            """, (producto_id,))
            producto = cur.fetchone()

            if not producto or producto["stock"] < cantidad:
                raise HTTPException(400, f"Sin stock para {nombre}")

            cur.execute("""
                INSERT INTO ventas_sj
                (producto_id, cantidad, fecha, nombre_manual,
                 tipo_pago, dni_cliente, tipo_precio, precio)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                producto_id,
                cantidad,
                fecha_actual,
                nombre,
                tipo_pago,
                dni_cliente,
                item["tipo_precio"],
                item["precio"]
            ))

            cur.execute("""
                UPDATE productos_sj
                SET stock = stock - %s
                WHERE id = %s
            """, (cantidad, producto_id))

        else:
            # servicio técnico
            cur.execute("""
                INSERT INTO reparaciones_sj
                (nombre_servicio, precio, cantidad,
                 tipo_pago, dni_cliente, fecha)
                VALUES (%s,%s,%s,%s,%s,%s)
            """, (
                nombre,
                item["precio"],
                cantidad,
                tipo_pago,
                dni_cliente,
                fecha_actual
            ))

    db.commit()
    request.session.pop("carrito", None)

    return {"ok": True}


# =====================================================
# PRECIOS ACTUALIZADOS
# =====================================================

@app.get("/api/carrito/precios_actualizados")
def precios_actualizados(tipo_precio: str = "venta", request: Request = None, db=Depends(get_db)):
    carrito = request.session.get("carrito", [])
    cur = db.cursor()

    nuevos = []

    for item in carrito:
        if item["id"]:
            cur.execute(
                "SELECT precio, precio_revendedor FROM productos_sj WHERE id=%s",
                (item["id"],),
            )
            p = cur.fetchone()
            precio = float(p["precio"] if tipo_precio == "venta" else p["precio_revendedor"])
            nuevos.append({
                "nombre": item["nombre"],
                "cantidad": item["cantidad"],
                "precio": precio,
            })
        else:
            nuevos.append(item)

    return nuevos

# =====================================================
# PRODUCTOS MÁS VENDIDOS
# =====================================================

@app.get("/productos_mas_vendidos")
def productos_mas_vendidos(db=Depends(get_db)):
    cur = db.cursor()

    cur.execute("""
        SELECT nombre, precio, cantidad_vendida
        FROM productos_sj
        ORDER BY cantidad_vendida DESC
        LIMIT 5
    """)
    productos = cur.fetchall()

    cur.execute("SELECT SUM(cantidad_vendida) FROM productos_sj")
    total = cur.fetchone()[0] or 0

    return {
        "total_ventas": total,
        "productos": [
            {
                "nombre": p["nombre"],
                "precio": float(p["precio"]),
                "cantidad": p["cantidad_vendida"],
                "porcentaje": round((p["cantidad_vendida"] / total) * 100, 2) if total else 0,
            }
            for p in productos
        ],
    }

# =====================================================
# PRODUCTOS MÁS VENDIDOS (DETALLADO)
# =====================================================

@app.get("/productos_mas_vendidos/detalle")
def productos_mas_vendidos_detalle(db=Depends(get_db)):
    cur = db.cursor()

    cur.execute("""
        SELECT nombre, precio, cantidad_vendida
        FROM productos_sj
        ORDER BY cantidad_vendida DESC
        LIMIT 5
    """)
    productos = cur.fetchall()

    cur.execute("SELECT SUM(cantidad_vendida) FROM productos_sj")
    total_ventas = cur.fetchone()[0] or 0

    productos_con_porcentaje = []
    for p in productos:
        porcentaje = (p["cantidad_vendida"] / total_ventas * 100) if total_ventas > 0 else 0
        productos_con_porcentaje.append({
            "nombre": p["nombre"],
            "precio": float(p["precio"]),
            "cantidad_vendida": p["cantidad_vendida"],
            "porcentaje": round(porcentaje, 2),
        })

    return {
        "total_ventas": total_ventas,
        "productos": productos_con_porcentaje,
    }

# =====================================================
# PRODUCTOS POR AGOTARSE
# =====================================================

@app.get("/productos_por_agotarse")
def productos_por_agotarse(db=Depends(get_db)):
    cur = db.cursor()

    cur.execute("""
        SELECT id, nombre, codigo_barras, stock, precio, precio_costo
        FROM productos_sj
        WHERE stock <= 2
        ORDER BY stock ASC
    """)
    productos = cur.fetchall()

    return [
        {
            "id": p["id"],
            "nombre": p["nombre"],
            "codigo_barras": p["codigo_barras"],
            "stock": p["stock"],
            "precio": float(p["precio"]),
            "precio_costo": float(p["precio_costo"]) if p["precio_costo"] else 0,
        }
        for p in productos
    ]

# =====================================================
# ÚLTIMAS VENTAS Y REPARACIONES
# =====================================================
@app.get("/ventas/buscar")
def buscar_productos(busqueda: str, db=Depends(get_db)):
    cur = db.cursor(cursor_factory=DictCursor)
    cur.execute("""
        SELECT id, nombre, codigo_barras, num, stock, precio, precio_revendedor
        FROM productos_sj
        WHERE codigo_barras = %s
           OR nombre ILIKE %s
           OR num ILIKE %s
        ORDER BY nombre
    """, (busqueda, f"%{busqueda}%", f"%{busqueda}%"))

    return cur.fetchall()



from openpyxl import Workbook
from io import BytesIO
from fastapi.responses import StreamingResponse

@app.get("/ultimas_ventas")
def ultimas_ventas(
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    exportar: bool = False,
    db=Depends(get_db)
):
    cur = db.cursor()

    argentina_tz = pytz.timezone("America/Argentina/Buenos_Aires")
    hoy = datetime.now(argentina_tz).strftime("%Y-%m-%d")

    fecha_desde = fecha_desde or hoy
    fecha_hasta = fecha_hasta or hoy

    # =============================
    # VENTAS
    # =============================
    cur.execute("""
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
        WHERE DATE(v.fecha) BETWEEN %s AND %s
        ORDER BY v.fecha DESC
    """, (fecha_desde, fecha_hasta))
    ventas = cur.fetchall()

    # =============================
    # REPARACIONES
    # =============================
    cur.execute("""
        SELECT 
            id AS reparacion_id,
            nombre_servicio,
            cantidad,
            precio AS precio_unitario,
            (cantidad * precio) AS total,
            fecha,
            tipo_pago
        FROM reparaciones_sj
        WHERE DATE(fecha) BETWEEN %s AND %s
        ORDER BY fecha DESC
    """, (fecha_desde, fecha_hasta))
    reparaciones = cur.fetchall()

    # =============================
    # TOTALES POR PAGO
    # =============================
    total_ventas_por_pago = {}
    for v in ventas:
        total_ventas_por_pago[v["tipo_pago"]] = (
            total_ventas_por_pago.get(v["tipo_pago"], 0) + (v["total"] or 0)
        )

    total_reparaciones_por_pago = {}
    for r in reparaciones:
        total_reparaciones_por_pago[r["tipo_pago"]] = (
            total_reparaciones_por_pago.get(r["tipo_pago"], 0) + (r["total"] or 0)
        )

    # =============================
    # EXPORTAR EXCEL
    # =============================
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
                v.get("num") or "",
                v["precio_unitario"] or 0,
                v["total"] or 0,
                v["fecha"].strftime("%Y-%m-%d %H:%M:%S") if v["fecha"] else "",
                v["tipo_pago"],
                v["dni_cliente"] or "",
                v["tipo_precio"].capitalize() if v["tipo_precio"] else "",
            ])

        output = BytesIO()
        wb.save(output)
        output.seek(0)

        filename = f"ventas_{fecha_desde}_a_{fecha_hasta}.xlsx"
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    return {
        "ventas": ventas,
        "reparaciones": reparaciones,
        "totales_ventas_por_pago": total_ventas_por_pago,
        "totales_reparaciones_por_pago": total_reparaciones_por_pago,
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
    }

# =====================================================
# ANULAR VENTA
# =====================================================

@app.delete("/anular_venta/{venta_id}")
def anular_venta(venta_id: int, db=Depends(get_db)):
    cur = db.cursor()

    cur.execute("SELECT id FROM ventas_sj WHERE id=%s", (venta_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Venta no encontrada")

    cur.execute("DELETE FROM ventas_sj WHERE id=%s", (venta_id,))
    db.commit()

    return {"success": True}

# =====================================================
# ANULAR REPARACIÓN
# =====================================================

@app.delete("/anular_reparacion/{reparacion_id}")
def anular_reparacion(reparacion_id: int, db=Depends(get_db)):
    cur = db.cursor()

    cur.execute("SELECT id FROM reparaciones_sj WHERE id=%s", (reparacion_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Reparación no encontrada")

    cur.execute("DELETE FROM reparaciones_sj WHERE id=%s", (reparacion_id,))
    db.commit()

    return {"success": True}

# =====================================================
# EGRESOS
# =====================================================

@app.get("/egresos")
def listar_egresos(db=Depends(get_db)):
    cur = db.cursor()
    cur.execute("""
        SELECT id, fecha, monto, descripcion, tipo_pago
        FROM egresos_sj
        ORDER BY fecha DESC
    """)
    egresos = cur.fetchall()

    return [
        {
            "id": e["id"],
            "fecha": e["fecha"],
            "monto": float(e["monto"]),
            "descripcion": e["descripcion"],
            "tipo_pago": e["tipo_pago"],
        }
        for e in egresos
    ]

@app.post("/egresos")
def agregar_egreso(data: dict, db=Depends(get_db)):
    cur = db.cursor()
    cur.execute("""
        INSERT INTO egresos_sj (fecha, monto, descripcion, tipo_pago)
        VALUES (%s, %s, %s, %s)
    """, (
        data["fecha"],
        float(data["monto"]),
        data["descripcion"],
        data["tipo_pago"],
    ))
    db.commit()
    return {"ok": True}

@app.delete("/egresos/{egreso_id}")
def eliminar_egreso(egreso_id: int, db=Depends(get_db)):
    cur = db.cursor()
    cur.execute("DELETE FROM egresos_sj WHERE id=%s", (egreso_id,))
    db.commit()
    return {"ok": True}

# =====================================================
# DASHBOARD
# =====================================================

@app.get("/dashboard")
def dashboard(
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    db=Depends(get_db)
):
    cur = db.cursor()

    hoy = datetime.now().strftime("%Y-%m-%d")
    fecha_desde = fecha_desde or hoy
    fecha_hasta = fecha_hasta or hoy

    # -----------------------------------------
    # Total ventas productos
    # -----------------------------------------
    cur.execute("""
        SELECT SUM(
            v.cantidad *
            CASE
                WHEN v.tipo_precio = 'revendedor' THEN p.precio_revendedor
                ELSE p.precio
            END
        ) AS total
        FROM ventas_sj v
        LEFT JOIN productos_sj p ON v.producto_id = p.id
        WHERE DATE(v.fecha) BETWEEN %s AND %s
    """, (fecha_desde, fecha_hasta))
    total_ventas_productos = cur.fetchone()["total"] or 0

    # -----------------------------------------
    # Total reparaciones
    # -----------------------------------------
    cur.execute("""
        SELECT SUM(precio) AS total
        FROM reparaciones_sj
        WHERE DATE(fecha) BETWEEN %s AND %s
    """, (fecha_desde, fecha_hasta))
    total_ventas_reparaciones = cur.fetchone()["total"] or 0

    total_ventas = total_ventas_productos + total_ventas_reparaciones

    # -----------------------------------------
    # Total egresos
    # -----------------------------------------
    cur.execute("""
        SELECT SUM(monto) AS total
        FROM egresos_sj
        WHERE DATE(fecha) BETWEEN %s AND %s
    """, (fecha_desde, fecha_hasta))
    total_egresos = cur.fetchone()["total"] or 0

    # -----------------------------------------
    # Costo productos vendidos
    # -----------------------------------------
    cur.execute("""
        SELECT SUM(v.cantidad * p.precio_costo) AS total
        FROM ventas_sj v
        JOIN productos_sj p ON v.producto_id = p.id
        WHERE DATE(v.fecha) BETWEEN %s AND %s
    """, (fecha_desde, fecha_hasta))
    total_costo = cur.fetchone()["total"] or 0

    ganancia = total_ventas - total_egresos - total_costo

    # -----------------------------------------
    # Distribución ventas
    # -----------------------------------------
    cur.execute("""
        SELECT 'Productos' AS tipo, SUM(
            v.cantidad *
            CASE
                WHEN v.tipo_precio = 'revendedor' THEN p.precio_revendedor
                ELSE p.precio
            END
        ) AS total
        FROM ventas_sj v
        LEFT JOIN productos_sj p ON v.producto_id = p.id
        WHERE DATE(v.fecha) BETWEEN %s AND %s

        UNION ALL

        SELECT 'Reparaciones' AS tipo, SUM(precio)
        FROM reparaciones_sj
        WHERE DATE(fecha) BETWEEN %s AND %s
    """, (fecha_desde, fecha_hasta, fecha_desde, fecha_hasta))

    distribucion = cur.fetchall()

    return {
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "total_ventas": total_ventas,
        "total_ventas_productos": total_ventas_productos,
        "total_ventas_reparaciones": total_ventas_reparaciones,
        "total_egresos": total_egresos,
        "total_costo": total_costo,
        "ganancia": ganancia,
        "distribucion_ventas": [
            {"tipo": d["tipo"], "total": d["total"] or 0}
            for d in distribucion
        ],
    }

# =====================================================
# RESUMEN SEMANAL
# =====================================================

@app.get("/resumen_semanal")
def resumen_semanal(db=Depends(get_db)):
    hoy = datetime.now()
    inicio_semana = hoy - timedelta(days=hoy.weekday())
    inicio_semana_str = inicio_semana.strftime("%Y-%m-%d")

    cur = db.cursor()
    cur.execute("""
        SELECT tipo_pago, SUM(total) AS total
        FROM ventas_sj
        WHERE fecha >= %s
        GROUP BY tipo_pago
    """, (inicio_semana_str,))

    resumen = cur.fetchall()

    return [
        {
            "tipo_pago": r["tipo_pago"],
            "total": r["total"] or 0,
        }
        for r in resumen
    ]

# =====================================================
# CAJA
# =====================================================

@app.get("/caja")
def caja(
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    db=Depends(get_db)
):
    argentina_tz = pytz.timezone("America/Argentina/Buenos_Aires")
    hoy = datetime.now(argentina_tz).date()

    fecha_desde = fecha_desde or hoy.strftime("%Y-%m-%d")
    fecha_hasta = fecha_hasta or hoy.strftime("%Y-%m-%d")

    cur = db.cursor()

    # ------------------------
    # Ventas
    # ------------------------
    cur.execute("""
        SELECT 
            v.tipo_pago,
            (v.cantidad *
            CASE
                WHEN v.tipo_precio = 'revendedor' THEN p.precio_revendedor
                ELSE p.precio
            END) AS total
        FROM ventas_sj v
        JOIN productos_sj p ON v.producto_id = p.id
        WHERE DATE(v.fecha) BETWEEN %s AND %s
    """, (fecha_desde, fecha_hasta))
    ventas = cur.fetchall()

    # ------------------------
    # Reparaciones
    # ------------------------
    cur.execute("""
        SELECT tipo_pago, (cantidad * precio) AS total
        FROM reparaciones_sj
        WHERE DATE(fecha) BETWEEN %s AND %s
    """, (fecha_desde, fecha_hasta))
    reparaciones = cur.fetchall()

    # ------------------------
    # Egresos
    # ------------------------
    cur.execute("""
        SELECT tipo_pago, monto
        FROM egresos_sj
        WHERE DATE(fecha) BETWEEN %s AND %s
    """, (fecha_desde, fecha_hasta))
    egresos = cur.fetchall()

    total_por_pago = {}

    for v in ventas:
        total_por_pago[v["tipo_pago"]] = total_por_pago.get(v["tipo_pago"], 0) + v["total"]

    for r in reparaciones:
        total_por_pago[r["tipo_pago"]] = total_por_pago.get(r["tipo_pago"], 0) + r["total"]

    egresos_por_pago = {}
    for e in egresos:
        egresos_por_pago[e["tipo_pago"]] = egresos_por_pago.get(e["tipo_pago"], 0) + e["monto"]

    neto_por_pago = {}
    for tipo_pago, total in total_por_pago.items():
        neto_por_pago[tipo_pago] = total - egresos_por_pago.get(tipo_pago, 0)

    return {
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "neto_por_pago": neto_por_pago,
    }

# =====================================================
# REPARACIONES
# =====================================================

import unicodedata

def normalizar(texto: str):
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower().strip()

@app.get("/reparaciones")
def listar_reparaciones(
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    db=Depends(get_db)
):
    fecha_desde = fecha_desde or (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    fecha_hasta = fecha_hasta or datetime.now().strftime("%Y-%m-%d")

    cur = db.cursor()

    # Últimos equipos
    cur.execute("""
        SELECT * FROM equipos_sj
        WHERE fecha BETWEEN %s AND %s
        ORDER BY nro_orden DESC
    """, (fecha_desde, fecha_hasta))
    equipos = cur.fetchall()

    # Por técnico
    cur.execute("""
        SELECT tecnico, COUNT(*) AS cantidad
        FROM equipos_sj
        WHERE fecha BETWEEN %s AND %s
        GROUP BY tecnico
    """, (fecha_desde, fecha_hasta))
    tecnicos = {r["tecnico"]: r["cantidad"] for r in cur.fetchall()}

    # Por estado
    cur.execute("""
        SELECT estado, COUNT(*) AS cantidad
        FROM equipos_sj
        WHERE fecha BETWEEN %s AND %s
        GROUP BY estado
    """, (fecha_desde, fecha_hasta))

    estados_raw = cur.fetchall()

    estados = {
        "por_reparar": 0,
        "en_reparacion": 0,
        "listo": 0,
        "retirado": 0,
        "no_salio": 0,
    }

    for r in estados_raw:
        e = normalizar(r["estado"])
        if e in ["por reparar", "por_reparar"]:
            estados["por_reparar"] += r["cantidad"]
        elif e in ["en reparacion", "en reparación", "en_reparacion"]:
            estados["en_reparacion"] += r["cantidad"]
        elif e == "listo":
            estados["listo"] += r["cantidad"]
        elif e == "retirado":
            estados["retirado"] += r["cantidad"]
        elif e in ["no salio", "no_salio"]:
            estados["no_salio"] += r["cantidad"]
        else:
            estados[e] = r["cantidad"]

    estados["total"] = sum(v for k, v in estados.items() if k != "total")

    return {
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "equipos": equipos,
        "equipos_por_tecnico": tecnicos,
        "estados": estados,
    }

# =====================================================
# ELIMINAR REPARACIÓN (EQUIPO)
# =====================================================

@app.delete("/reparaciones/{id}")
def eliminar_reparacion(id: int, db=Depends(get_db)):
    cur = db.cursor()
    cur.execute("DELETE FROM equipos_sj WHERE id = %s", (id,))
    db.commit()
    return {"success": True}

# =====================================================
# ACTUALIZAR ESTADO DE REPARACIÓN
# =====================================================

@app.post("/reparaciones/actualizar_estado")
def actualizar_estado(data: dict, db=Depends(get_db)):
    nro_orden = data["nro_orden"]
    estado = data["estado"]

    cur = db.cursor()
    cur.execute("""
        UPDATE equipos_sj
        SET estado = %s
        WHERE nro_orden = %s
    """, (estado, nro_orden))
    db.commit()

    return {"success": True}

# =====================================================
# MERCADERÍA FALLADA
# =====================================================

@app.get("/mercaderia_fallada")
def listar_mercaderia_fallada(db=Depends(get_db)):
    cur = db.cursor()
    cur.execute("""
        SELECT mf.id, p.nombre, mf.cantidad, mf.fecha, mf.descripcion
        FROM mercaderia_fallada mf
        JOIN productos_sj p ON mf.producto_id = p.id
        ORDER BY mf.fecha DESC
    """)
    return cur.fetchall()


@app.post("/mercaderia_fallada")
def registrar_mercaderia_fallada(data: dict, db=Depends(get_db)):
    producto_id = data["producto_id"]
    cantidad = int(data["cantidad"])
    descripcion = data["descripcion"]
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur = db.cursor()
    cur.execute("SELECT stock FROM productos_sj WHERE id=%s", (producto_id,))
    prod = cur.fetchone()

    if not prod or prod["stock"] < cantidad:
        raise HTTPException(status_code=400, detail="Stock insuficiente")

    cur.execute("""
        INSERT INTO mercaderia_fallada (producto_id, cantidad, fecha, descripcion)
        VALUES (%s, %s, %s, %s)
    """, (producto_id, cantidad, fecha, descripcion))

    cur.execute("""
        UPDATE productos_sj
        SET stock = stock - %s
        WHERE id = %s
    """, (cantidad, producto_id))

    db.commit()
    return {"success": True}

# =====================================================
# CATEGORÍAS
# =====================================================

def crear_tabla_categorias():
    conn = psycopg2.connect(os.getenv("DATABASE_URL"), cursor_factory=DictCursor, sslmode="require")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS categorias_sj (
            id SERIAL PRIMARY KEY,
            nombre TEXT UNIQUE NOT NULL
        )
    """)
    conn.commit()
    conn.close()

crear_tabla_categorias()


@app.get("/categorias")
def listar_categorias(db=Depends(get_db)):
    cur = db.cursor()
    cur.execute("SELECT nombre FROM categorias_sj ORDER BY nombre")
    return [r["nombre"] for r in cur.fetchall()]


@app.post("/categorias")
def agregar_categoria(data: dict, db=Depends(get_db)):
    cur = db.cursor()
    cur.execute(
        "INSERT INTO categorias_sj (nombre) VALUES (%s) ON CONFLICT DO NOTHING",
        (data["nombre"].strip(),)
    )
    db.commit()
    return {"ok": True}


@app.delete("/categorias/{nombre}")
def eliminar_categoria(nombre: str, db=Depends(get_db)):
    cur = db.cursor()
    cur.execute("DELETE FROM categorias_sj WHERE nombre=%s", (nombre,))
    db.commit()
    return {"ok": True}

# =====================================================
# PRODUCTOS / STOCK
# =====================================================

@app.get("/productos")
def listar_productos(
    busqueda: str | None = None,
    page: int = 1,
    limit: int = 20,
    db=Depends(get_db)
):
    offset = (page - 1) * limit
    cur = db.cursor(cursor_factory=DictCursor)

    if busqueda:
        cur.execute("""
            SELECT *
            FROM productos_sj
            WHERE nombre ILIKE %s
               OR codigo_barras ILIKE %s
               OR num ILIKE %s
            ORDER BY id DESC
            LIMIT %s OFFSET %s
        """, (
            f"%{busqueda}%",
            f"%{busqueda}%",
            f"%{busqueda}%",
            limit,
            offset
        ))
    else:
        cur.execute("""
            SELECT *
            FROM productos_sj
            ORDER BY id DESC
            LIMIT %s OFFSET %s
        """, (limit, offset))

    rows = cur.fetchall()

    # total (para paginación)
    cur.execute("SELECT COUNT(*) FROM productos_sj")
    total = cur.fetchone()[0]

    return {
        "items": [dict(r) for r in rows],
        "total": total
    }


# ==========================
# SUBIDA DE IMÁGENES (Cloudinary)
# ==========================
from fastapi import UploadFile, File, HTTPException
import cloudinary
import cloudinary.uploader
import traceback

@app.post("/upload-imagen")
async def upload_imagen(file: UploadFile = File(...)):
    try:
        print("📷 Archivo recibido:", file.filename, file.content_type)

        result = cloudinary.uploader.upload(
            file.file,
            folder="productos",
            resource_type="image"
        )

        return {
            "ok": True,
            "url": result["secure_url"]
        }

    except Exception as e:
        print("❌ ERROR CLOUDINARY", e)
        raise HTTPException(status_code=500, detail=str(e))



@app.post("/productos")
def agregar_producto(data: dict, db=Depends(get_db)):
    try:
        cur = db.cursor(cursor_factory=DictCursor)

        cur.execute("""
            INSERT INTO productos_sj (
                nombre,
                codigo_barras,
                stock,
                precio,
                precio_costo,
                foto_url,
                categoria,
                num,
                color,
                bateria,
                precio_revendedor,
                condicion
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            data["nombre"].upper(),
            data["codigo_barras"],
            int(data["stock"]),
            float(data["precio"]),
            float(data["precio_costo"]),
            data.get("foto_url"),
            data.get("categoria"),
            data.get("num"),
            data.get("color"),
            data.get("bateria"),
            data.get("precio_revendedor"),
            data.get("condicion"),
        ))

        db.commit()
        return {"ok": True}

    except KeyError as e:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Falta el campo obligatorio: {e}"
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )



@app.put("/productos/{id}")
def editar_producto(id: int, data: dict, db=Depends(get_db)):
    cur = db.cursor()
    cur.execute("""
        UPDATE productos_sj
        SET nombre=%s, codigo_barras=%s, stock=%s, precio=%s, precio_costo=%s,
            categoria=%s, num=%s, color=%s, bateria=%s, precio_revendedor=%s, condicion=%s
        WHERE id=%s
    """, (
        data["nombre"].upper(),
        data["codigo_barras"],
        int(data["stock"]),
        float(data["precio"]),
        float(data["precio_costo"]),
        data.get("categoria"),
        data.get("num"),
        data.get("color"),
        data.get("bateria"),
        data.get("precio_revendedor"),
        data.get("condicion"),
        id,
    ))
    db.commit()
    return {"ok": True}


@app.delete("/productos/{id}")
def eliminar_producto(id: int, db=Depends(get_db)):
    cur = db.cursor()
    cur.execute("DELETE FROM productos_sj WHERE id=%s", (id,))
    db.commit()
    return {"ok": True}

# =====================================================
# TIENDA (PÚBLICA)
# =====================================================

# =====================================================
# TIENDA (PÚBLICA) - FIX DEFINITIVO
# =====================================================

@app.get("/tienda")
def tienda(categoria: str | None = None, db=Depends(get_db)):
    cur = db.cursor()

    if categoria:
        cur.execute("""
            SELECT
                id,
                nombre,
                stock,
                precio,
                foto_url,
                categoria,
                color,
                bateria,
                condicion,
                precio_revendedor
            FROM productos_sj
            WHERE categoria=%s
              AND foto_url IS NOT NULL
              AND stock > 0
            ORDER BY nombre
        """, (categoria,))
    else:
        cur.execute("""
            SELECT
                id,
                nombre,
                stock,
                precio,
                foto_url,
                categoria,
                color,
                bateria,
                condicion,
                precio_revendedor
            FROM productos_sj
            WHERE foto_url IS NOT NULL
              AND stock > 0
            ORDER BY nombre
        """)

    rows = cur.fetchall()

    productos = [
        {
            "id": r[0],
            "nombre": r[1],
            "stock": r[2],
            "precio": float(r[3]) if r[3] is not None else 0,
            "foto_url": r[4],
            "categoria": r[5],
            "color": r[6],
            "bateria": r[7],
            "condicion": r[8],
            "precio_revendedor": float(r[9]) if r[9] is not None else 0,
        }
        for r in rows
    ]

    cur.execute("""
        SELECT DISTINCT categoria
        FROM productos_sj
        WHERE categoria IS NOT NULL
        ORDER BY categoria
    """)
    categorias = [r[0] for r in cur.fetchall()]

    return {
        "productos": productos,
        "categorias": categorias,
        "categoria_seleccionada": categoria,
    }


# =====================================================
# EXPORTAR STOCK
# =====================================================

from openpyxl.styles import Font, Alignment, PatternFill
from fastapi.responses import StreamingResponse

@app.get("/exportar_stock")
def exportar_stock(db=Depends(get_db)):
    cur = db.cursor()
    cur.execute("""
        SELECT id, nombre, codigo_barras, num, color, bateria,
               condicion, stock, precio, precio_costo, precio_revendedor
        FROM productos_sj
        ORDER BY nombre
    """)
    productos = cur.fetchall()

    wb = Workbook()
    ws = wb.active
    ws.title = "Stock"

    headers = [
        "ID", "Nombre", "Código", "Núm", "Color", "Batería",
        "Condición", "Stock", "Precio Venta", "Precio Costo", "Precio Rev."
    ]
    ws.append(headers)

    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="4B5563", end_color="4B5563", fill_type="solid")
        cell.alignment = Alignment(horizontal="center")

    for p in productos:
        ws.append(list(p))

    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width = max(
            len(str(c.value)) if c.value else 0 for c in col
        ) + 2

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=stock.xlsx"}
    )

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
