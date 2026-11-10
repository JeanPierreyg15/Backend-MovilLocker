from datetime import datetime, timezone
import re
from typing import List, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_serializer, field_validator


# ---------- Utilidades de validación ----------

LONGITUD_MAXIMA_URL = 2048
LONGITUD_MAXIMA_PASSWORD_BYTES = 72
ESQUEMAS_PERMITIDOS = frozenset({"http", "https"})
ESQUEMAS_PELIGROSOS = frozenset(
    {"javascript", "data", "file", "vbscript", "blob", "mailto", "tel"}
)


def validar_password_bytes(valor: str) -> str:
    """bcrypt solo usa los primeros 72 BYTES (no caracteres) de la contraseña."""
    if len(valor.encode("utf-8")) > LONGITUD_MAXIMA_PASSWORD_BYTES:
        raise ValueError(
            f"La contraseña no puede superar los {LONGITUD_MAXIMA_PASSWORD_BYTES} bytes "
            "(bcrypt trunca las contraseñas más largas)"
        )
    return valor


def normalizar_url(valor: str) -> str:
    """Valida que sea una URL http/https y la normaliza (añade https:// si falta).

    Un esquema solo se considera explícito si va seguido de ``://``: así
    ``localhost:3000`` o ``example.com:8443`` se tratan como host:puerto y no
    como un esquema desconocido. Los esquemas peligrosos se rechazan aunque
    no lleven ``//`` (``javascript:``, ``data:``, ``mailto:``...).
    """
    texto = (valor or "").strip()
    if not texto:
        raise ValueError("La URL es obligatoria")
    if len(texto) > LONGITUD_MAXIMA_URL:
        raise ValueError(f"La URL no puede superar los {LONGITUD_MAXIMA_URL} caracteres")
    if any(caracter.isspace() for caracter in texto):
        raise ValueError("La URL no puede contener espacios")

    coincidencia = re.match(r"^([a-zA-Z][a-zA-Z0-9+.-]*)://", texto)
    if coincidencia:
        if coincidencia.group(1).lower() not in ESQUEMAS_PERMITIDOS:
            raise ValueError("La URL debe usar http o https")
        try:
            url = urlparse(texto)
        except ValueError as error:
            raise ValueError("La URL debe ser un enlace válido http o https") from error
    else:
        posible_esquema = re.match(r"^([a-zA-Z][a-zA-Z0-9+.-]*):", texto)
        if (
            posible_esquema
            and posible_esquema.group(1).lower() in ESQUEMAS_PELIGROSOS
        ):
            raise ValueError("La URL debe usar http o https")
        try:
            url = urlparse(f"https://{texto}")
        except ValueError as error:
            raise ValueError("La URL debe ser un enlace válido http o https") from error

    if url.scheme not in ESQUEMAS_PERMITIDOS or not url.netloc:
        raise ValueError("La URL debe ser un enlace válido http o https")
    try:
        # hostname/port lanzan ValueError con hosts o puertos malformados.
        if not url.hostname:
            raise ValueError
        url.port
    except ValueError as error:
        raise ValueError("La URL debe ser un enlace válido http o https") from error

    # El host no distingue mayúsculas/minúsculas y la barra final del path es
    # redundante: normalizarlos evita duplicados que solo difieren en eso.
    netloc = url.netloc
    if "@" in netloc:
        credenciales, host_puerto = netloc.rsplit("@", 1)
        netloc = f"{credenciales}@{host_puerto.lower()}"
    else:
        netloc = netloc.lower()

    ruta = url.path
    if not url.query and not url.fragment:
        if ruta == "/":
            ruta = ""
        elif ruta.endswith("/"):
            ruta = ruta[:-1]

    return url._replace(netloc=netloc, path=ruta).geturl()


# ---------- Usuarios / Autenticación ----------

class UserBase(BaseModel):
    email: EmailStr
    nombre: str = Field(min_length=1, max_length=80)

    @field_validator("email")
    @classmethod
    def email_minusculas(cls, valor: str) -> str:
        return valor.strip().lower()

    @field_validator("nombre")
    @classmethod
    def nombre_sin_espacios(cls, valor: str) -> str:
        limpio = valor.strip()
        if not limpio:
            raise ValueError("El nombre no puede estar vacío")
        return limpio


class UserCreate(UserBase):
    # bcrypt solo usa los primeros 72 bytes: limitamos para evitar sorpresas
    password: str = Field(min_length=8, max_length=72)

    @field_validator("password")
    @classmethod
    def password_en_bytes(cls, valor: str) -> str:
        return validar_password_bytes(valor)


class UserUpdate(BaseModel):
    nombre: Optional[str] = Field(default=None, min_length=1, max_length=80)
    email: Optional[EmailStr] = None
    avatar_color: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    bio: Optional[str] = Field(default=None, max_length=280)

    @field_validator("email")
    @classmethod
    def email_minusculas(cls, valor):
        return valor.strip().lower() if valor else valor

    @field_validator("bio")
    @classmethod
    def bio_limpia(cls, valor):
        return valor.strip() if valor else valor


class UserResponse(BaseModel):
    id: int
    email: str
    nombre: str
    avatar_color: Optional[str] = None
    bio: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)

    @field_validator("email")
    @classmethod
    def email_minusculas(cls, valor: str) -> str:
        return valor.strip().lower()

    @field_validator("password")
    @classmethod
    def password_en_bytes(cls, valor: str) -> str:
        return validar_password_bytes(valor)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginResponse(Token):
    usuario: UserResponse


class CambiarPassword(BaseModel):
    password_actual: str = Field(min_length=1, max_length=72)
    password_nueva: str = Field(min_length=8, max_length=72)

    @field_validator("password_actual", "password_nueva")
    @classmethod
    def passwords_en_bytes(cls, valor: str) -> str:
        return validar_password_bytes(valor)


class EliminarCuenta(BaseModel):
    password: str = Field(min_length=1, max_length=72)

    @field_validator("password")
    @classmethod
    def password_en_bytes(cls, valor: str) -> str:
        return validar_password_bytes(valor)


# ---------- Etiquetas ----------

class TagBase(BaseModel):
    nombre: str = Field(min_length=1, max_length=40)
    icono: Optional[str] = Field(default=None, max_length=16)

    @field_validator("nombre")
    @classmethod
    def nombre_limpio(cls, valor: str) -> str:
        limpio = valor.strip()
        if not limpio:
            raise ValueError("El nombre de la etiqueta no puede estar vacío")
        return limpio


class TagCreate(TagBase):
    pass


class TagResponse(TagBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class TagCountResponse(TagResponse):
    """Etiqueta con el número real de links que la usan."""

    links_count: int = 0


# ---------- Links ----------

class LinkBase(BaseModel):
    url: str
    titulo: str = Field(min_length=1, max_length=200)

    @field_validator("url")
    @classmethod
    def url_valida(cls, valor: str) -> str:
        return normalizar_url(valor)

    @field_validator("titulo")
    @classmethod
    def titulo_limpio(cls, valor: str) -> str:
        limpio = valor.strip()
        if not limpio:
            raise ValueError("El título no puede estar vacío")
        return limpio


class LinkCreate(LinkBase):
    tag_ids: Optional[List[int]] = []


class LinkResponse(LinkBase):
    id: int
    tags: List[TagResponse] = []
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("created_at", when_used="json")
    def serializar_created_at(self, valor: Optional[datetime]) -> Optional[str]:
        """Siempre emite UTC con sufijo Z, aunque la fecha llegue naive."""
        if valor is None:
            return None
        if valor.tzinfo is None:
            valor = valor.replace(tzinfo=timezone.utc)
        return valor.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
