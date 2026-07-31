# Capa de datos — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir el esquema, el motor de conexión cacheado y las
operaciones de lectura/escritura atómicas que necesita el resto del
proyecto — usuarios, marcas por usuario, términos de búsqueda, ofertas y su
análisis genérico — sin scraping ni interfaz todavía.

**Architecture:** Dos módulos en la raíz del proyecto, mismo patrón que
`mapa-mercado-laboral` (motor de base de datos y esquema cacheados por
proceso — la lección de rendimiento más cara de aquel proyecto), pero con
código, esquema y credenciales propios: `conexion.py` arma la URL de
Postgres desde secretos propios; `db.py` expone un `Engine` cacheado, crea
el esquema de forma idempotente, y ofrece funciones atómicas de
lectura/escritura. Todo se prueba contra SQLite temporal — no hace falta
Postgres real para correr la suite.

**Tech Stack:** Python 3.11+, SQLAlchemy 2.x, `psycopg[binary]` como driver
de Postgres, SQLite vía la biblioteca estándar para pruebas y desarrollo
local. pytest para las pruebas.

## Global Constraints

- **Proyecto independiente.** No importar, copiar ni depender de nada de
  `mapa-mercado-laboral`. Ese repo no se toca — se puede leer como
  referencia, nunca importar.
- **Motor y esquema cacheados por proceso**, desde el primer día: crear un
  `Engine` nuevo en cada llamada, o reinspeccionar el esquema en cada
  consulta, es la causa de lentitud que ya se pagó una vez en el proyecto
  de referencia.
- **`oferta_analisis` guarda solo lo genérico.** Nada de `match`,
  `cargo_no_afin`, `electrico` ni detalle de puntaje — eso depende del
  perfil de cada usuario y se calcula al vuelo con `motor.puntaje.puntuar`
  desde una capa posterior (la app), no se persiste acá.
- **Los upserts son atómicos.** `INSERT ... ON CONFLICT`, no
  `SELECT`-luego-`UPDATE`: dos escritores concurrentes (una corrida de
  scraping y un usuario marcando una oferta al mismo tiempo) no deben poder
  dejar filas a medio actualizar ni duplicadas.
- **Las marcas son por usuario.** `usuario_id` entra a la llave primaria de
  `marcas`; las marcas de una persona nunca deben aparecer al consultar las
  de otra.
- **SQL portable entre SQLite y Postgres**: parámetros con nombre (`:x`),
  identificadores entre comillas dobles cuando hace falta, nada de sintaxis
  exclusiva de un motor.
- **Sin CV, sin datos de terceros.** Esta capa no maneja nada de eso — está
  fuera de alcance del proyecto en esta fase.
- **Nombres en español**, consistentes con el resto del proyecto.

---

## Estructura de archivos

```
buscador-empleo-personalizado/
├── conexion.py            arma la URL de Postgres desde secretos propios
├── db.py                  Engine cacheado, esquema, upserts, consultas
├── .streamlit/
│   └── secrets.toml.ejemplo   plantilla, sin credenciales reales
├── requirements.txt        sqlalchemy, psycopg[binary]
├── requirements-dev.txt    pytest (ya existe)
└── tests/
    ├── test_conexion.py
    └── test_db.py
```

`conexion.py` no depende de `db.py`. `db.py` importa `conexion` solo para
resolver la URL cuando no se pasa una ruta local explícita — el mismo
patrón que ya probó su valor en el proyecto de referencia. Ninguno de los
dos módulos importa nada de `motor/`: la capa de datos no calcula puntajes,
solo guarda y entrega lo genérico.

---

### Task 1: Conexión a Postgres desde secretos propios

Arma la URL de conexión sin que haya que codificar la contraseña a mano.
Sin base de datos real todavía — solo parseo de configuración.

**Files:**
- Create: `conexion.py`
- Create: `.streamlit/secrets.toml.ejemplo`
- Test: `tests/test_conexion.py`

**Interfaces:**
- Consumes: nada
- Produces:
  - `leer() -> dict` — configuración desde variables de entorno o
    `secrets.toml`
  - `url_postgres() -> str | None` — URL lista para SQLAlchemy, o `None` si
    falta configuración
  - `diagnostico() -> str | None` — mensaje explicando qué falta, o `None`
    si está todo listo

- [ ] **Step 1: Escribir la prueba que falla**

Crear `tests/test_conexion.py`:

