# Locker API (Backend-MovilLocker)

API REST en FastAPI para la app Locker: autenticación con JWT, links y etiquetas por usuario.

## Requisitos

- Python 3.11+
- pip

## Configuración

1. Crea y activa un entorno virtual:

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate
```

2. Instala dependencias:

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt   # solo para tests
```

3. Copia `.env.example` como `.env` y genera una clave segura:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Pega el resultado en `SECRET_KEY`. La aplicación **no arranca** si la clave falta
o tiene menos de 32 caracteres.

4. Arranca el servidor:

```bash
uvicorn main:app --reload --port 8000
```

Documentación interactiva: <http://localhost:8000/docs>
Healthcheck: <http://localhost:8000/health>

> Si ya tenías una base de datos `locker.db` de una versión anterior, bórrala:
> `create_all()` no modifica tablas existentes y faltarían columnas nuevas
> (`bio`, `token_version`, `tags.icono`). En producción usa migraciones (Alembic).

## Variables de entorno

| Variable | Obligatoria | Descripción |
|----------|-------------|-------------|
| `SECRET_KEY` | Sí | Firma de los JWT. Mínimo 32 caracteres. |
| `ALGORITHM` | No | Algoritmo JWT (por defecto `HS256`). |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | Vida del token de sesión (60). |
| `RESET_TOKEN_EXPIRE_MINUTES` | No | Vida del código de recuperación (15). |
| `DEBUG` | No | Si es `true`, `/auth/recuperar` devuelve el código de recuperación. **Solo desarrollo.** |
| `CORS_ORIGINS` | No | Orígenes permitidos separados por coma. |
| `DATABASE_URL` | No | Cadena SQLAlchemy (por defecto `sqlite:///./locker.db`). |

Ejemplo de `CORS_ORIGINS` para web + Capacitor:

```
http://localhost:5173,http://127.0.0.1:5173,capacitor://localhost,https://localhost,http://localhost
```

## Recuperación de contraseña

- `POST /auth/recuperar` responde **siempre 200** con el mismo mensaje, exista o
  no el correo (no revela cuentas registradas).
- El código es de un solo uso: al cambiar la contraseña la huella del hash cambia
  y el token deja de ser válido.
- Con `DEBUG=true` el código se devuelve en `reset_token` para poder probar el
  flujo en local. En producción debe enviarse por email (SMTP, Resend, SendGrid...),
  lo cual **queda pendiente de configurar**.
- Cambiar o restablecer la contraseña incrementa `token_version`, por lo que todos
  los JWT de sesión emitidos antes dejan de funcionar.

## Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/health` | Estado de la API y de la base de datos |
| POST | `/auth/register` | Registro (`nombre`, `email`, `password` 8–72) |
| POST | `/auth/login` | Login → `{access_token, token_type, usuario}` |
| GET | `/auth/me` | Usuario autenticado |
| PUT | `/auth/perfil` | Actualiza `nombre`, `bio`, `avatar_color` |
| PUT | `/auth/password` | Cambia contraseña (`password_actual`, `password_nueva`) → token nuevo |
| DELETE | `/auth/cuenta` | Elimina la cuenta (body `{password}`) y todos sus datos |
| POST | `/auth/recuperar` | Solicita código de recuperación |
| POST | `/auth/restablecer` | Restablece con `{token, password}` |
| GET | `/links/?skip=&limit=` | Lista links del usuario (más recientes primero) |
| POST | `/links/` | Crea link (`url`, `titulo`, `tag_ids`) |
| PUT | `/links/{id}` | Edita link |
| DELETE | `/links/{id}` | Elimina link |
| GET | `/tags/?skip=&limit=` | Lista etiquetas |
| POST | `/tags/` | Crea etiqueta (`nombre`, `icono`) |
| PUT | `/tags/{id}` | Renombra / cambia icono |
| DELETE | `/tags/{id}` | Elimina etiqueta (los links se conservan) |

Notas de validación:

- Emails se normalizan a minúsculas.
- URLs solo `http`/`https`; se añade `https://` si falta y se rechazan
  `javascript:`, `data:`, `file:`.
- No se permiten URLs duplicadas por usuario.
- Etiquetas únicas por usuario sin distinguir mayúsculas.
- `avatar_color` debe ser hex `#RRGGBB`.
- Rate limiting básico: 20 login/min y 10 recuperaciones/min por IP.

## Tests

```bash
.venv\Scripts\python -m pytest tests -q
```

La suite cubre registro/login, perfil, links (incluidas URLs peligrosas y
duplicados), aislamiento entre usuarios, etiquetas, recuperación monouso,
invalidación de sesiones, borrado de cuenta y healthcheck.

## Docker

```bash
docker build -t locker-api .
docker run --env-file .env -p 8000:8000 locker-api
```

## Estructura

```
main.py            App FastAPI, CORS, healthcheck y routers
config.py          Configuración (SECRET_KEY obligatoria)
database.py        Engine, sesión y PRAGMA foreign_keys para SQLite
models.py          User, Link, Tag y tabla link_tags con cascadas
schemas.py         Validación de entrada/salida (Pydantic)
routers/auth.py    Registro, login, perfil, contraseña y recuperación
routers/links.py   CRUD de links por usuario
routers/tags.py    CRUD de etiquetas por usuario
tests/             Pruebas con pytest + TestClient
```
