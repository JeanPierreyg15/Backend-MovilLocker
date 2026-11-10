from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config import config
from database import get_db
from models import Link, Tag, User
from schemas import Token, UserCreate, UserLogin, UserResponse, UserUpdate

router = APIRouter(prefix="/auth", tags=["Auth"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

ERROR_NO_AUTORIZADO = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="No se pudieron validar las credenciales",
    headers={"WWW-Authenticate": "Bearer"},
)


# ---------- Esquemas propios de recuperación ----------

class SolicitudRecuperacion(BaseModel):
    email: EmailStr


class RestablecerPassword(BaseModel):
    token: str
    password: str = Field(min_length=6)


# ---------- Utilidades de token ----------

def crear_token(datos: dict, minutos: int) -> str:
    expiracion = datetime.now(timezone.utc) + timedelta(minutes=minutos)
    a_codificar = {**datos, "exp": expiracion}
    return jwt.encode(a_codificar, config.SECRET_KEY, algorithm=config.ALGORITHM)


def decodificar_token(token: str) -> dict:
    # jwt.decode ya lanza JWTError si el token es inválido o está expirado
    return jwt.decode(token, config.SECRET_KEY, algorithms=[config.ALGORITHM])


def existe_usuario(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        carga = decodificar_token(token)
        email: str = carga.get("sub")
        if email is None or carga.get("proposito") == "reset":
            # Los tokens de recuperación no sirven como sesión
            raise ERROR_NO_AUTORIZADO
    except JWTError:
        raise ERROR_NO_AUTORIZADO from None

    usuario = db.query(User).filter(User.email == email).first()
    if usuario is None:
        raise ERROR_NO_AUTORIZADO
    return usuario


# ---------- Registro / Login ----------

@router.post("/register", response_model=UserResponse)
def register(user: UserCreate, db: Session = Depends(get_db)):
    if existe_usuario(db, user.email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email ya registrado")

    usuario_nuevo = User(
        nombre=user.nombre,
        email=user.email,
        hashed_password=pwd_context.hash(user.password),
    )
    db.add(usuario_nuevo)
    try:
        db.commit()
    except IntegrityError:
        # Carrera de dos registros concurrentes con el mismo email -> 400 en vez de 500
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email ya registrado") from None
    db.refresh(usuario_nuevo)
    return usuario_nuevo


@router.post("/login", response_model=Token)
def login(user: UserLogin, db: Session = Depends(get_db)):
    usuario = existe_usuario(db, user.email)
    if not usuario or not pwd_context.verify(user.password, usuario.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")
    token = crear_token({"sub": usuario.email}, minutos=config.ACCESS_TOKEN_EXPIRE_MINUTES)
    return Token(access_token=token, token_type="bearer")


@router.get("/me", response_model=UserResponse)
def me(usuario_actual: User = Depends(get_current_user)):
    """Devuelve los datos del usuario autenticado (para restaurar la sesión)."""
    return usuario_actual


# ---------- Perfil ----------

@router.put("/perfil", response_model=UserResponse)
def actualizar_perfil(
    datos: UserUpdate,
    usuario_actual: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Actualiza datos del perfil: nombre y/o color de avatar.

    El cambio de correo no está permitido en esta versión (requiere re-verificación).
    """
    if datos.email is not None and datos.email != usuario_actual.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El cambio de correo no está disponible en esta versión",
        )

    if datos.nombre is not None and datos.nombre.strip():
        usuario_actual.nombre = datos.nombre.strip()
    if datos.avatar_color is not None and datos.avatar_color.strip():
        usuario_actual.avatar_color = datos.avatar_color.strip()

    db.commit()
    db.refresh(usuario_actual)
    return usuario_actual


@router.delete("/cuenta", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_cuenta(
    usuario_actual: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Elimina permanentemente la cuenta y todos sus datos (links y etiquetas)."""
    db.query(Link).filter(Link.user_id == usuario_actual.id).delete(synchronize_session=False)
    db.query(Tag).filter(Tag.user_id == usuario_actual.id).delete(synchronize_session=False)
    db.delete(usuario_actual)
    db.commit()
    return None


# ---------- Recuperación de contraseña ----------

@router.post("/recuperar")
def solicitar_recuperacion(solicitud: SolicitudRecuperacion, db: Session = Depends(get_db)):
    """
    Genera un token de recuperación válido por RESET_TOKEN_EXPIRE_MINUTES minutos.

    Nota de desarrollo: no hay servidor SMTP configurado, por lo que el token se
    devuelve en la respuesta. En producción habría que enviarlo por correo y NO
    revelarlo aquí (además de no delatar si el correo existe o no).
    """
    usuario = existe_usuario(db, solicitud.email)
    if not usuario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No hay una cuenta con ese correo")

    token = crear_token(
        {"sub": usuario.email, "proposito": "reset"},
        minutos=config.RESET_TOKEN_EXPIRE_MINUTES,
    )
    return {
        "mensaje": "Token de recuperación generado.",
        "reset_token": token,
    }


@router.post("/restablecer")
def restablecer_password(datos: RestablecerPassword, db: Session = Depends(get_db)):
    try:
        carga = decodificar_token(datos.token)
        email = carga.get("sub")
        if carga.get("proposito") != "reset" or not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token de recuperación inválido o expirado",
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token de recuperación inválido o expirado",
        ) from None

    usuario = existe_usuario(db, email)
    if not usuario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No hay una cuenta con ese correo")

    usuario.hashed_password = pwd_context.hash(datos.password)
    db.commit()
    return {"mensaje": "Contraseña actualizada con éxito. Ya puedes iniciar sesión."}