```python
# -*- coding: utf-8 -*-
import conexion


def test_leer_desde_variable_de_entorno(monkeypatch):
    monkeypatch.setenv("POSTGRES_URL", "postgresql://x/y")
    monkeypatch.setenv("POSTGRES_PASSWORD", "secreta")
    datos = conexion.leer()
    assert datos == {"postgres_url": "postgresql://x/y", "password": "secreta"}


def test_leer_sin_configuracion_da_vacio(monkeypatch, tmp_path):
    monkeypatch.delenv("POSTGRES_URL", raising=False)
    monkeypatch.setattr(conexion, "SECRETS", tmp_path / "no_existe.toml")
    assert conexion.leer() == {}


def test_url_postgres_reemplaza_el_marcador(monkeypatch):
    monkeypatch.setenv("POSTGRES_URL",
                       "postgresql://u:[YOUR-PASSWORD]@host/db")
    monkeypatch.setenv("POSTGRES_PASSWORD", "cl@ve#rara")
    url = conexion.url_postgres()
    assert url is not None
    assert "[YOUR-PASSWORD]" not in url
    assert "cl%40ve%23rara" in url  # @ y # codificados


def test_url_postgres_sin_configuracion_da_none(monkeypatch, tmp_path):
    monkeypatch.delenv("POSTGRES_URL", raising=False)
    monkeypatch.setattr(conexion, "SECRETS", tmp_path / "no_existe.toml")
    assert conexion.url_postgres() is None


def test_url_postgres_normaliza_prefijo_postgres(monkeypatch):
    monkeypatch.setenv("POSTGRES_URL", "postgres://u:pass@host/db")
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    url = conexion.url_postgres()
    assert url.startswith("postgresql://")


def test_diagnostico_sin_secrets_explica_que_falta(monkeypatch, tmp_path):
    monkeypatch.delenv("POSTGRES_URL", raising=False)
    monkeypatch.setattr(conexion, "SECRETS", tmp_path / "no_existe.toml")
    mensaje = conexion.diagnostico()
    assert mensaje is not None
    assert "secrets.toml" in mensaje


def test_diagnostico_todo_listo_da_none(monkeypatch):
    monkeypatch.setenv("POSTGRES_URL", "postgresql://u:pass@host/db")
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    assert conexion.diagnostico() is None
```

- [ ] **Step 2: Correr la prueba y verificar que falla**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_conexion.py -v
```

Esperado: FAIL con `ModuleNotFoundError: No module named 'conexion'`

- [ ] **Step 3: Implementar**

Crear `conexion.py`:

```python
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
```

Crear `.streamlit/secrets.toml.ejemplo`:

```toml
[conexion]
postgres_url = "postgresql://postgres.xxxxx:[YOUR-PASSWORD]@aws-0-xx-xxxx-1.pooler.supabase.com:5432/postgres"
password = "PEGA_AQUI"
```

- [ ] **Step 4: Correr las pruebas y verificar que pasan**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_conexion.py -v
```

Esperado: 7 passed

- [ ] **Step 5: Agregar SQLAlchemy y el driver de Postgres**

Crear `requirements.txt`:

```
sqlalchemy>=2.0
psycopg[binary]>=3.1
```

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

- [ ] **Step 6: Commit**

```bash
git add conexion.py .streamlit/secrets.toml.ejemplo tests/test_conexion.py requirements.txt
git commit -m "feat: conexión a Postgres desde secretos propios del proyecto"
```

---

### Task 2: Motor de base de datos cacheado y esquema idempotente

El `Engine` de SQLAlchemy y la verificación de esquema se cachean por
proceso — crear uno nuevo o reinspeccionar el catálogo en cada llamada es
lo que hacía inusable al proyecto de referencia en la nube.

**Files:**
- Create: `db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `conexion.url_postgres`
- Produces:
  - `engine(db_path=None) -> Engine` — cacheado por ruta/URL
  - `es_nube(eng: Engine) -> bool`
  - `etiqueta(eng: Engine) -> str`
  - `ejecutar(eng, sql: str, params=None)` — ejecuta y confirma
  - `consultar(eng, sql: str, params=None) -> list`
  - `escalar(eng, sql: str, params=None)`
  - `ensure_schema(eng: Engine) -> None` — cacheado por `Engine`, idempotente.
    Crea `usuarios`, `marcas`, `terminos_busqueda`, `ofertas`, `snapshots` y
    `oferta_analisis`. Las columnas de `ofertas` son fijas desde ahora
    (mismo conjunto que produce JobSpy + las fuentes propias del proyecto
    de referencia); el plan de Recolección las llena, no las define.

- [ ] **Step 1: Escribir la prueba que falla**

Crear `tests/test_db.py`:

```python
# -*- coding: utf-8 -*-
"""El esquema debe crearse igual en SQLite (local) y en Postgres (nube).
Se prueba contra SQLite temporal; el SQL usado es portable."""
from sqlalchemy import inspect

