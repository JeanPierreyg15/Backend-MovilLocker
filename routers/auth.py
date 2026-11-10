import hashlib
import logging
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jwt import PyJWTError
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config import config
from correo import enmascarar_email, enviar_codigo_recuperacion
from database import get_db
from limitador import ip_cliente, limitar_peticiones
from models import User
from schemas import (
    CambiarPassword,
    EliminarCuenta,
    LoginResponse,
    Token,
    UserCreate,
    UserLogin,
    UserResponse,
    UserUpdate,
    validar_password_bytes,
)

router = APIRouter(prefix="/auth", tags=["Auth"])
logger = logging.getLogger("locker.auth")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# Hash falso para que el login tarde lo mismo exista o no el usuario (anti timing attack)
HASH_FALSO = pwd_context.hash("contraseña-falsa-para-comparacion")


# ---------- Esquemas propios de recuperación ----------

class SolicitudRecuperacion(BaseModel):
    email: EmailStr


class RestablecerPassword(BaseModel):
    token: str
    password: str


# ---------- Utilidades de token ----------

def crear_token(datos: dict, minutos: int) -> str:
    expiracion = datetime.now(timezone.utc) + timedelta(minutes=minutos)
    return jwt.encode({**datos, "exp": expiracion}, config.SECRET_KEY, algorithm=config.ALGORITHM)


def decodificar_token(token: str) -> dict:
    return jwt.decode(token, config.SECRET_KEY, algorithms=[config.ALGORITHM])


def huella_password(usuario: User) -> str:
    """Huella corta del hash actual: invalida el token de reset tras usarlo."""
    return hashlib.sha256(usuario.hashed_password.encode()).hexdigest()[:16]


def error_no_autorizado() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )


def existe_usuario(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    try:
        carga = decodificar_token(token)
        # Un token de recuperación no puede usarse como sesión
        if carga.get("proposito") is not None:
            raise error_no_autorizado()
        usuario_id = int(carga["sub"])
    except (PyJWTError, KeyError, ValueError):
        raise error_no_autorizado() from None

    usuario = db.get(User, usuario_id)
    if usuario is None or usuario.token_version != carga.get("ver"):
        raise error_no_autorizado()
    return usuario


# ---------- Registro / Login ----------

@router.post("/register", response_model=UserResponse)
def register(user: UserCreate, request: Request, db: Session = Depends(get_db)):
    limitar_peticiones(request, "register", maximo=10)

    if existe_usuario(db, user.email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email ya registrado")

    usuario_nuevo = User(
        nombre=user.nombre,
        email=user.email,
        hashed_password=pwd_context.hash(user.password),
        token_version=1,
    )
    db.add(usuario_nuevo)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email ya registrado") from None
    db.refresh(usuario_nuevo)
    return usuario_nuevo


@router.post("/login", response_model=LoginResponse)
def login(user: UserLogin, request: Request, db: Session = Depends(get_db)):
    # Cubo único IP + correo: evita que un usuario bloquee a todos los que
    # comparten IP (NAT) y limita la fuerza bruta contra una cuenta concreta.
    limitar_peticiones(
        request,
        "login",
        maximo=10,
        incluir_ip=False,
        claves_extra=[f"ip:{ip_cliente(request)}:correo:{user.email}"],
    )

    usuario = existe_usuario(db, user.email)
    if usuario is None:
        # Verificación contra hash falso: mismo tiempo de respuesta exista o no el email
        pwd_context.verify(user.password, HASH_FALSO)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")

    if not pwd_context.verify(user.password, usuario.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")

    token = crear_token(
        {"sub": str(usuario.id), "ver": usuario.token_version},
        minutos=config.ACCESS_TOKEN_EXPIRE_MINUTES,
    )
    return LoginResponse(access_token=token, usuario=usuario)


@router.get("/me", response_model=UserResponse)
def me(usuario_actual: User = Depends(get_current_user)):
    return usuario_actual


# ---------- Perfil ----------

@router.put("/perfil", response_model=UserResponse)
def actualizar_perfil(
    datos: UserUpdate,
    usuario_actual: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Actualiza nombre, bio y color de avatar. El cambio de correo no está permitido."""
    if datos.email is not None and datos.email != usuario_actual.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El cambio de correo no está disponible en esta versión",
        )

    if datos.nombre is not None:
        usuario_actual.nombre = datos.nombre
    if datos.bio is not None:
        usuario_actual.bio = datos.bio
    if datos.avatar_color is not None:
        usuario_actual.avatar_color = datos.avatar_color

    db.commit()
    db.refresh(usuario_actual)
    return usuario_actual


@router.put("/password", response_model=Token)
def cambiar_password(
    datos: CambiarPassword,
    request: Request,
    usuario_actual: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cambia la contraseña verificando la actual e invalida las sesiones anteriores."""
    limitar_peticiones(
        request,
        "password",
        maximo=5,
        claves_extra=[f"usuario:{usuario_actual.id}"],
    )

    if not pwd_context.verify(datos.password_actual, usuario_actual.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La contraseña actual no es correcta")

    if datos.password_actual == datos.password_nueva:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La nueva contraseña debe ser diferente a la actual",
        )

    usuario_actual.hashed_password = pwd_context.hash(datos.password_nueva)
    usuario_actual.token_version += 1
    db.commit()
    db.refresh(usuario_actual)

    # Se entrega un token nuevo para no cerrar la sesión del propio usuario
    token = crear_token(
        {"sub": str(usuario_actual.id), "ver": usuario_actual.token_version},
        minutos=config.ACCESS_TOKEN_EXPIRE_MINUTES,
    )
    return Token(access_token=token)


@router.delete("/cuenta", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_cuenta(
    datos: EliminarCuenta,
    request: Request,
    usuario_actual: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Elimina la cuenta (con sus links y etiquetas) tras confirmar la contraseña."""
    limitar_peticiones(
        request,
        "cuenta",
        maximo=5,
        claves_extra=[f"usuario:{usuario_actual.id}"],
    )

    if not pwd_context.verify(datos.password, usuario_actual.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La contraseña no es correcta")

    # El ORM elimina en cascada links, etiquetas y las filas de link_tags
    db.delete(usuario_actual)
    db.commit()
    return None


# ---------- Recuperación de contraseña ----------

def es_peticion_local(request: Request) -> bool:
    """True si la petición llega directamente desde loopback (desarrollo local)."""
    if request.headers.get("x-forwarded-for") or request.headers.get("x-real-ip"):
        # Detrás de un proxy todas las peticiones parecen venir de 127.0.0.1.
        return False
    host = request.client.host if request.client else ""
    return host in {"127.0.0.1", "::1", "localhost"}


@router.post("/recuperar")
def solicitar_recuperacion(
    solicitud: SolicitudRecuperacion,
    request: Request,
    tareas: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Solicita un enlace/código de recuperación.

    Por seguridad responde SIEMPRE lo mismo (exista o no el correo) y el envío
    SMTP se hace en segundo plano, de modo que el tiempo de respuesta no revela
    qué correos están registrados. Solo en desarrollo (DEBUG=true) y desde
    loopback se devuelve ``reset_token`` para probar el flujo sin servidor de
    correo.
    """
    limitar_peticiones(request, "recuperar", maximo=10)

    usuario = existe_usuario(db, solicitud.email)
    respuesta: dict = {"mensaje": "Si el correo está registrado, recibirás instrucciones para restablecer tu contraseña."}

    if usuario is not None:
        token = crear_token(
            {
                "sub": str(usuario.id),
                "proposito": "reset",
                "pwd": huella_password(usuario),
            },
            minutos=config.RESET_TOKEN_EXPIRE_MINUTES,
        )

        if config.smtp_configurado:
            # La respuesta se devuelve ya: el SMTP puede tardar (o fallar) sin
            # afectar al tiempo de respuesta ni revelar si el correo existe.
            tareas.add_task(enviar_codigo_recuperacion, usuario.email, token)
        elif config.DEBUG and es_peticion_local(request):
            # Barrera: exponer el token únicamente en local y con DEBUG activo.
            respuesta["reset_token"] = token
        else:
            logger.warning(
                "Recuperación solicitada para %s pero no se pudo entregar el correo "
                "(SMTP no configurado o falló). El usuario no recibirá instrucciones.",
                enmascarar_email(usuario.email),
            )

    return respuesta


@router.post("/restablecer")
def restablecer_password(datos: RestablecerPassword, db: Session = Depends(get_db)):
    try:
        carga = decodificar_token(datos.token)
        usuario = db.get(User, int(carga["sub"]))
        if (
            carga.get("proposito") != "reset"
            or usuario is None
            or carga.get("pwd") != huella_password(usuario)
        ):
            raise PyJWTError
    except (PyJWTError, KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código de recuperación inválido o expirado",
        ) from None

    if len(datos.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La contraseña debe tener al menos 8 caracteres",
        )
    try:
        validar_password_bytes(datos.password)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from None

    # Al cambiar el hash, el token deja de ser válido (huella distinta) y se
    # invalidan además todas las sesiones activas.
    usuario.hashed_password = pwd_context.hash(datos.password)
    usuario.token_version += 1
    db.commit()
    return {"mensaje": "Contraseña actualizada con éxito. Ya puedes iniciar sesión."}
