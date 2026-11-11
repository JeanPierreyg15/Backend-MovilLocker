from datetime import datetime, timezone
import re
from typing import List, Optional
from urllib.parse import urlparse, urlunparse

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_serializer, field_validator


# ---------- Utilidades de validación ----------

def normalizar_url(valor: str) -> str:
    """Valida que sea una URL http/https y la normaliza (añade https:// si falta).

    Reglas:
    - Si hay algo: al inicio y lo que sigue empieza con //, el esquema debe ser http/https.
    - Si hay algo: al inicio y lo que sigue son 1-5 dígitos seguidos de /, ?, # o fin → host:puerto, se antepone https://.
    - Cualquier otro esquema (javascript:, data:, file:, mailto:…) se rechaza.
    - El hostname debe existir y no ser solo puntos.
    - Se canonicaliza para detectar duplicados: esquema y host en minúsculas,
      sin puerto por defecto (:80 en http, :443 en https), sin #fragmento y sin
      la / final cuando la ruta es solo la raíz.
    - Máximo 2048 caracteres.
    """
    texto = (valor or "").strip()
    if not texto:
        raise ValueError("La URL es obligatoria")

    if len(texto) > 2048:
        raise ValueError("La URL no puede superar 2048 caracteres")

    esquema = re.match(r"^([a-zA-Z][a-zA-Z0-9+.-]*):(.*)", texto, re.DOTALL)
    if esquema:
        nombre_esquema = esquema.group(1).lower()
        resto = esquema.group(2)
        if nombre_esquema in ("http", "https"):
            # Esquema http/https explícito: procesamos tal cual
            url = urlparse(texto)
        elif re.match(r"^(\d{1,5})([/?#]|$)", resto):
            # Parece host:puerto (ej. localhost:3000 o midominio.com:8080/ruta)
            url = urlparse(f"https://{texto}")
        else:
            # javascript:, data:, file:, mailto:, etc. → rechazado
            raise ValueError("La URL debe usar http o https")
    else:
        url = urlparse(f"https://{texto}")

    # El hostname debe existir y no ser solo puntos
    hostname = url.hostname or ""
    if not hostname or re.fullmatch(r"\.+", hostname):
        raise ValueError("La URL debe ser un enlace válido http o https")

    if url.scheme not in ("http", "https") or not url.netloc or " " in url.netloc:
        raise ValueError("La URL debe ser un enlace válido http o https")

    return _url_canonica(url)


def _url_canonica(url) -> str:
    """Reconstruye la URL con la forma canónica usada para detectar duplicados."""
    esquema = url.scheme.lower()
    host = (url.hostname or "").lower()
    try:
        puerto = url.port
    except ValueError:
        raise ValueError("La URL debe ser un enlace válido http o https") from None

    if (esquema == "http" and puerto == 80) or (esquema == "https" and puerto == 443):
        puerto = None

    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = f"{host}:{puerto}" if puerto else host

    ruta = url.path or ""
    if ruta == "/":
        ruta = ""

    # El fragmento nunca identifica el recurso en el servidor: no distingue links.
    return urlunparse((esquema, netloc, ruta, url.params, url.query, ""))


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


def _validar_bytes_password(valor: str) -> str:
    """Valida que la contraseña no supere 72 bytes UTF-8 (límite de bcrypt)."""
    if len(valor.encode("utf-8")) > 72:
        raise ValueError(
            "La contraseña no puede superar 72 bytes. "
            "Algunos caracteres especiales (ñ, á, 中…) ocupan más de 1 byte."
        )
    return valor


class UserCreate(UserBase):
    # bcrypt trunca en silencio a 72 bytes: validamos en bytes, no en caracteres
    password: str = Field(min_length=8)

    @field_validator("password")
    @classmethod
    def password_en_bytes(cls, valor: str) -> str:
        return _validar_bytes_password(valor)


class UserUpdate(BaseModel):
    nombre: Optional[str] = Field(default=None, min_length=1, max_length=80)
    email: Optional[EmailStr] = None
    avatar_color: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    bio: Optional[str] = Field(default=None, max_length=280)

    @field_validator("email")
    @classmethod
    def email_minusculas(cls, valor):
        return valor.strip().lower() if valor else valor

    @field_validator("nombre")
    @classmethod
    def nombre_sin_espacios(cls, valor):
        if valor is None:
            return valor
        limpio = valor.strip()
        if not limpio:
            raise ValueError("El nombre no puede estar vacío")
        return limpio

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
    # No se limita la longitud: una cuenta antigua pudo guardar una contraseña
    # larga y bcrypt solo compara sus primeros 72 bytes.
    password: str = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def email_minusculas(cls, valor: str) -> str:
        return valor.strip().lower()


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginResponse(Token):
    usuario: UserResponse


class CambiarPassword(BaseModel):
    password_actual: str = Field(min_length=1)
    password_nueva: str = Field(min_length=8)

    @field_validator("password_nueva")
    @classmethod
    def password_nueva_en_bytes(cls, valor: str) -> str:
        return _validar_bytes_password(valor)


class EliminarCuenta(BaseModel):
    password: str = Field(min_length=1)


class RestablecerPassword(BaseModel):
    """Restablecimiento con el código recibido por correo."""

    token: str = Field(min_length=1)
    password: str = Field(min_length=8)

    @field_validator("password")
    @classmethod
    def password_en_bytes(cls, valor: str) -> str:
        return _validar_bytes_password(valor)


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
    tag_ids: List[int] = Field(default_factory=list, max_length=50)

    @field_validator("tag_ids")
    @classmethod
    def sin_duplicados(cls, valores: List[int]) -> List[int]:
        """Conserva el orden pero elimina ids repetidos."""
        return list(dict.fromkeys(valores))


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
