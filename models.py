from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Table, UniqueConstraint
from sqlalchemy.orm import relationship
from database import Base


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    avatar_color = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=ahora_utc)

    links = relationship("Link", back_populates="owner")
    tags = relationship("Tag", back_populates="owner")


link_tags = Table(
    "link_tags",
    Base.metadata,
    Column("link_id", Integer, ForeignKey("links.id"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id"), primary_key=True),
)


class Link(Base):
    __tablename__ = "links"
    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, nullable=False)
    titulo = Column(String, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=ahora_utc)

    owner = relationship("User", back_populates="links")
    tags = relationship("Tag", secondary=link_tags, back_populates="links")


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("user_id", "nombre", name="uq_tags_usuario_nombre"),)
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=ahora_utc)

    owner = relationship("User", back_populates="tags")
    links = relationship("Link", secondary=link_tags, back_populates="tags")
