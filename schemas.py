from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------- Usuarios / Autenticación ----------

class UserBase(BaseModel):
    email: EmailStr
    nombre: str = Field(min_length=1)


class UserCreate(UserBase):
    password: str = Field(min_length=6)


class UserUpdate(BaseModel):
    nombre: Optional[str] = None
    email: Optional[EmailStr] = None
    avatar_color: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    email: str
    nombre: str
    avatar_color: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str


# ---------- Etiquetas ----------

class TagBase(BaseModel):
    nombre: str = Field(min_length=1)


class TagCreate(TagBase):
    pass


class TagResponse(TagBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


# ---------- Links ----------

class LinkBase(BaseModel):
    url: str
    titulo: str


class LinkCreate(LinkBase):
    tag_ids: Optional[List[int]] = []


class LinkResponse(LinkBase):
    id: int
    tags: List[TagResponse] = []
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
