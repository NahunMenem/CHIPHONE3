from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import (
    auth,
    ventas,
    productos,
    stock,
    reparaciones,
    caja,
    dashboard,
    egresos,
    exportaciones,
    tienda,
)

app = FastAPI(
    title="Sistema Comercial SJ",
    description="Backend FastAPI migrado desde Flask",
    version="1.0.0"
)

# -------------------------------
# CORS (por si después conectás Next / Flutter)
# -------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------
# Routers
# -------------------------------
app.include_router(auth.router)
app.include_router(ventas.router)
app.include_router(productos.router)
app.include_router(stock.router)
app.include_router(reparaciones.router)
app.include_router(caja.router)
app.include_router(dashboard.router)
app.include_router(egresos.router)
app.include_router(exportaciones.router)
app.include_router(tienda.router)

# -------------------------------
# Health check
# -------------------------------
@app.get("/health")
def health():
    return {"status": "ok"}
