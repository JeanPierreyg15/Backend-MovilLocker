from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models import Link, Tag, User, link_tags, normalizar_nombre_etiqueta
from schemas import TagCountResponse, TagCreate, TagResponse
from routers.auth import get_current_user

router = APIRouter(prefix="/tags", tags=["Tags"])


def _conteo_links_por_etiqueta(db: Session, usuario_id: int) -> dict[int, int]:
    """Número real de links por etiqueta (sin el límite de la paginación)."""
    filas = (
        db.query(link_tags.c.tag_id, func.count(link_tags.c.link_id))
        .join(Link, Link.id == link_tags.c.link_id)
        .filter(Link.user_id == usuario_id)
        .group_by(link_tags.c.tag_id)
        .all()
    )
    return {tag_id: total for tag_id, total in filas}


def _buscar_por_nombre(db: Session, nombre: str, usuario_id: int, excluir_id: int | None = None):
    """Búsqueda por la clave normalizada (NFKC + casefold)."""
    consulta = db.query(Tag).filter(
        Tag.user_id == usuario_id,
        Tag.nombre_normalizado == normalizar_nombre_etiqueta(nombre),
    )
    if excluir_id is not None:
        consulta = consulta.filter(Tag.id != excluir_id)
    return consulta.first()


@router.get("/count")
def contar_etiquetas(
    db: Session = Depends(get_db),
    usuario_actual: User = Depends(get_current_user),
):
    """Total real de etiquetas del usuario."""
    total = (
        db.query(func.count(Tag.id))
        .filter(Tag.user_id == usuario_actual.id)
        .scalar()
    )
    return {"count": total or 0}


@router.get("/", response_model=list[TagCountResponse])
def listar_etiquetas(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
    usuario_actual: User = Depends(get_current_user),
):
    etiquetas = (
        db.query(Tag)
        .filter(Tag.user_id == usuario_actual.id)
        .order_by(Tag.nombre.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    conteos = _conteo_links_por_etiqueta(db, usuario_actual.id)
    return [
        TagCountResponse(
            id=etiqueta.id,
            nombre=etiqueta.nombre,
            icono=etiqueta.icono,
            links_count=conteos.get(etiqueta.id, 0),
        )
        for etiqueta in etiquetas
    ]


@router.post("/", response_model=TagResponse)
def crear_etiqueta(
    tag: TagCreate,
    db: Session = Depends(get_db),
    usuario_actual: User = Depends(get_current_user),
):
    if _buscar_por_nombre(db, tag.nombre, usuario_actual.id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Etiqueta ya registrada")

    nueva = Tag(
        nombre=tag.nombre,
        nombre_normalizado=normalizar_nombre_etiqueta(tag.nombre),
        icono=tag.icono,
        user_id=usuario_actual.id,
    )
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
    etiqueta.nombre_normalizado = normalizar_nombre_etiqueta(tag.nombre)
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
