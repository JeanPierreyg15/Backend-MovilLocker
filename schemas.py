from datetime import datetime
import re
from typing import List, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# ---------- Utilidades de validación ----------

def normalizar_url(valor: str) -> str:
    """Valida que sea una URL http/https y la normaliza (añade https:// si falta)."""
    texto = (valor or "").strip()
    if not texto:
        raise ValueError("La URL es obligatoria")

    esquema = re.match(r"^([a-zA-Z][a-zA-Z0-9+.-]*):", texto)
    if esquema:
        # Solo se permiten http/https: bloquea javascript:, data:, file:, etc.
        if esquema.group(1).lower() not in ("http", "https"):
            raise ValueError("La URL debe usar http o https")
        url = urlparse(texto)
    else:
        url = urlparse(f"https://{texto}")

    if url.scheme not in ("http", "https") or not url.netloc or " " in url.netloc:
        raise ValueError("La URL debe ser un enlace válido http o https")
    return url.geturl()


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


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginResponse(Token):
    usuario: UserResponse


class CambiarPassword(BaseModel):
    password_actual: str = Field(min_length=1, max_length=72)
    password_nueva: str = Field(min_length=8, max_length=72)


class EliminarCuenta(BaseModel):
    password: str = Field(min_length=1, max_length=72)


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
