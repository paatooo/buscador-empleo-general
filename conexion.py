# -*- coding: utf-8 -*-
"""Arma la URL de conexión a Postgres (Supabase) propia de este proyecto.

Pensado para que NO haya que percent-codificar la contraseña a mano: se
pega la cadena tal cual la entrega Supabase (dejando el marcador
[YOUR-PASSWORD]) y la contraseña va aparte; acá se codifica correctamente
aunque tenga @ # / : ? etc.

Fuentes, en orden: variables de entorno (Streamlit Cloud / CI) y luego
.streamlit/secrets.toml (local). Credenciales propias de este proyecto —
nunca las de mapa-mercado-laboral.
"""
import os
import re
import tomllib
from pathlib import Path
from urllib.parse import quote

BASE = Path(__file__).parent
SECRETS = BASE / ".streamlit" / "secrets.toml"

MARCADOR = re.compile(r"\[?YOUR-PASSWORD\]?|\[?TU_PASSWORD\]?", re.I)
SIN_PEGAR = "PEGA_AQUI"


def leer() -> dict:
    if os.environ.get("POSTGRES_URL"):
        return {"postgres_url": os.environ["POSTGRES_URL"],
                "password": os.environ.get("POSTGRES_PASSWORD", "")}
    if SECRETS.exists():
        datos = tomllib.loads(SECRETS.read_text(encoding="utf-8"))
        return datos.get("conexion") or {}
    return {}


def url_postgres() -> str | None:
    """URL lista para SQLAlchemy, o None si falta configuración."""
    datos = leer()
    url = str(datos.get("postgres_url") or "").strip()
    if not url or SIN_PEGAR in url:
        return None
    pwd = str(datos.get("password") or "").strip()
    if pwd:
        url = MARCADOR.sub(quote(pwd, safe=""), url, count=1)
    if MARCADOR.search(url):
        return None  # quedó el marcador sin reemplazar
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if url.startswith("postgresql://"):
        # SQLAlchemy usa psycopg2 por defecto para el esquema "postgresql://"
        # a secas, pero este proyecto solo instala psycopg v3 (psycopg[binary]
        # en requirements.txt). Sin este driver explícito, create_engine()
        # revienta con ModuleNotFoundError apenas se intenta conectar.
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def diagnostico() -> str | None:
    """Mensaje explicando qué falta, o None si está todo listo."""
    datos = leer()
    if not datos:
        return ("Falta el archivo .streamlit/secrets.toml.\n"
                "  Copia .streamlit/secrets.toml.ejemplo como secrets.toml.")
    url = str(datos.get("postgres_url") or "").strip()
    if not url or SIN_PEGAR in url:
        return ("Todavía no pegaste la cadena de Supabase en secrets.toml\n"
                "  (botón Connect -> pestaña Direct -> Session pooler -> URI).")
    if MARCADOR.search(url) and not str(datos.get("password") or "").strip():
        return ("La cadena tiene el marcador [YOUR-PASSWORD] pero no indicaste\n"
                "  la contraseña. Escríbela en el campo  password  de secrets.toml\n"
                "  (tal cual, sin codificar: el código la codifica solo).")
    if not url_postgres():
        return "La cadena de conexión no se pudo interpretar. Revísala."
    return None
