from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models import Link, Tag, User
from schemas import LinkCreate, LinkResponse
from routers.auth import get_current_user

router = APIRouter(prefix="/links", tags=["Links"])


@router.get("/", response_model=list[LinkResponse])
def obtener_links(db: Session = Depends(get_db), usuario_actual: User = Depends(get_current_user)):
    """Lista todos los links del usuario autenticado."""
    return db.query(Link).filter(Link.user_id == usuario_actual.id).all()


@router.post("/", response_model=LinkResponse)
def crear_link(
    link: LinkCreate,
    db: Session = Depends(get_db),
    usuario_actual: User = Depends(get_current_user),
):
    if link.tag_ids:
        encontradas = db.query(Tag).filter(
            Tag.id.in_(link.tag_ids), Tag.user_id == usuario_actual.id
        ).all()
        if len(encontradas) != len(set(link.tag_ids)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Alguna etiqueta no existe o no te pertenece",
            )
    else:
        encontradas = []

    nuevo_link = Link(url=link.url, titulo=link.titulo, user_id=usuario_actual.id, tags=encontradas)
    db.add(nuevo_link)
    db.commit()
    db.refresh(nuevo_link)
    return nuevo_link


@router.delete("/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_link(
    link_id: int,
    db: Session = Depends(get_db),
    usuario_actual: User = Depends(get_current_user),
):
    link = db.query(Link).filter(Link.id == link_id, Link.user_id == usuario_actual.id).first()
    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Enlace no encontrado o no autorizado",
        )
    db.delete(link)
    db.commit()
    return None