import db


def test_engine_local_es_sqlite(tmp_path):
    assert not db.es_nube(db.engine(tmp_path / "x.db"))


def test_engine_reusa_el_mismo_objeto_para_la_misma_ruta(tmp_path):
    """Antes cada llamada a engine() abría una conexión nueva desde cero
    (TCP+TLS) incluso con la misma ruta en el mismo proceso — eso
    multiplicaba la latencia de cada operación cruzando de región hacia
    Supabase. Debe reusar el Engine."""
    a = db.engine(tmp_path / "x.db")
    b = db.engine(tmp_path / "x.db")
    assert a is b


def test_engine_rutas_distintas_dan_motores_distintos(tmp_path):
    a = db.engine(tmp_path / "a.db")
    b = db.engine(tmp_path / "b.db")
    assert a is not b


def test_ensure_schema_crea_todas_las_tablas(tmp_path):
    eng = db.engine(tmp_path / "test.db")
    db.ensure_schema(eng)
    tablas = set(inspect(eng).get_table_names())
    assert {"usuarios", "marcas", "terminos_busqueda", "ofertas",
            "snapshots", "oferta_analisis"} <= tablas


def test_ensure_schema_es_idempotente(tmp_path):
    eng = db.engine(tmp_path / "test.db")
    db.ensure_schema(eng)
    db.ensure_schema(eng)  # segunda corrida no debe fallar


def test_ejecutar_consultar_escalar(tmp_path):
    eng = db.engine(tmp_path / "test.db")
    db.ejecutar(eng, "CREATE TABLE t (x TEXT)")
    db.ejecutar(eng, "INSERT INTO t VALUES (:v)", {"v": "hola"})
    assert db.escalar(eng, "SELECT x FROM t") == "hola"
    assert db.consultar(eng, "SELECT x FROM t") == [("hola",)]
```

- [ ] **Step 2: Correr la prueba y verificar que falla**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_db.py -v
```

Esperado: FAIL con `ModuleNotFoundError: No module named 'db'`

- [ ] **Step 3: Implementar**

Crear `db.py`:

```python
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

from sqlalchemy import create_engine, inspect, text
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
    with _ESQUEMA_LOCK:
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
```

- [ ] **Step 4: Correr las pruebas y verificar que pasan**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_db.py -v
```

Esperado: 6 passed

- [ ] **Step 5: Commit**

```bash
git add db.py tests/test_db.py
git commit -m "feat: motor de base de datos cacheado y esquema idempotente"
```

---

### Task 3: Usuarios

Guarda y recupera el perfil de cada persona como JSON — la misma
estructura que ya consume `motor.puntaje.Perfil`, solo que vive en una fila
en vez de en un archivo.

**Files:**
- Modify: `db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `engine`, `ensure_schema`, `ejecutar`, `consultar`
- Produces:
  - `upsert_usuario(eng, usuario_id: str, perfil_json: str, creado_en: str) -> None`
  - `cargar_usuario(eng, usuario_id: str) -> dict | None` — `{"id", "perfil_json", "creado_en"}`

- [ ] **Step 1: Escribir la prueba que falla**

Agregar a `tests/test_db.py`:

```python
def test_upsert_usuario_crea_y_actualiza(tmp_path):
    eng = db.engine(tmp_path / "u.db")
    db.ensure_schema(eng)
    db.upsert_usuario(eng, "ana@x.cl", '{"cargos_buscados": ["cajero"]}',
                      "2026-07-30")
    fila = db.cargar_usuario(eng, "ana@x.cl")
    assert fila["perfil_json"] == '{"cargos_buscados": ["cajero"]}'
    assert fila["creado_en"] == "2026-07-30"

    db.upsert_usuario(eng, "ana@x.cl", '{"cargos_buscados": ["guardia"]}',
                      "2026-08-01")
    fila = db.cargar_usuario(eng, "ana@x.cl")
    assert fila["perfil_json"] == '{"cargos_buscados": ["guardia"]}'
    assert fila["creado_en"] == "2026-07-30"  # no se pisa al actualizar
    assert db.escalar(eng, "SELECT COUNT(*) FROM usuarios") == 1  # sin duplicar


def test_cargar_usuario_inexistente_da_none(tmp_path):
    eng = db.engine(tmp_path / "u2.db")
    db.ensure_schema(eng)
    assert db.cargar_usuario(eng, "no-existe@x.cl") is None
```

