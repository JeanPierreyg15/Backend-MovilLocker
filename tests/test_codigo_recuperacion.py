from datetime import timedelta

from models import PasswordReset, ahora_utc
from routers.auth import pwd_context
from database import SessionLocal

PASSWORD = "secreto123"


def registrar(cliente):
    return cliente.post(
        "/auth/register",
        json={"nombre": "Ana", "email": "ana@ejemplo.com", "password": PASSWORD},
    )


def login(cliente, password=PASSWORD):
    return cliente.post(
        "/auth/login", json={"email": "ana@ejemplo.com", "password": password}
    )


def pedir_codigo(cliente):
    respuesta = cliente.post("/auth/recuperar", json={"email": "ana@ejemplo.com"})
    assert respuesta.status_code == 200, respuesta.text
    codigo = respuesta.json()["codigo_desarrollo"]
    assert len(codigo) == 8 and codigo.isdigit()
    return codigo


def restablecer(cliente, codigo, password="nuevaClave99"):
    return cliente.post(
        "/auth/restablecer",
        json={"email": "ana@ejemplo.com", "codigo": codigo, "password": password},
    )


def _ultimo_reset():
    db = SessionLocal()
    try:
        return (
            db.query(PasswordReset)
            .order_by(PasswordReset.id.desc())
            .first()
        )
    finally:
        db.close()


def test_el_codigo_se_guarda_solo_como_hash(cliente):
    assert registrar(cliente).status_code == 200
    codigo = pedir_codigo(cliente)

    registro = _ultimo_reset()
    assert registro.codigo_hash != codigo
    assert codigo not in registro.codigo_hash
    assert pwd_context.verify(codigo, registro.codigo_hash)
    assert registro.usado is False
    assert registro.intentos == 0


def test_el_codigo_caduca(cliente):
    assert registrar(cliente).status_code == 200
    codigo = pedir_codigo(cliente)

    db = SessionLocal()
    try:
        registro = db.query(PasswordReset).order_by(PasswordReset.id.desc()).first()
        registro.expira_at = ahora_utc() - timedelta(seconds=1)
        db.commit()
    finally:
        db.close()

    respuesta = restablecer(cliente, codigo)
    assert respuesta.status_code == 400
    assert respuesta.json()["detail"] == "Código de recuperación inválido o expirado"

    # La contraseña no cambió y el código quedó marcado como usado.
    assert login(cliente).status_code == 200
    assert _ultimo_reset().usado is True


def test_el_codigo_es_de_un_solo_uso(cliente):
    assert registrar(cliente).status_code == 200
    codigo = pedir_codigo(cliente)

    assert restablecer(cliente, codigo).status_code == 200
    assert login(cliente, "nuevaClave99").status_code == 200

    reuso = restablecer(cliente, codigo, "otraClave99")
    assert reuso.status_code == 400
    # La contraseña sigue siendo la del primer cambio.
    assert login(cliente, "nuevaClave99").status_code == 200
    assert login(cliente, "otraClave99").status_code == 401


def test_el_codigo_se_agota_tras_cinco_intentos_fallidos(cliente):
    assert registrar(cliente).status_code == 200
    codigo = pedir_codigo(cliente)
    incorrecto = "00000000" if codigo != "00000000" else "11111111"

    for intento in range(5):
        respuesta = restablecer(cliente, incorrecto)
        assert respuesta.status_code == 400, intento
        assert respuesta.json()["detail"] == "Código de recuperación inválido o expirado"

    registro = _ultimo_reset()
    assert registro.intentos == 5
    assert registro.usado is True

    # Ni siquiera el código correcto vuelve a servir.
    assert restablecer(cliente, codigo).status_code == 400
    assert login(cliente).status_code == 200


def test_un_codigo_nuevo_invalida_el_anterior(cliente, monkeypatch):
    assert registrar(cliente).status_code == 200

    codigos = iter(["11111111", "22222222"])
    monkeypatch.setattr(
        "routers.auth._generar_codigo", lambda: next(codigos)
    )

    primero = pedir_codigo(cliente)
    segundo = pedir_codigo(cliente)
    assert (primero, segundo) == ("11111111", "22222222")

    # El primero ya no sirve; el segundo sí.
    assert restablecer(cliente, primero).status_code == 400
    assert restablecer(cliente, segundo).status_code == 200
    assert login(cliente, "nuevaClave99").status_code == 200


def test_no_enumera_correos_registrados(cliente):
    assert registrar(cliente).status_code == 200
    pedir_codigo(cliente)

    conocido = restablecer(cliente, "00000000")
    desconocido = cliente.post(
        "/auth/restablecer",
        json={
            "email": "nadie@ejemplo.com",
            "codigo": "00000000",
            "password": "nuevaClave99",
        },
    )

    assert conocido.status_code == desconocido.status_code == 400
    assert conocido.json() == desconocido.json()


def test_restablecer_exige_un_codigo_de_ocho_digitos(cliente):
    assert registrar(cliente).status_code == 200

    for codigo in ("1234567", "123456789", "1234567a", "abcdefgh"):
        respuesta = restablecer(cliente, codigo)
        assert respuesta.status_code == 422, codigo

    assert login(cliente).status_code == 200
