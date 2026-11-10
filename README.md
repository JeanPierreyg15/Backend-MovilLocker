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
> El arranque toma un lock de archivo (`.locker-migraciones.lock`) para que
> varios workers del mismo host no migren a la vez. En producción con varias
> réplicas se recomienda `AUTO_MIGRATE=false` y ejecutar `alembic upgrade head`
> como paso único de despliegue.
>
> Una `locker.db` de una versión anterior **se actualiza sin perder datos**: la
> migración inicial conserva las tablas existentes, la segunda añade `bio`,
> `token_version` y `tags.icono`, la tercera fusiona URLs duplicadas y crea la
> restricción única `(user_id, url)`, y la cuarta añade `password_resets` para
> los códigos de recuperación.

## Variables de entorno

| Variable | Obligatoria | Descripción |
|----------|-------------|-------------|
| `SECRET_KEY` | Sí | Firma de los JWT. Mínimo 32 caracteres. |
| `ALGORITHM` | No | Algoritmo JWT (por defecto `HS256`). |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | Vida del token de sesión (60). |
| `RESET_TOKEN_EXPIRE_MINUTES` | No | Vida del código de recuperación (15). |
| `DEBUG` | No | Si es `true`, `/auth/recuperar` devuelve el código **solo a peticiones desde loopback**. **Solo desarrollo.** |
| `CORS_ORIGINS` | No | Orígenes permitidos separados por coma. |
| `DATABASE_URL` | No | Cadena SQLAlchemy (por defecto `sqlite:///./locker.db`). |
| `AUTO_MIGRATE` | No | Aplica `alembic upgrade head` al arrancar (por defecto `true`). Con varias réplicas, desactívalo y migra como paso de despliegue. |
| `TRUSTED_PROXIES` | No | IPs/CIDR de proxies de confianza separadas por coma. Solo desde ellas se acepta `X-Forwarded-For` como IP real. |
| `SMTP_HOST` | No | Servidor SMTP para enviar el código de recuperación. |
| `SMTP_PORT` | No | Puerto SMTP (587). |
| `SMTP_USER` / `SMTP_PASSWORD` | No | Credenciales SMTP (usa una contraseña de aplicación). |
| `SMTP_FROM` | No | Remitente visible (por defecto `SMTP_USER`). |
| `SMTP_TLS` / `SMTP_SSL` | No | STARTTLS (587) o SSL directo (465). |
| `APP_URL` | No | URL pública de la app. Solo si es `http`/`https` con un host no local se incluye un enlace en el correo; si no, se envía solo el código. |

Ejemplo de `CORS_ORIGINS` para web + Capacitor:

```
http://localhost:5173,http://127.0.0.1:5173,capacitor://localhost,https://localhost,http://localhost
```

## Recuperación de contraseña

- `POST /auth/recuperar` responde **siempre 200** con el mismo mensaje, exista o
  no el correo (no revela cuentas registradas). El envío SMTP se hace en segundo
  plano (`BackgroundTasks`), así que el tiempo de respuesta tampoco lo revela.
- El código es numérico, de **8 dígitos**, generado con `secrets` (admite ceros a
  la izquierda como `00123456`).
- En la base de datos solo se guarda su **hash bcrypt** en `password_resets`,
  junto con la caducidad, el número de intentos y si ya se usó.
- El código **caduca** a los `RESET_TOKEN_EXPIRE_MINUTES` (15 por defecto), es de
  **un solo uso** y admite un **máximo de 5 intentos fallidos**; al agotarlos se
  invalida aunque después se introduzca el correcto.
- Pedir un código nuevo invalida el anterior: solo sirve el último solicitado.
- Los logs enmascaran el correo (`a***@ejemplo.com`); nunca se registra completo.
- El código se envía por SMTP si defines `SMTP_HOST` y `SMTP_FROM` (o
  `SMTP_USER`). Sin SMTP, en producción el usuario no recibe nada: la app
  registra una advertencia ruidosa al arrancar.
- El correo incluye el código y, **solo si `APP_URL` es una web real** (http/https
  con host no local), un enlace a `APP_URL/recuperar?correo=...&codigo=...`. Con
  `localhost`, loopback o dominios `.local` no se envía enlace.
- Con `DEBUG=true`, `codigo_desarrollo` solo se devuelve si la petición viene de
  loopback (`127.0.0.1`/`::1`). Si `DEBUG=true` y hay orígenes CORS no locales,
  el backend avisa en el log al arrancar.
- Cambiar o restablecer la contraseña incrementa `token_version`, por lo que todos
  los JWT de sesión emitidos antes dejan de funcionar. `POST /auth/cerrar-sesiones`
  hace lo mismo y devuelve un token nuevo al dispositivo que lo solicita.

