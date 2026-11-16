import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import scraper
from config import config
from database import get_db
from models import Link, Tag, User
from schemas import LinkCreate, LinkPreview, LinkResponse, normalizar_url
from routers.auth import get_current_user, limitar_peticiones

router = APIRouter(prefix="/links", tags=["Links"])
logger = logging.getLogger("locker.links")


@router.get("/preview", response_model=LinkPreview)
def vista_previa(
    request: Request,
    url: str = Query(min_length=1, max_length=2048),
    usuario_actual: User = Depends(get_current_user),
):
    """Web scraping: devuelve título, descripción e imagen de la página.

    Si la página no se puede leer (caída, bloquea bots, no es HTML...) responde
    200 solo con la URL y el dominio: el cliente simplemente no autocompleta.
    Las direcciones no públicas (localhost, red privada...) se rechazan con 400.
    """
    limitar_peticiones(
        request,
        "preview",
        config.LIMITE_PREVIEW,
        clave_extra=str(usuario_actual.id),
    )
    try:
        url_normalizada = normalizar_url(url)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from None

    try:
        vista = scraper.obtener_vista_previa(url_normalizada)
    except scraper.DestinoNoPermitido:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede generar la vista previa de esa dirección",
        ) from None
    except scraper.ErrorVistaPrevia as error:
        logger.info("Vista previa no disponible para %s: %s", url_normalizada, error)
        vista = scraper.VistaPrevia(url=url_normalizada, sitio=scraper.urlparse(url_normalizada).hostname)

    return LinkPreview(
        url=vista.url,
        titulo=vista.titulo,
        descripcion=vista.descripcion,
        imagen=vista.imagen,
        sitio=vista.sitio,
    )


def _etiquetas_del_usuario(db: Session, tag_ids: list[int], usuario_id: int) -> list[Tag]:
    if not tag_ids:
        return []
    encontradas = db.query(Tag).filter(Tag.id.in_(tag_ids), Tag.user_id == usuario_id).all()
    if len(encontradas) != len(set(tag_ids)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Alguna etiqueta no existe o no te pertenece",
        )
    return encontradas


@router.get("/count")
def contar_links(
    db: Session = Depends(get_db),
    usuario_actual: User = Depends(get_current_user),
):
    """Total real de links del usuario (no limitado por la paginación)."""
    total = (
        db.query(func.count(Link.id))
        .filter(Link.user_id == usuario_actual.id)
        .scalar()
    )
    return {"count": total or 0}


@router.get("/", response_model=list[LinkResponse])
def obtener_links(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    usuario_actual: User = Depends(get_current_user),
):
    """Lista los links del usuario, del más reciente al más antiguo y paginados."""
    return (
        db.query(Link)
        .filter(Link.user_id == usuario_actual.id)
        .order_by(Link.created_at.desc(), Link.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.post("/", response_model=LinkResponse)
def crear_link(
    link: LinkCreate,
    db: Session = Depends(get_db),
    usuario_actual: User = Depends(get_current_user),
):
    duplicado = db.query(Link).filter(
        Link.user_id == usuario_actual.id, Link.url == link.url
    ).first()
    if duplicado:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ese enlace ya está guardado")

    nuevo_link = Link(
        url=link.url,
        titulo=link.titulo,
        user_id=usuario_actual.id,
        tags=_etiquetas_del_usuario(db, link.tag_ids or [], usuario_actual.id),
    )
    db.add(nuevo_link)
    try:
        db.commit()
    except IntegrityError:
        # Carrera entre dos peticiones simultáneas: la restricción de BD gana.
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ese enlace ya está guardado") from None
    db.refresh(nuevo_link)
    return nuevo_link


@router.put("/{link_id}", response_model=LinkResponse)
def actualizar_link(
    link_id: int,
    link: LinkCreate,
    db: Session = Depends(get_db),
    usuario_actual: User = Depends(get_current_user),
):
    existente = db.query(Link).filter(
        Link.id == link_id, Link.user_id == usuario_actual.id
    ).first()
    if not existente:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enlace no encontrado o no autorizado")

    duplicado = db.query(Link).filter(
        Link.user_id == usuario_actual.id, Link.url == link.url, Link.id != link_id
    ).first()
    if duplicado:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ese enlace ya está guardado")

    existente.url = link.url
    existente.titulo = link.titulo
    existente.tags = _etiquetas_del_usuario(db, link.tag_ids or [], usuario_actual.id)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ese enlace ya está guardado") from None
    db.refresh(existente)
    return existente


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