- [ ] **Step 2: Correr la prueba y verificar que falla**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_db.py -k usuario -v
```

Esperado: FAIL con `AttributeError: module 'db' has no attribute 'upsert_usuario'`

- [ ] **Step 3: Implementar**

Agregar a `db.py` (al final del archivo):

```python
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
```

- [ ] **Step 4: Correr las pruebas y verificar que pasan**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_db.py -v
```

Esperado: 8 passed

- [ ] **Step 5: Commit**

```bash
git add db.py tests/test_db.py
git commit -m "feat: upsert y carga de usuarios"
```

---

### Task 4: Marcas por usuario

Cada persona tiene sus propias marcas (⭐📨✔) sobre las mismas ofertas
compartidas. Esta es la tarea con más riesgo de fuga de privacidad entre
usuarios — la prueba de aislamiento es obligatoria, no opcional.

**Files:**
- Modify: `db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `engine`, `ensure_schema`, `es_nube`, `ejecutar`, `consultar`,
  `CAMPOS_MARCA`
- Produces:
  - `upsert_marca(eng, usuario_id: str, job_url: str, campo: str, valor: bool, fecha: str) -> None`
  - `cargar_marcas(eng, usuario_id: str) -> dict[str, dict]` — `job_url ->
    {"revisada", "favorita", "postulada", "fecha"}`, solo las del usuario
    pedido

- [ ] **Step 1: Escribir la prueba que falla**

Agregar a `tests/test_db.py`:

```python
def test_upsert_marca_crea_y_actualiza(tmp_path):
    eng = db.engine(tmp_path / "m.db")
    db.ensure_schema(eng)
    db.upsert_marca(eng, "ana@x.cl", "http://x/1", "favorita", True,
                    "2026-07-30")
    marcas = db.cargar_marcas(eng, "ana@x.cl")
    assert marcas["http://x/1"]["favorita"] == 1

    db.upsert_marca(eng, "ana@x.cl", "http://x/1", "postulada", True,
                    "2026-07-30")
    marcas = db.cargar_marcas(eng, "ana@x.cl")
    assert marcas["http://x/1"]["favorita"] == 1    # no pisa la marca anterior
    assert marcas["http://x/1"]["postulada"] == 1

    db.upsert_marca(eng, "ana@x.cl", "http://x/1", "favorita", False,
                    "2026-07-31")
    marcas = db.cargar_marcas(eng, "ana@x.cl")
    assert marcas["http://x/1"]["favorita"] == 0
    assert db.escalar(eng, "SELECT COUNT(*) FROM marcas") == 1  # sin duplicar


def test_upsert_marca_rechaza_campo_invalido(tmp_path):
    eng = db.engine(tmp_path / "m2.db")
    db.ensure_schema(eng)
    try:
        db.upsert_marca(eng, "ana@x.cl", "http://x/1",
                        "borrar; DROP TABLE marcas", True, "x")
        assert False, "debió rechazar el campo"
    except ValueError:
        pass


def test_marcas_de_un_usuario_no_se_filtran_a_otro(tmp_path):
    # Requisito explícito del spec: privacidad entre usuarios.
    eng = db.engine(tmp_path / "m3.db")
    db.ensure_schema(eng)
    db.upsert_marca(eng, "ana@x.cl", "http://x/1", "favorita", True,
                    "2026-07-30")
    db.upsert_marca(eng, "beto@x.cl", "http://x/2", "postulada", True,
                    "2026-07-30")

    marcas_ana = db.cargar_marcas(eng, "ana@x.cl")
    marcas_beto = db.cargar_marcas(eng, "beto@x.cl")

    assert list(marcas_ana) == ["http://x/1"]
    assert list(marcas_beto) == ["http://x/2"]


def test_dos_usuarios_pueden_marcar_la_misma_oferta_distinto(tmp_path):
    eng = db.engine(tmp_path / "m4.db")
    db.ensure_schema(eng)
    db.upsert_marca(eng, "ana@x.cl", "http://x/1", "favorita", True,
                    "2026-07-30")
    db.upsert_marca(eng, "beto@x.cl", "http://x/1", "favorita", False,
                    "2026-07-30")

    assert db.cargar_marcas(eng, "ana@x.cl")["http://x/1"]["favorita"] == 1
    assert db.cargar_marcas(eng, "beto@x.cl")["http://x/1"]["favorita"] == 0
