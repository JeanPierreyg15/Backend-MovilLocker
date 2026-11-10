from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.types import TypeDecorator

from database import Base


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Guarda UTC sin zona (SQLite no la soporta) y la restaura al leer.

    SQLite devuelve ``created_at`` como datetime naive. Sin este decorador,
    Pydantic lo serializa sin ``Z`` y el navegador lo interpreta como hora
    local (de ahí los "dentro de 5 horas" en zonas como America/Lima).
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    avatar_color = Column(String(7), nullable=True)
    bio = Column(Text, nullable=True)
    # Versión de sesión: se incrementa al cambiar/restablecer contraseña para
    # invalidar todos los JWT emitidos anteriormente.
    token_version = Column(Integer, nullable=False, default=1)
    created_at = Column(UTCDateTime, default=ahora_utc)

    links = relationship(
        "Link", back_populates="owner", cascade="all, delete-orphan"
    )
    tags = relationship(
        "Tag", back_populates="owner", cascade="all, delete-orphan"
    )
    password_resets = relationship(
        "PasswordReset", back_populates="usuario", cascade="all, delete-orphan"
    )


link_tags = Table(
    "link_tags",
    Base.metadata,
    Column("link_id", Integer, ForeignKey("links.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Link(Base):
    __tablename__ = "links"
    __table_args__ = (
        UniqueConstraint("user_id", "url", name="uq_links_usuario_url"),
    )
    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, nullable=False)
    titulo = Column(String, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    created_at = Column(UTCDateTime, default=ahora_utc)

    owner = relationship("User", back_populates="links")
    tags = relationship("Tag", secondary=link_tags, back_populates="links")


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("user_id", "nombre", name="uq_tags_usuario_nombre"),)
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, index=True, nullable=False)
    icono = Column(String(16), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(UTCDateTime, default=ahora_utc)

    owner = relationship("User", back_populates="tags")
    links = relationship("Link", secondary=link_tags, back_populates="tags")


class PasswordReset(Base):
    """Código de recuperación de contraseña.

    El código numérico nunca se guarda en claro: solo su hash bcrypt. Cada
    código caduca, es de un solo uso y admite un máximo de intentos fallidos.
    """

    __tablename__ = "password_resets"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    codigo_hash = Column(String, nullable=False)
    expira_at = Column(UTCDateTime, nullable=False)
    intentos = Column(Integer, nullable=False, default=0)
    usado = Column(Boolean, nullable=False, default=False)
    created_at = Column(UTCDateTime, default=ahora_utc)

    usuario = relationship("User", back_populates="password_resets")
