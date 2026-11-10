import sqlite3
from pathlib import Path

from main import (
    _bloquear_migraciones,
    _desbloquear_migraciones,
    _ruta_lock_migraciones,
    ejecutar_migraciones,
)


def test_el_lock_de_migraciones_se_libera(tmp_path):
    ruta = tmp_path / "migraciones.lock"

    primero = _bloquear_migraciones(ruta)
    _desbloquear_migraciones(primero)

    # Si no se hubiera liberado, el segundo bloqueo fallaría o se quedaría colgado.
    segundo = _bloquear_migraciones(ruta)
    _desbloquear_migraciones(segundo)


def test_la_ruta_del_lock_esta_junto_a_la_base_de_datos():
    ruta = _ruta_lock_migraciones()
    assert ruta.name == ".locker-migraciones.lock"
    assert ruta.parent == Path.cwd().resolve()


def test_las_migraciones_se_pueden_ejecutar_dos_veces(tmp_path, monkeypatch):
    ruta_db = tmp_path / "migraciones.db"
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", f"sqlite:///{ruta_db.as_posix()}")

    ejecutar_migraciones()
    ejecutar_migraciones()  # el lock se libera y la segunda pasada es idempotente

    conexion = sqlite3.connect(ruta_db)
    tablas = {fila[0] for fila in conexion.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conexion.close()

    assert {"users", "links", "tags", "link_tags", "alembic_version"} <= tablas
