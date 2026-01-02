from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
from psycopg2.extras import DictCursor
from datetime import datetime, timedelta
import pytz
import os
import cloudinary
import cloudinary.uploader
from io import BytesIO
from openpyxl import Workbook
import unicodedata

# =====================================================
# APP
# =====================================================
app = FastAPI(title="Sistema Comercial SJ")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =====================================================
# CLOUDINARY
# =====================================================
cloudinary.config(
    cloud_name="dcbdjnpzo",
    api_key="381622333637456",
    api_secret="P1Pzvu85aCR02HuRSCnz76yzrgg"
)

# =====================================================
# DB
# =====================================================
def get_db():
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL no definido")
    return psycopg2.connect(dsn, cursor_factory=DictCursor, sslmode="require")

# =====================================================
# HELPERS
# =====================================================
def normalizar(texto):
    return unicodedata.normalize("NFKD", texto).encode("ASCII", "ignore").decode().lower().strip()

arg_tz = pytz.timezone("America/Argentina/Buenos_Aires")

# =====================================================
# AUTH
# =====================================================
@app.post("/login")
def login(username: str = Form(...), password: str = Form(...)):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM usuarios WHERE username=%s", (username,))
    user = cur.fetchone()
    conn.close()

    if not user or user["password"] != password:
        raise HTTPException(401, "Credenciales inválidas")

    return {"username": user["username"], "role": user["role"]}

# =====================================================
# PRODUCTOS / STOCK
# =====================================================
@app.get("/productos")
def productos(busqueda: str | None = None):
    conn = get_db()
    cur = conn.cursor()

    if busqueda:
        cur.execute("""
            SELECT
                id,
                nombre,
                codigo_barras,
                stock,
                precio,
                precio_costo,
                categoria,
                num,
                color,
                bateria,
                precio_revendedor,
                condicion
            FROM productos_sj
            WHERE nombre ILIKE %s
               OR codigo_barras ILIKE %s
               OR num ILIKE %s
            ORDER BY nombre
        """, (f"%{busqueda}%", f"%{busqueda}%", f"%{busqueda}%"))
    else:
        cur.execute("""
            SELECT
                id,
                nombre,
                codigo_barras,
                stock,
                precio,
                precio_costo,
                categoria,
                num,
                color,
                bateria,
                precio_revendedor,
                condicion
            FROM productos_sj
            ORDER BY nombre
        """)

    columnas = [desc[0] for desc in cur.description]
    data = [dict(zip(columnas, fila)) for fila in cur.fetchall()]

    conn.close()
    return data


@app.post("/productos")
def agregar_producto(
    nombre: str = Form(...),
    codigo_barras: str = Form(...),
    stock: int = Form(...),
    precio: float = Form(...),
    precio_costo: float = Form(...),
    categoria: str = Form(None),
    num: str = Form(None),
    color: str = Form(None),
    bateria: str = Form(None),
    precio_revendedor: float = Form(None),
    condicion: str = Form(None),
    foto: UploadFile = File(None)
):
    conn = get_db()
    cur = conn.cursor()

    foto_url = None
    if foto:
        foto_url = cloudinary.uploader.upload(foto.file)["secure_url"]

    cur.execute("""
        INSERT INTO productos_sj
        (nombre, codigo_barras, stock, precio, precio_costo, categoria,
         foto_url, num, color, bateria, precio_revendedor, condicion)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        nombre.upper(), codigo_barras, stock, precio, precio_costo, categoria,
        foto_url, num, color, bateria, precio_revendedor, condicion
    ))
    conn.commit()
    conn.close()
    return {"success": True}

@app.delete("/productos/{id}")
def eliminar_producto(id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM productos_sj WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return {"success": True}

# =====================================================
# VENTAS
# =====================================================
@app.post("/ventas")
def registrar_venta(data: dict):
    conn = get_db()
    cur = conn.cursor()
    fecha = datetime.now(arg_tz)

    for item in data["items"]:
        cur.execute("""
            INSERT INTO ventas_sj
            (producto_id, cantidad, fecha, nombre_manual,
             tipo_pago, dni_cliente, tipo_precio)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (
            item.get("producto_id"),
            item["cantidad"],
            fecha,
            item["nombre"],
            data["tipo_pago"],
            data.get("dni_cliente"),
            item["tipo_precio"]
        ))

        if item.get("producto_id"):
            cur.execute("""
                UPDATE productos_sj
                SET stock = stock - %s
                WHERE id=%s
            """, (item["cantidad"], item["producto_id"]))

    conn.commit()
    conn.close()
    return {"success": True}

