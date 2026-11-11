from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# env_file relativo se resuelve contra el directorio de trabajo: al arrancar
# desde otra carpeta (systemd, Docker, IDE) el .env no se encontraba.
RAIZ_PROYECTO = Path(__file__).resolve().parent


class Configuracion(BaseSettings):
    """Configuración de la app. Lee las variables del archivo .env.

    SECRET_KEY es obligatoria y debe tener al menos 32 caracteres:
    si falta, la aplicación no arranca (mejor fallar claro que firmar
    tokens con una clave débil conocida).
    """

    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    RESET_TOKEN_EXPIRE_MINUTES: int = 15
    DEBUG: bool = False

    # Orígenes permitidos para CORS (separados por coma en .env).
    # Incluye Vite en desarrollo y los orígenes que usa el WebView de Capacitor.
    CORS_ORIGINS: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "capacitor://localhost,https://localhost,http://localhost"
    )

    DATABASE_URL: str = "sqlite:///./locker.db"

    # Migraciones: al arrancar se aplica `alembic upgrade head` salvo que se
    # desactive (útil si las migraciones se ejecutan en un paso de despliegue).
    AUTO_MIGRATE: bool = True

    # Envío de correo para la recuperación de contraseña (SMTP).
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM: str | None = None
    SMTP_TLS: bool = True
    SMTP_SSL: bool = False

    # URL pública de la app, usada en el cuerpo del correo de recuperación.
    APP_URL: str = "http://localhost:5173"

    # Proxies de confianza (separados por coma). Solo si la petición llega desde
    # uno de ellos se usa X-Forwarded-For; de lo contrario cualquiera podría
    # falsificar su IP y saltarse el rate limit.
    TRUSTED_PROXIES: str = ""

    # Límite de intentos por ventana. Los máximos viven aquí para poder ajustarlos
    # sin tocar código. Con varios workers hace falta un almacén compartido
    # (Redis): esta implementación es en memoria y cada proceso lleva su cuenta.
    VENTANA_RATE_LIMIT_SEGUNDOS: int = 60
    LIMITE_LOGIN: int = 20
    LIMITE_REGISTRO: int = 10
    LIMITE_RECUPERAR: int = 10
    LIMITE_RESTABLECER: int = 10
    LIMITE_CAMBIAR_PASSWORD: int = 10
    LIMITE_ELIMINAR_CUENTA: int = 5

    model_config = SettingsConfigDict(
        env_file=RAIZ_PROYECTO / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("SECRET_KEY")
    @classmethod
    def validar_secret_key(cls, valor: str) -> str:
        if not valor or len(valor) < 32:
            raise ValueError(
                "SECRET_KEY debe tener al menos 32 caracteres. "
                'Genera una con: python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        return valor

    @field_validator("CORS_ORIGINS")
    @classmethod
    def validar_origenes_cors(cls, valor: str) -> str:
        """Rechaza el comodín: con credenciales permitiría cualquier origen."""
        origenes = [origen.strip() for origen in valor.split(",") if origen.strip()]
        if "*" in origenes:
            raise ValueError(
                "CORS_ORIGINS no puede contener '*': la API envía credenciales. "
                "Indica los orígenes exactos separados por coma."
            )
        return ",".join(origenes)

    @property
    def origenes_cors(self) -> list[str]:
        return [origen.strip() for origen in self.CORS_ORIGINS.split(",") if origen.strip()]

    @property
    def proxies_confiables(self) -> set[str]:
        return {
            proxy.strip()
            for proxy in self.TRUSTED_PROXIES.split(",")
            if proxy.strip()
        }

    @property
    def smtp_configurado(self) -> bool:
        return bool(self.SMTP_HOST and (self.SMTP_FROM or self.SMTP_USER))


config = Configuracion()