```

- [ ] **Step 2: Correr la prueba y verificar que falla**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_db.py -k marca -v
```

Esperado: FAIL con `AttributeError: module 'db' has no attribute 'upsert_marca'`

- [ ] **Step 3: Implementar**

Agregar a `db.py`:

```python
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
```

- [ ] **Step 4: Correr las pruebas y verificar que pasan**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_db.py -v
```

Esperado: 12 passed

- [ ] **Step 5: Commit**

```bash
git add db.py tests/test_db.py
git commit -m "feat: marcas por usuario, con prueba de aislamiento entre usuarios"
```

---

### Task 5: Términos de búsqueda

La lista de búsquedas vive en la base, no en el código. Esta tarea
construye las operaciones sobre `terminos_busqueda`: agregar un término
nuevo, registrar el resultado de una corrida, y devolver los términos en
orden de prioridad para la próxima corrida (sin ejecutar el scraping en
sí — eso es un plan aparte).

**Files:**
- Modify: `db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `engine`, `ensure_schema`, `ejecutar`, `consultar`
- Produces:
  - `agregar_termino(eng, termino: str, origen: str, agregado_en: str) -> None`
    — `origen` es `"base"` o `"usuario"`; no hace nada si el término ya existe
  - `registrar_corrida_termino(eng, termino: str, ofertas_encontradas: int, fecha: str) -> None`
  - `terminos_pendientes(eng, limite: int | None = None, ahora: str | None = None) -> list[str]`
    — `ahora` es un ISO-8601 opcional para pruebas deterministas (por
    defecto usa la hora actual). Orden de prioridad: (1) términos de
    usuario nunca corridos, (2) términos base nunca corridos, (3) el
    resto, primero los que devolvieron ofertas la última vez y luego los
    estériles, y dentro de cada grupo del que hace más tiempo se corrió al
    que hace menos. Excluye términos corridos en las últimas 24 horas
    (`_HORAS_MIN_ENTRE_CORRIDAS`, provisional).

- [ ] **Step 1: Escribir la prueba que falla**

Agregar a `tests/test_db.py`:

```python
def test_agregar_termino_no_duplica(tmp_path):
    eng = db.engine(tmp_path / "t.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "cajero", "base", "2026-07-30T00:00:00")
    db.agregar_termino(eng, "cajero", "usuario", "2026-08-01T00:00:00")
    assert db.escalar(eng, "SELECT COUNT(*) FROM terminos_busqueda") == 1
    assert db.escalar(
        eng, "SELECT origen FROM terminos_busqueda WHERE termino = 'cajero'"
    ) == "base"  # el segundo agregar_termino no pisa el origen original


def test_registrar_corrida_actualiza_termino_existente(tmp_path):
    eng = db.engine(tmp_path / "t2.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "cajero", "base", "2026-07-30T00:00:00")
    db.registrar_corrida_termino(eng, "cajero", 12, "2026-08-01T10:00:00")
    fila = db.consultar(
        eng, "SELECT ultima_corrida, ofertas_ultimas FROM terminos_busqueda"
             " WHERE termino = 'cajero'")[0]
    assert tuple(fila) == ("2026-08-01T10:00:00", 12)


def test_terminos_pendientes_prioriza_usuario_nunca_corrido(tmp_path):
    eng = db.engine(tmp_path / "t3.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "cajero", "base", "2026-07-01T00:00:00")
    db.agregar_termino(eng, "soldador", "usuario", "2026-08-01T00:00:00")
    pendientes = db.terminos_pendientes(eng)
    assert pendientes[0] == "soldador"


def test_terminos_pendientes_excluye_corridos_hace_poco(tmp_path):
    eng = db.engine(tmp_path / "t4.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "cajero", "base", "2026-07-01T00:00:00")
    db.registrar_corrida_termino(eng, "cajero", 5, "2026-08-01T09:00:00")
    # "ahora" es 2 horas después de la corrida: no debe reaparecer
    pendientes = db.terminos_pendientes(eng, ahora="2026-08-01T11:00:00")
    assert "cajero" not in pendientes


def test_terminos_pendientes_reaparece_pasadas_24_horas(tmp_path):
    eng = db.engine(tmp_path / "t5.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "cajero", "base", "2026-07-01T00:00:00")
    db.registrar_corrida_termino(eng, "cajero", 5, "2026-08-01T09:00:00")
    pendientes = db.terminos_pendientes(eng, ahora="2026-08-02T10:00:00")
    assert "cajero" in pendientes


def test_terminos_pendientes_respeta_el_limite(tmp_path):
    eng = db.engine(tmp_path / "t6.db")
    db.ensure_schema(eng)
    for i in range(5):
        db.agregar_termino(eng, f"termino{i}", "base", "2026-07-01T00:00:00")
    assert len(db.terminos_pendientes(eng, limite=2)) == 2


def test_terminos_pendientes_despriorizar_esteriles(tmp_path):
    # Requisito del spec: "se despriorizan los términos que llevan
    # corridas sin devolver nada" — un término sin resultados la última
    # vez debe quedar después de uno con resultados, aunque su corrida
    # anterior sea más antigua.
    eng = db.engine(tmp_path / "t7.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "con_resultados", "base", "2026-07-01T00:00:00")
    db.registrar_corrida_termino(eng, "con_resultados", 10,
                                 "2026-07-25T00:00:00")  # corrida reciente
    db.agregar_termino(eng, "esteril", "base", "2026-07-01T00:00:00")
    db.registrar_corrida_termino(eng, "esteril", 0,
                                 "2026-07-01T00:00:00")  # corrida antigua

    pendientes = db.terminos_pendientes(eng, ahora="2026-08-05T00:00:00")
    assert pendientes.index("con_resultados") < pendientes.index("esteril")
```

