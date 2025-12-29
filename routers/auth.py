from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.deps import get_db
from pydantic import BaseModel
import jwt
import os
from datetime import datetime, timedelta

router = APIRouter(tags=["Auth"])

SECRET_KEY = os.getenv("SECRET_KEY", "change-me")
ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = 60 * 12  # 12 hs

class LoginIn(BaseModel):
    username: str
    password: str

@router.post("/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    result = db.execute(
        text("SELECT username, password, role FROM usuarios WHERE username = :u"),
        {"u": data.username}
    ).mappings().first()

    if not result or result["password"] != data.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos"
        )

    payload = {
        "sub": result["username"],
        "role": result["role"],
        "exp": datetime.utcnow() + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    }

    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    return {
        "access_token": token,
        "token_type": "bearer",
        "username": result["username"],
        "role": result["role"]
    }

@router.get("/inicio")
def inicio():
    return {"message": "Sistema activo"}

@router.post("/logout")
def logout():
    return {"message": "Logout OK (el frontend elimina el token)"}
