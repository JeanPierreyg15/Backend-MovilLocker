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

> Las migraciones se aplican solas al arrancar (`AUTO_MIGRATE=true`). También
> puedes ejecutarlas manualmente:
>
> ```bash
> .venv\Scripts\alembic upgrade head
> ```
>
> **Con más de un worker** (por ejemplo `uvicorn --workers 4`) pon
> `AUTO_MIGRATE=false` y ejecuta `alembic upgrade head` como paso del despliegue,
> antes de arrancar los workers. Así varias instancias no compiten por migrar la
> misma base de datos.
>
> Una `locker.db` de una versión anterior **se actualiza sin perder datos**: las
> migraciones conservan las tablas existentes y añaden columnas, índices y la
> canonicalización de URLs.

## Variables de entorno

| Variable | Obligatoria | Descripción |
|----------|-------------|-------------|
| `SECRET_KEY` | Sí | Firma de los JWT. Mínimo 32 caracteres. |
| `ALGORITHM` | No | Algoritmo JWT (por defecto `HS256`). |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | Vida del token de sesión (60). |
| `RESET_TOKEN_EXPIRE_MINUTES` | No | Vida del código de recuperación (15). |
| `DEBUG` | No | Si es `true`, `/auth/recuperar` devuelve el código **solo a peticiones desde loopback**. **Solo desarrollo.** |
| `CORS_ORIGINS` | No | Orígenes permitidos separados por coma. No admite `*`. |
| `DATABASE_URL` | No | Cadena SQLAlchemy (por defecto `sqlite:///./locker.db`). |
| `AUTO_MIGRATE` | No | Aplica `alembic upgrade head` al arrancar (por defecto `true`). |
| `SMTP_HOST` | No | Servidor SMTP para enviar el código de recuperación. |
| `SMTP_PORT` | No | Puerto SMTP (587). |
| `SMTP_USER` / `SMTP_PASSWORD` | No | Credenciales SMTP (usa una contraseña de aplicación). |
| `SMTP_FROM` | No | Remitente visible (por defecto `SMTP_USER`). |
| `SMTP_TLS` / `SMTP_SSL` | No | STARTTLS (587) o SSL directo (465). |
| `APP_URL` | No | URL pública usada en el correo de recuperación. |
| `TRUSTED_PROXIES` | No | IPs de proxies de confianza separadas por coma. Solo desde ellas se acepta `X-Forwarded-For`. |
| `VENTANA_RATE_LIMIT_SEGUNDOS` | No | Ventana del rate limit (60 s). |
| `LIMITE_LOGIN` / `LIMITE_REGISTRO` | No | Intentos por ventana (20 / 10). |
| `LIMITE_RECUPERAR` / `LIMITE_RESTABLECER` | No | Intentos por ventana (10 / 10). |
| `LIMITE_CAMBIAR_PASSWORD` / `LIMITE_ELIMINAR_CUENTA` | No | Intentos por ventana (10 / 5). |

El rate limit es **en memoria y por proceso**. Con varios workers cada uno lleva
su cuenta; si necesitas un límite global, usa un almacén compartido (Redis).

Ejemplo de `CORS_ORIGINS` para web + Capacitor:

```
http://localhost:5173,http://127.0.0.1:5173,capacitor://localhost,https://localhost,http://localhost
```

## Recuperación de contraseña

- `POST /auth/recuperar` responde **siempre 200** con el mismo mensaje, exista o
  no el correo (no revela cuentas registradas).
- El código se envía por SMTP si defines `SMTP_HOST` y `SMTP_FROM` (o
  `SMTP_USER`). El envío se hace en segundo plano para no bloquear la respuesta.
  Sin SMTP, en producción el usuario no recibe nada: la app registra una
  advertencia ruidosa al arrancar.
- El código es de un solo uso: al cambiar la contraseña la huella del hash cambia
  y el token deja de ser válido.
- Con `DEBUG=true`, `reset_token` solo se devuelve si la petición viene de
  loopback (`127.0.0.1`/`::1`). Si llega desde un móvil físico (no loopback), el
  token se escribe en el log del servidor para poder probar el flujo sin SMTP.
  Si `DEBUG=true` y hay orígenes CORS no locales, el backend avisa al arrancar.
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
| GET | `/links/?skip=&limit=` | Lista links del usuario (más recientes primero, por defecto 100) |
| GET | `/links/count` | Total real de links del usuario (`{count}`) |
| POST | `/links/` | Crea link (`url`, `titulo`, `tag_ids`) |
| PUT | `/links/{id}` | Edita link |
| DELETE | `/links/{id}` | Elimina link |
| GET | `/tags/?skip=&limit=` | Lista etiquetas (incluye `links_count` real por etiqueta) |
| GET | `/tags/count` | Total real de etiquetas del usuario (`{count}`) |
| POST | `/tags/` | Crea etiqueta (`nombre`, `icono`) |
| PUT | `/tags/{id}` | Renombra / cambia icono |
| DELETE | `/tags/{id}` | Elimina etiqueta (los links se conservan) |

Notas de validación:

- Emails se normalizan a minúsculas.
- URLs solo `http`/`https`; se añade `https://` si falta y se rechazan
  `javascript:`, `data:`, `file:`. Se canonicalizan (esquema/host en minúsculas,
  sin `:80`/`:443`, sin `#fragmento` y sin `/` final en la raíz) para que dos
  formas de la misma URL cuenten como un solo link.
- No se permiten URLs duplicadas por usuario (también garantizado por la BD).
- Etiquetas únicas por usuario sin distinguir mayúsculas.
- `avatar_color` debe ser hex `#RRGGBB`.
- Rate limiting por IP: login (IP + correo), registro, recuperación,
  restablecimiento, cambio de contraseña y borrado de cuenta. Los máximos se
  configuran en `.env`; los registros inactivos se depuran solos.

## Tests

```bash
.venv\Scripts\python -m pytest tests -q
```

La suite cubre registro/login, perfil, links (incluidas URLs peligrosas,
duplicados, paginación y conteo real), aislamiento entre usuarios, etiquetas con
`links_count`, recuperación monouso (solo loopback en DEBUG), migración de una
base de datos antigua, borrado en cascada incluso con FK antiguas sin
`ON DELETE CASCADE`, invalidación de sesiones, borrado de cuenta y healthcheck.

## Docker

```bash
docker build -t locker-api .
docker run --env-file .env -p 8000:8000 locker-api
```

La imagen corre con un usuario sin privilegios y tiene `HEALTHCHECK` sobre
`/health`. Con Docker Compose la base SQLite queda en un volumen, así que
recrear el contenedor no borra los datos:

```bash
docker compose up --build
```

El servicio escucha en `http://localhost:8000` y guarda la BD en
`sqlite:////data/locker.db`.

## Estructura

```
main.py            App FastAPI, CORS, healthcheck, migraciones y routers
config.py          Configuración (SECRET_KEY obligatoria, SMTP, CORS)
correo.py          Envío del código de recuperación por SMTP
database.py        Engine, sesión y PRAGMA foreign_keys para SQLite
models.py          User, Link, Tag, link_tags y UTCDateTime (UTC en SQLite)
schemas.py         Validación de entrada/salida (Pydantic)
alembic/           Migraciones (esquema inicial + columnas de perfil)
routers/auth.py    Registro, login, perfil, contraseña y recuperación
routers/links.py   CRUD de links por usuario + conteo
routers/tags.py    CRUD de etiquetas por usuario + conteo
tests/             Pruebas con pytest + TestClient
```