- [ ] **Step 2: Correr la prueba y verificar que falla**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_db.py -k termino -v
```

Esperado: FAIL con `AttributeError: module 'db' has no attribute 'agregar_termino'`

- [ ] **Step 3: Implementar**

Agregar a `db.py` (al inicio del archivo, junto a las otras constantes):

```python
# Un término corrido hace menos de esto no vuelve a proponerse: evita
# volver a scrapear lo que ya se buscó recién. PROVISIONAL: calibrar
# contra la duración real de una corrida completa cuando exista el
# pipeline de recolección.
_HORAS_MIN_ENTRE_CORRIDAS = 24
```

Agregar al final de `db.py`:

```python
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
    from datetime import datetime, timedelta

    ahora_dt = (datetime.fromisoformat(ahora) if ahora
                else datetime.utcnow())
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
```

- [ ] **Step 4: Correr las pruebas y verificar que pasan**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_db.py -v
```

Esperado: 19 passed

- [ ] **Step 5: Commit**

```bash
git add db.py tests/test_db.py
git commit -m "feat: términos de búsqueda con prioridad y recencia"
```

---

### Task 6: Ofertas y análisis genérico

Guarda las ofertas recolectadas (compartidas entre todos los usuarios) y su
análisis genérico. Ninguna columna de `oferta_analisis` puede depender de
un perfil concreto — ese fue el error del proyecto de referencia que este
proyecto existe para no repetir.

**Files:**
- Modify: `db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `engine`, `ensure_schema`, `es_nube`, `ejecutar`, `consultar`
- Produces:
  - `upsert_ofertas(eng, filas: list[dict], columnas: list[str]) -> int` —
    inserta ignorando duplicados por `job_url`, devuelve cuántas quedaron
    insertadas
  - `upsert_oferta_analisis(eng, filas: list[dict]) -> None` — reemplaza el
    análisis de cada oferta, atómico
  - `cargar_ofertas(eng) -> list[dict]` — ofertas con su análisis, join por
    `job_url`

- [ ] **Step 1: Escribir la prueba que falla**

Agregar a `tests/test_db.py`:

```python
def test_upsert_ofertas_ignora_duplicados(tmp_path):
    eng = db.engine(tmp_path / "o.db")
    db.ensure_schema(eng)  # ensure_schema ya crea la tabla `ofertas`
    filas = [{"job_url": "http://x/1", "title": "Cajero", "company": "A",
              "site": "trabajando", "scrape_date": "2026-07-30"}]
    insertadas = db.upsert_ofertas(eng, filas, list(filas[0]))
    assert insertadas == 1
    insertadas_de_nuevo = db.upsert_ofertas(eng, filas, list(filas[0]))
    assert insertadas_de_nuevo == 0
    assert db.escalar(eng, "SELECT COUNT(*) FROM ofertas") == 1


