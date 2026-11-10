from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("SECRET_KEY")
    @classmethod
    def validar_secret_key(cls, valor: str) -> str:
        if not valor or len(valor) < 32:
            raise ValueError(
                "SECRET_KEY debe tener al menos 32 caracteres. "
                'Genera una con: python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        return valor

    @property
    def origenes_cors(self) -> list[str]:
        return [origen.strip() for origen in self.CORS_ORIGINS.split(",") if origen.strip()]


config = Configuracion()
