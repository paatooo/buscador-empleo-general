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

# Un término corrido hace menos de esto no vuelve a proponerse: evita
# volver a scrapear lo que ya se buscó recién. PROVISIONAL: calibrar
# contra la duración real de una corrida completa cuando exista el
# pipeline de recolección.
_HORAS_MIN_ENTRE_CORRIDAS = 24

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


def upsert_marca(eng: Engine, usuario_id: str, job_url: str, campo: str,
                 valor: bool, fecha: str) -> None:
    """Crea o actualiza una marca de un usuario sobre una oferta. Atómico y
    seguro con escritores concurrentes (INSERT ... ON CONFLICT en vez de
    UPDATE-luego-INSERT, que puede chocar si dos procesos marcan la misma
    oferta al mismo tiempo)."""
    if campo not in CAMPOS_MARCA:
        raise ValueError(f"campo inválido: {campo}")
    with eng.begin() as con:
        if es_nube(eng):
            con.execute(text(
                "INSERT INTO marcas (usuario_id, job_url, revisada,"
                " favorita, postulada, fecha) VALUES (:u, :j, 0, 0, 0, :f)"
                " ON CONFLICT (usuario_id, job_url)"
                f' DO UPDATE SET "{campo}" = :v, fecha = :f'),
                {"u": usuario_id, "j": job_url, "v": int(valor), "f": fecha})
            # ON CONFLICT sólo pisa el campo pedido en la fila EXISTENTE; en
            # una fila recién creada por este mismo INSERT, además hay que
            # fijarlo (el INSERT deja 0 en todos los campos por defecto).
            con.execute(
                text(f'UPDATE marcas SET "{campo}" = :v'
                     " WHERE usuario_id = :u AND job_url = :j"
                     f' AND "{campo}" != :v'),
                {"u": usuario_id, "j": job_url, "v": int(valor)})
        else:
            con.execute(text(
                "INSERT INTO marcas (usuario_id, job_url, revisada,"
                " favorita, postulada, fecha) VALUES (:u, :j, 0, 0, 0, :f)"
                " ON CONFLICT (usuario_id, job_url) DO NOTHING"),
                {"u": usuario_id, "j": job_url, "f": fecha})
            con.execute(
                text(f'UPDATE marcas SET "{campo}" = :v, fecha = :f'
                     " WHERE usuario_id = :u AND job_url = :j"),
                {"v": int(valor), "f": fecha, "u": usuario_id, "j": job_url})


def cargar_marcas(eng: Engine, usuario_id: str) -> dict:
    filas = consultar(eng,
        "SELECT job_url, revisada, favorita, postulada, fecha FROM marcas"
        " WHERE usuario_id = :u", {"u": usuario_id})
    return {
        job_url: {"revisada": revisada, "favorita": favorita,
                  "postulada": postulada, "fecha": fecha}
        for job_url, revisada, favorita, postulada, fecha in filas
    }


def agregar_termino(eng: Engine, termino: str, origen: str,
                    agregado_en: str) -> None:
    """No hace nada si el término ya existe — no se pisa su origen ni su
    fecha de alta por un segundo aporte del mismo término."""
    with eng.begin() as con:
        con.execute(text(
            "INSERT INTO terminos_busqueda (termino, origen, agregado_en)"
            " VALUES (:t, :o, :a)"
            " ON CONFLICT (termino) DO NOTHING"),
            {"t": termino, "o": origen, "a": agregado_en})


def registrar_corrida_termino(eng: Engine, termino: str,
                              ofertas_encontradas: int, fecha: str) -> None:
    ejecutar(eng,
        "UPDATE terminos_busqueda SET ultima_corrida = :f,"
        " ofertas_ultimas = :n WHERE termino = :t",
        {"f": fecha, "n": ofertas_encontradas, "t": termino})


def terminos_pendientes(eng: Engine, limite: int | None = None,
                        ahora: str | None = None) -> list[str]:
    """Orden de prioridad: términos de usuario nunca corridos primero,
    luego términos base nunca corridos, luego el resto — dentro de ese
    resto, los que sí devolvieron ofertas la última vez antes que los
    estériles (`ofertas_ultimas == 0`), y entre iguales, del más antiguo
    al más reciente. Excluye lo corrido en las últimas
    `_HORAS_MIN_ENTRE_CORRIDAS` horas."""
    from datetime import datetime, timedelta, timezone

    # datetime.utcnow() está deprecado desde 3.12; esto da el mismo
    # datetime naive en UTC (mismo valor, mismo isoformat) sin la
    # advertencia, así que no cambia el formato de las cadenas que ya se
    # comparan lexicográficamente contra ultima_corrida.
    ahora_dt = (datetime.fromisoformat(ahora) if ahora
                else datetime.now(timezone.utc).replace(tzinfo=None))
    corte = (ahora_dt - timedelta(hours=_HORAS_MIN_ENTRE_CORRIDAS)).isoformat()

    filas = consultar(eng,
        "SELECT termino, origen, ultima_corrida, ofertas_ultimas"
        " FROM terminos_busqueda"
        " WHERE ultima_corrida IS NULL OR ultima_corrida < :corte",
        {"corte": corte})

    def prioridad(fila):
        termino, origen, ultima_corrida, ofertas_ultimas = fila
        if ultima_corrida is None and origen == "usuario":
            return (0, "", "")
        if ultima_corrida is None:
            return (1, "", "")
        esteril = 1 if not ofertas_ultimas else 0
        return (2, esteril, ultima_corrida)  # estéril al final; luego más antiguo primero

    ordenados = sorted(filas, key=prioridad)
    terminos = [f[0] for f in ordenados]
    return terminos[:limite] if limite is not None else terminos
