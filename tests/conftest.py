import os

# La configuración se lee al importar la app: definimos el entorno de pruebas ANTES.
os.environ["SECRET_KEY"] = "clave-de-pruebas-con-mas-de-32-caracteres-123456"
os.environ["DATABASE_URL"] = "sqlite:///./test_locker.db"
os.environ["DEBUG"] = "true"
os.environ["CORS_ORIGINS"] = "http://localhost:5173"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "60"
# Los tests crean el esquema con Base.metadata.create_all(); las migraciones se
# prueban por separado sobre bases temporales.
os.environ["AUTO_MIGRATE"] = "false"

import pytest
from fastapi.testclient import TestClient

from database import Base, engine
from limitador import reiniciar as reiniciar_limitador
from main import app


@pytest.fixture()
def cliente():
    # El rate limit es en memoria y por IP: se limpia para que un test no
    # afecte al siguiente al ejecutar la suite varias veces seguidas.
    reiniciar_limitador()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app, client=("127.0.0.1", 50000)) as test_client:
        yield test_client