## Errores y logs

- Un error inesperado devuelve `{"detail": "Error interno del servidor"}` con
  estado 500, sin exponer trazas ni datos internos. La traza completa queda en
  el log del servidor.
- Cada petición genera una línea con método, ruta, estado y duración. Nunca se
  registran cuerpos, cabeceras `Authorization` ni tokens.

## Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/health` | Estado de la API y de la base de datos |
| POST | `/auth/register` | Registro (`nombre`, `email`, `password` de 8 caracteres a 72 bytes) |
| POST | `/auth/login` | Login → `{access_token, token_type, usuario}` |
| GET | `/auth/me` | Usuario autenticado |
| PUT | `/auth/perfil` | Actualiza `nombre`, `bio`, `avatar_color` |
| PUT | `/auth/password` | Cambia contraseña (`password_actual`, `password_nueva`) → token nuevo |
| POST | `/auth/cerrar-sesiones` | Invalida los JWT anteriores y devuelve un token nuevo para este dispositivo |
| DELETE | `/auth/cuenta` | Elimina la cuenta (body `{password}`) y todos sus datos |
| POST | `/auth/recuperar` | Envía un código de 8 dígitos al correo (`{email}`) |
| POST | `/auth/restablecer` | Restablece con `{email, codigo, password}` |
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
- Contraseñas: mínimo 8 caracteres y máximo 72 **bytes** UTF-8 (bcrypt trunca
  a 72 bytes, no a 72 caracteres). Se valida también en el frontend con
  `TextEncoder`.
- URLs solo `http`/`https`; se añade `https://` si falta (también en
  `localhost:3000` o `example.com:8443/ruta`), se rechazan los esquemas
  peligrosos (`javascript:`, `data:`, `file:`, `vbscript:`, `blob:`, `mailto:`,
  `tel:`) y las URLs de más de 2048 caracteres o con espacios.
- No se permiten URLs duplicadas por usuario: el host se guarda en minúsculas,
  se quita la barra final redundante y la BD tiene una restricción única
  `(user_id, url)` (la migración fusiona duplicados previos conservando el más
  antiguo y sus etiquetas).
- Etiquetas únicas por usuario sin distinguir mayúsculas.
- `avatar_color` debe ser hex `#RRGGBB`.
- Rate limiting en memoria:
  - registro: 10/min por IP;
  - login: 10/min por combinación IP + correo;
  - recuperación: 10/min por IP;
  - restablecer: 10/min por combinación IP + correo;
  - cambio de contraseña y borrado de cuenta: 5/min por IP y por usuario.
  - Solo se usa `X-Forwarded-For` si la petición viene de una IP de
    `TRUSTED_PROXIES`; si no, la cabecera se ignora.
  - **Limitación**: el contador vive en el proceso. Con varios workers o
    réplicas cada uno lleva su propia cuenta (el límite efectivo se multiplica).
    Para producción con varios workers usa un almacén compartido (Redis) o un
    límite en el proxy inverso.

## Tests

```bash
.venv\Scripts\python -m pytest tests -q
```

La suite cubre registro/login, perfil, links (incluidas URLs peligrosas,
duplicados, paginación y conteo real), aislamiento entre usuarios, etiquetas con
`links_count`, recuperación por código de 8 dígitos (hash en BD, caducidad, un
solo uso, máximo de intentos y no enumeración), migración de una base de datos
antigua, borrado en cascada incluso con FK antiguas sin `ON DELETE CASCADE`,
invalidación de sesiones, borrado de cuenta y healthcheck.

## Docker

```bash
docker build -t locker-api .
docker run --env-file .env -p 8000:8000 locker-api
```

## Estructura

```
main.py            App FastAPI, CORS, healthcheck, migraciones y routers
config.py          Configuración (SECRET_KEY obligatoria, SMTP, CORS)
correo.py          Envío del código de recuperación por SMTP
database.py        Engine, sesión y PRAGMA foreign_keys para SQLite
limitador.py       Rate limiting en memoria (IP, usuario, X-Forwarded-For)
models.py          User, Link, Tag, PasswordReset, link_tags y UTCDateTime
schemas.py         Validación de entrada/salida (Pydantic)
alembic/           Migraciones (esquema, perfil, URLs únicas y códigos de recuperación)
routers/auth.py    Registro, login, perfil, contraseña y recuperación
routers/links.py   CRUD de links por usuario + conteo
routers/tags.py    CRUD de etiquetas por usuario + conteo
tests/             Pruebas con pytest + TestClient
```