@app.get("/ventas")
def listar_ventas(fecha_desde: str, fecha_hasta: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT v.*, p.nombre
        FROM ventas_sj v
        LEFT JOIN productos_sj p ON v.producto_id=p.id
        WHERE DATE(v.fecha) BETWEEN %s AND %s
        ORDER BY v.fecha DESC
    """, (fecha_desde, fecha_hasta))
    data = cur.fetchall()
    conn.close()
    return data

@app.delete("/ventas/{id}")
def anular_venta(id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM ventas_sj WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return {"success": True}

# =====================================================
# REPARACIONES
# =====================================================
@app.post("/reparaciones")
def registrar_reparacion(data: dict):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO equipos_sj
        (tipo_reparacion, marca, modelo, tecnico, monto,
         nombre_cliente, telefono, nro_orden, fecha, hora, estado)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'Por Reparar')
    """, (
        data["tipo_reparacion"],
        data["marca"],
        data["modelo"],
        data["tecnico"],
        data["monto"],
        data["nombre_cliente"],
        data["telefono"],
        data["nro_orden"],
        datetime.now().date(),
        datetime.now().strftime("%H:%M:%S")
    ))
    conn.commit()
    conn.close()
    return {"success": True}

@app.get("/reparaciones")
def listar_reparaciones(fecha_desde: str, fecha_hasta: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM equipos_sj
        WHERE fecha BETWEEN %s AND %s
        ORDER BY nro_orden DESC
    """, (fecha_desde, fecha_hasta))
    data = cur.fetchall()
    conn.close()
    return data

@app.patch("/reparaciones/estado")
def actualizar_estado(data: dict):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE equipos_sj SET estado=%s WHERE nro_orden=%s
    """, (data["estado"], data["nro_orden"]))
    conn.commit()
    conn.close()
    return {"success": True}

@app.delete("/reparaciones/{id}")
def eliminar_reparacion(id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM equipos_sj WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return {"success": True}

# =====================================================
# EGRESOS
# =====================================================
@app.post("/egresos")
def agregar_egreso(data: dict):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO egresos_sj (fecha, monto, descripcion, tipo_pago)
        VALUES (%s,%s,%s,%s)
    """, (
        data["fecha"],
        data["monto"],
        data["descripcion"],
        data["tipo_pago"]
    ))
    conn.commit()
    conn.close()
    return {"success": True}

@app.get("/egresos")
def listar_egresos():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM egresos_sj ORDER BY fecha DESC")
    data = cur.fetchall()
    conn.close()
    return data

@app.delete("/egresos/{id}")
def eliminar_egreso(id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM egresos_sj WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return {"success": True}

# =====================================================
# CAJA / DASHBOARD
# =====================================================
@app.get("/caja")
def caja(fecha_desde: str, fecha_hasta: str):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT tipo_pago,
        SUM(cantidad *
        CASE WHEN tipo_precio='revendedor'
        THEN p.precio_revendedor ELSE p.precio END) AS total
        FROM ventas_sj v
        JOIN productos_sj p ON v.producto_id=p.id
        WHERE DATE(v.fecha) BETWEEN %s AND %s
        GROUP BY tipo_pago
    """, (fecha_desde, fecha_hasta))

    ventas = cur.fetchall()

    cur.execute("""
        SELECT tipo_pago, SUM(monto) AS total
        FROM egresos_sj
        WHERE DATE(fecha) BETWEEN %s AND %s
        GROUP BY tipo_pago
    """, (fecha_desde, fecha_hasta))

    egresos = cur.fetchall()
    conn.close()

    return {
        "ventas": ventas,
        "egresos": egresos
    }

# =====================================================
# EXPORTAR STOCK
# =====================================================
@app.get("/exportar_stock")
def exportar_stock():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT nombre, codigo_barras, stock, precio, precio_costo, precio_revendedor
        FROM productos_sj
        ORDER BY nombre
    """)
    productos = cur.fetchall()
    conn.close()

    wb = Workbook()
    ws = wb.active
    ws.append(["Nombre", "Código", "Stock", "Precio", "Costo", "Revendedor"])
    for p in productos:
        ws.append(list(p))

    out = BytesIO()
    wb.save(out)
    out.seek(0)

    return StreamingResponse(
        out,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=stock.xlsx"}
    )

# =====================================================
# TIENDA
# =====================================================
@app.get("/tienda")
def tienda(categoria: str | None = None):
    conn = get_db()
    cur = conn.cursor()

    if categoria:
        cur.execute("""
            SELECT * FROM productos_sj
            WHERE categoria=%s AND stock>0 AND foto_url IS NOT NULL
        """, (categoria,))
    else:
        cur.execute("""
            SELECT * FROM productos_sj
            WHERE stock>0 AND foto_url IS NOT NULL
        """)

    productos = cur.fetchall()
    conn.close()
    return productos

# =====================================================
# RUN
# =====================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
