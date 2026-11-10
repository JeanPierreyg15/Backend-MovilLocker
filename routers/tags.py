from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models import Tag, User
from schemas import TagCreate, TagResponse
from routers.auth import get_current_user

router = APIRouter(prefix="/tags", tags=["Tags"])


@router.get("/", response_model=list[TagResponse])
def listar_etiquetas(db: Session = Depends(get_db), usuario_actual: User = Depends(get_current_user)):
    """Lista las etiquetas del usuario autenticado."""
    return db.query(Tag).filter(Tag.user_id == usuario_actual.id).all()


@router.post("/", response_model=TagResponse)
def crear_etiqueta(
    tag: TagCreate,
    db: Session = Depends(get_db),
    usuario_actual: User = Depends(get_current_user),
):
    existe = db.query(Tag).filter(
        Tag.nombre == tag.nombre, Tag.user_id == usuario_actual.id
    ).first()
    if existe:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Etiqueta ya registrada")

    nueva = Tag(nombre=tag.nombre, user_id=usuario_actual.id)
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_etiqueta(
    tag_id: int,
    db: Session = Depends(get_db),
    usuario_actual: User = Depends(get_current_user),
):
    """Elimina una etiqueta propia (los links se siguen guardando, solo pierden esta etiqueta)."""
    etiqueta = db.query(Tag).filter(Tag.id == tag_id, Tag.user_id == usuario_actual.id).first()
    if not etiqueta:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Etiqueta no encontrada")
    db.delete(etiqueta)
    db.commit()
    return None