def test_upsert_oferta_analisis_no_guarda_columnas_prohibidas(tmp_path):
    # No debe existir forma de guardar match/cargo_no_afin/electrico/detalle
    # — son dependientes de perfil, y esta tabla es genérica.
    eng = db.engine(tmp_path / "o2.db")
    db.ensure_schema(eng)
    columnas = {c["name"] for c in
                __import__("sqlalchemy").inspect(eng).get_columns("oferta_analisis")}
    prohibidas = {"match", "cargo_no_afin", "electrico", "detalle"}
    assert columnas.isdisjoint(prohibidas)


def test_upsert_oferta_analisis_reemplaza_atomico(tmp_path):
    eng = db.engine(tmp_path / "o3.db")
    db.ensure_schema(eng)
    filas = [{"job_url": "http://x/1", "habilidades": '["Excel"]',
              "areas": '["administracion"]', "region": "Metropolitana",
              "modalidad": "Presencial", "tipo_contrato": "Indefinido",
              "anios_experiencia_pedidos": 2, "ingles_excluyente": 0,
              "duplicada": 0, "vigencia_estimada": "2026-08-30",
              "analizado_en": "2026-07-30T10:00:00"}]
    db.upsert_oferta_analisis(eng, filas)
    fila = db.consultar(eng, "SELECT habilidades, region FROM oferta_analisis"
                             " WHERE job_url = 'http://x/1'")[0]
    assert tuple(fila) == ('["Excel"]', "Metropolitana")

    filas[0]["region"] = "Valparaíso"
    db.upsert_oferta_analisis(eng, filas)
    assert db.escalar(
        eng, "SELECT region FROM oferta_analisis WHERE job_url = 'http://x/1'"
    ) == "Valparaíso"
    assert db.escalar(eng, "SELECT COUNT(*) FROM oferta_analisis") == 1


def test_cargar_ofertas_hace_join_con_analisis(tmp_path):
    eng = db.engine(tmp_path / "o4.db")
    db.ensure_schema(eng)
    db.ejecutar(eng, "INSERT INTO ofertas (job_url, title, company, site,"
                     " scrape_date) VALUES ('http://x/1', 'Cajero', 'A',"
                     " 'trabajando', '2026-07-30')")
    db.upsert_oferta_analisis(eng, [{
        "job_url": "http://x/1", "habilidades": '[]', "areas": '[]',
        "region": "Metropolitana", "modalidad": "Presencial",
        "tipo_contrato": "Indefinido", "anios_experiencia_pedidos": None,
        "ingles_excluyente": 0, "duplicada": 0, "vigencia_estimada": None,
        "analizado_en": "2026-07-30T10:00:00"}])
    ofertas = db.cargar_ofertas(eng)
    assert len(ofertas) == 1
    assert ofertas[0]["job_url"] == "http://x/1"
    assert ofertas[0]["title"] == "Cajero"
    assert ofertas[0]["region"] == "Metropolitana"


def test_cargar_ofertas_sin_filas_da_lista_vacia(tmp_path):
    eng = db.engine(tmp_path / "o5.db")
    db.ensure_schema(eng)
    assert db.cargar_ofertas(eng) == []
```

- [ ] **Step 2: Correr la prueba y verificar que falla**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_db.py -k "ofertas or analisis" -v
```

Esperado: FAIL con `AttributeError: module 'db' has no attribute 'upsert_ofertas'`

- [ ] **Step 3: Implementar**

Agregar a `db.py`:

```python
def upsert_ofertas(eng: Engine, filas: list[dict], columnas: list[str]) -> int:
    """Inserta ofertas nuevas ignorando las que ya existan (mismo
    job_url), de forma atómica. Devuelve cuántas filas quedaron realmente
    insertadas."""
    if not filas:
        return 0
    cols = ", ".join(f'"{c}"' for c in columnas)
    vals = ", ".join(f":{c}" for c in columnas)
    with eng.begin() as con:
        res = con.execute(text(
            f"INSERT INTO ofertas ({cols}) VALUES ({vals})"
            " ON CONFLICT (job_url) DO NOTHING"
        ), filas)
        return res.rowcount if res.rowcount is not None else 0


def upsert_oferta_analisis(eng: Engine, filas: list[dict]) -> None:
    """Reemplaza el análisis genérico de cada oferta, en una única
    transacción: si algo falla a mitad de camino, todo se revierte y el
    análisis anterior queda intacto."""
    if not filas:
        return
    with eng.begin() as con:
        con.execute(text(
            "INSERT INTO oferta_analisis"
            " (job_url, habilidades, areas, region, modalidad,"
            " tipo_contrato, anios_experiencia_pedidos, ingles_excluyente,"
            " duplicada, vigencia_estimada, analizado_en)"
            " VALUES (:job_url, :habilidades, :areas, :region, :modalidad,"
            " :tipo_contrato, :anios_experiencia_pedidos, :ingles_excluyente,"
            " :duplicada, :vigencia_estimada, :analizado_en)"
            " ON CONFLICT (job_url) DO UPDATE SET"
            " habilidades = excluded.habilidades, areas = excluded.areas,"
            " region = excluded.region, modalidad = excluded.modalidad,"
            " tipo_contrato = excluded.tipo_contrato,"
            " anios_experiencia_pedidos = excluded.anios_experiencia_pedidos,"
            " ingles_excluyente = excluded.ingles_excluyente,"
            " duplicada = excluded.duplicada,"
            " vigencia_estimada = excluded.vigencia_estimada,"
            " analizado_en = excluded.analizado_en"
        ), filas)


def cargar_ofertas(eng: Engine) -> list[dict]:
    """Ofertas con su análisis genérico ya unido, listas para que una capa
    posterior calcule el puntaje por usuario con motor.puntaje.puntuar.
    Asume que `ensure_schema` ya corrió (la tabla `ofertas` existe siempre,
    aunque esté vacía)."""
    filas = consultar(eng, """
        SELECT o.job_url, o.title, o.company, o.site, o.scrape_date,
               a.habilidades, a.areas, a.region, a.modalidad,
               a.tipo_contrato, a.anios_experiencia_pedidos,
               a.ingles_excluyente, a.duplicada, a.vigencia_estimada
        FROM ofertas o
        LEFT JOIN oferta_analisis a ON a.job_url = o.job_url
    """)
    columnas = ["job_url", "title", "company", "site", "scrape_date",
                "habilidades", "areas", "region", "modalidad",
                "tipo_contrato", "anios_experiencia_pedidos",
                "ingles_excluyente", "duplicada", "vigencia_estimada"]
    return [dict(zip(columnas, fila)) for fila in filas]
```

- [ ] **Step 4: Correr las pruebas y verificar que pasan**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_db.py -v
```

Esperado: 24 passed

- [ ] **Step 5: Correr la suite completa del proyecto**

```powershell
.venv\Scripts\python.exe -m pytest tests -v
```

Esperado: 105 passed (74 del motor + 7 de conexión + 24 de db)

- [ ] **Step 6: Commit**

```bash
git add db.py tests/test_db.py
git commit -m "feat: ofertas y análisis genérico, con join listo para el motor"
```

---

## Al terminar

Queda una capa de datos completa y probada contra SQLite: esquema
idempotente, motor cacheado, y operaciones atómicas para usuarios, marcas
por usuario, términos de búsqueda y ofertas con su análisis genérico. Nada
de esto calcula un puntaje — eso lo hace `motor.puntaje.puntuar`, en una
capa posterior, sobre lo que devuelve `cargar_ofertas` combinado con el
`perfil_json` de `cargar_usuario`.

**Planes siguientes**, en orden (según el spec):

1. **Recolección** — fuentes de scraping, pipeline con presupuesto de
   tiempo (~45 min) que consume `terminos_pendientes` y llama
   `registrar_corrida_termino` y `upsert_ofertas`/`upsert_oferta_analisis`.
2. **App Streamlit** — pantalla de correo, formulario de perfil, pestañas
   (Ofertas para ti, Filtro avanzado, Tendencias, Empresas), marcas por
   usuario.
3. **Búsqueda en vivo** — scraping al registrarse con tope de 30 segundos.

## Pendiente de calibración

- `_HORAS_MIN_ENTRE_CORRIDAS = 24` en `db.py` es un punto de partida, no un
  valor medido. Ajustar según cuánto tarda realmente una corrida completa
  del pipeline de recolección (plan siguiente).
- Las columnas de `ofertas` (Task 2) se fijaron por adelantado, copiando el
  conjunto que produce JobSpy más las fuentes propias del proyecto de
  referencia (`site`, `search_term`, `title`, `company`, `location`,
  `date_posted`, `job_type`, `is_remote`, `min_amount`, `max_amount`,
  `currency`, `interval`, `description`, `scrape_date`, `last_seen`). El
  plan de Recolección puede necesitar agregar una columna si alguna fuente
  produce un atributo que no está en esta lista — no debería necesitar
  quitar ninguna.
