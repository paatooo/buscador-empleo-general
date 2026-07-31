# -*- coding: utf-8 -*-
"""Acceso a la base de datos de este proyecto.

Funciona con dos motores sin que el resto del código lo note:
  - **Postgres (Supabase)** si hay conexión configurada en `conexion.py`.
  - **SQLite local** si no la hay (o si se pide una ruta explícita, como en
    los tests).

Todo el SQL de acá es portable entre ambos: parámetros con nombre (:x),
identificadores entre comillas dobles y nada de sintaxis propia de SQLite.

Esquema propio de este proyecto — no comparte tablas ni conexión con
mapa-mercado-laboral.
"""
import threading
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

import conexion

BASE = Path(__file__).parent
DB_PATH = BASE / "data" / "buscador.db"

CAMPOS_MARCA = ("revisada", "favorita", "postulada")

# Cachea el Engine por proceso: crear uno nuevo en cada llamada abre una
# conexión TCP+TLS desde cero cada vez. SQLAlchemy está pensado para crear
# el Engine una sola vez: su pool interno ya es seguro entre
# threads/sesiones concurrentes, así que reusarlo es lo correcto.
_ENGINES: dict = {}
_ENGINES_LOCK = threading.Lock()


def engine(db_path=None) -> Engine:
    """Motor de base de datos (cacheado). Postgres si está configurado; si
    no, SQLite."""
    if db_path is None:
        url = conexion.url_postgres()
        clave = ("nube", url) if url else ("local", str(DB_PATH))
    else:
        clave = ("local", str(Path(db_path)))
    with _ENGINES_LOCK:
        eng = _ENGINES.get(clave)
        if eng is None:
            if clave[0] == "nube":
                # pool_pre_ping: el pooler de Supabase cierra conexiones ociosas
                eng = create_engine(clave[1], pool_pre_ping=True, pool_recycle=280)
            else:
                path = Path(clave[1])
                path.parent.mkdir(exist_ok=True)
                eng = create_engine(f"sqlite:///{path}")
            _ENGINES[clave] = eng
        return eng


def es_nube(eng: Engine) -> bool:
    return eng.dialect.name == "postgresql"


def etiqueta(eng: Engine) -> str:
    return "Supabase (nube)" if es_nube(eng) else "SQLite local"


def ejecutar(eng: Engine, sql: str, params=None):
    """Ejecuta y confirma una sentencia."""
    with eng.begin() as con:
        return con.execute(text(sql), params or {})


def consultar(eng: Engine, sql: str, params=None) -> list:
    with eng.connect() as con:
        return con.execute(text(sql), params or {}).fetchall()


def escalar(eng: Engine, sql: str, params=None):
    with eng.connect() as con:
        return con.execute(text(sql), params or {}).scalar()


# Motores ya verificados en este proceso: inspeccionar el esquema contra
# Postgres es lento (varias consultas al catálogo) y el esquema no cambia
# mientras la app corre — sin esta caché, cada lectura pagaría ese costo
# de nuevo.
_ESQUEMA_LISTO: set = set()
_ESQUEMA_LOCK = threading.Lock()


def ensure_schema(eng: Engine) -> None:
    """Idempotente y cacheado por Engine: crea las tablas de este proyecto,
    pero solo la primera vez que se llama con un Engine dado en este
    proceso."""
    with _ESQUEMA_LOCK:
        if eng in _ESQUEMA_LISTO:
            return
        _ensure_schema_real(eng)
        _ESQUEMA_LISTO.add(eng)


def _ensure_schema_real(eng: Engine) -> None:
    ejecutar(eng, "CREATE TABLE IF NOT EXISTS usuarios ("
                  " id TEXT PRIMARY KEY, perfil_json TEXT, creado_en TEXT)")
    ejecutar(eng, "CREATE TABLE IF NOT EXISTS marcas ("
                  " usuario_id TEXT, job_url TEXT,"
                  " revisada INTEGER DEFAULT 0, favorita INTEGER DEFAULT 0,"
                  " postulada INTEGER DEFAULT 0, fecha TEXT,"
                  " PRIMARY KEY (usuario_id, job_url))")
    ejecutar(eng, "CREATE TABLE IF NOT EXISTS terminos_busqueda ("
                  " termino TEXT PRIMARY KEY, origen TEXT, agregado_en TEXT,"
                  " ultima_corrida TEXT, ofertas_ultimas INTEGER)")
    ejecutar(eng, "CREATE TABLE IF NOT EXISTS ofertas ("
                  " job_url TEXT PRIMARY KEY, site TEXT, search_term TEXT,"
                  " title TEXT, company TEXT, location TEXT,"
                  " date_posted TEXT, job_type TEXT, is_remote TEXT,"
                  " min_amount REAL, max_amount REAL, currency TEXT,"
                  " interval TEXT, description TEXT, scrape_date TEXT,"
                  " last_seen TEXT)")
    ejecutar(eng, "CREATE TABLE IF NOT EXISTS snapshots ("
                  " run_date TEXT, source TEXT, ofertas_total INTEGER,"
                  " ofertas_nuevas INTEGER, error TEXT)")
    ejecutar(eng, "CREATE TABLE IF NOT EXISTS oferta_analisis ("
                  " job_url TEXT PRIMARY KEY, habilidades TEXT, areas TEXT,"
                  " region TEXT, modalidad TEXT, tipo_contrato TEXT,"
                  " anios_experiencia_pedidos INTEGER,"
                  " ingles_excluyente INTEGER, duplicada INTEGER,"
                  " vigencia_estimada TEXT, analizado_en TEXT)")


def upsert_usuario(eng: Engine, usuario_id: str, perfil_json: str,
                   creado_en: str) -> None:
    """Crea o actualiza el perfil de un usuario. `creado_en` solo se fija
    la primera vez — actualizar el perfil no debe cambiar la fecha de
    alta.

    A diferencia de `upsert_marca` (Task 4), esta sentencia es idéntica en
    SQLite y Postgres — no hace falta ramificar por `es_nube`."""
    ejecutar(eng,
        "INSERT INTO usuarios (id, perfil_json, creado_en)"
        " VALUES (:id, :p, :c)"
        " ON CONFLICT (id) DO UPDATE SET perfil_json = :p",
        {"id": usuario_id, "p": perfil_json, "c": creado_en})


def cargar_usuario(eng: Engine, usuario_id: str) -> dict | None:
    filas = consultar(eng, "SELECT id, perfil_json, creado_en FROM usuarios"
                           " WHERE id = :id", {"id": usuario_id})
    if not filas:
        return None
    id_, perfil_json, creado_en = filas[0]
    return {"id": id_, "perfil_json": perfil_json, "creado_en": creado_en}
