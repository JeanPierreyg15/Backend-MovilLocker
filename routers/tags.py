from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models import Tag, User
from schemas import TagCreate, TagResponse
from routers.auth import get_current_user

router = APIRouter(prefix="/tags", tags=["Tags"])


def _buscar_por_nombre(db: Session, nombre: str, usuario_id: int, excluir_id: int | None = None):
    """Búsqueda de etiqueta por nombre sin distinguir mayúsculas/minúsculas."""
    consulta = db.query(Tag).filter(
        Tag.user_id == usuario_id, func.lower(Tag.nombre) == nombre.lower()
    )
    if excluir_id is not None:
        consulta = consulta.filter(Tag.id != excluir_id)
    return consulta.first()


@router.get("/", response_model=list[TagResponse])
def listar_etiquetas(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
    usuario_actual: User = Depends(get_current_user),
):
    return (
        db.query(Tag)
        .filter(Tag.user_id == usuario_actual.id)
        .order_by(Tag.nombre.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.post("/", response_model=TagResponse)
def crear_etiqueta(
    tag: TagCreate,
    db: Session = Depends(get_db),
    usuario_actual: User = Depends(get_current_user),
):
    if _buscar_por_nombre(db, tag.nombre, usuario_actual.id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Etiqueta ya registrada")

    nueva = Tag(nombre=tag.nombre, icono=tag.icono, user_id=usuario_actual.id)
    db.add(nueva)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Etiqueta ya registrada") from None
    db.refresh(nueva)
    return nueva


@router.put("/{tag_id}", response_model=TagResponse)
def actualizar_etiqueta(
    tag_id: int,
    tag: TagCreate,
    db: Session = Depends(get_db),
    usuario_actual: User = Depends(get_current_user),
):
    etiqueta = db.query(Tag).filter(
        Tag.id == tag_id, Tag.user_id == usuario_actual.id
    ).first()
    if not etiqueta:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Etiqueta no encontrada")

    if _buscar_por_nombre(db, tag.nombre, usuario_actual.id, excluir_id=tag_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ya tienes una etiqueta con ese nombre")

    etiqueta.nombre = tag.nombre
    etiqueta.icono = tag.icono
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ya tienes una etiqueta con ese nombre") from None
    db.refresh(etiqueta)
    return etiqueta


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_etiqueta(
    tag_id: int,
    db: Session = Depends(get_db),
    usuario_actual: User = Depends(get_current_user),
):
    """Elimina una etiqueta propia (los links se conservan, solo pierden la etiqueta)."""
    etiqueta = db.query(Tag).filter(
        Tag.id == tag_id, Tag.user_id == usuario_actual.id
    ).first()
    if not etiqueta:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Etiqueta no encontrada")
    db.delete(etiqueta)
    db.commit()
    return None
