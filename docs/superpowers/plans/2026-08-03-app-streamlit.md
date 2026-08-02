# App Streamlit — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir la interfaz Streamlit — pantalla de correo, formulario
de perfil, y las cinco pestañas del spec — como primer consumidor real de
`db.cargar_ofertas`, `db.cargar_usuario` y `motor.puntaje.puntuar`, con el
match calculado al vuelo por usuario, nunca guardado.

**Architecture:** Dos capas, igual que el proyecto de referencia: `app_data.py`
(consultas y agregaciones testeables con pytest, sin `streamlit`) y `app.py`
(la interfaz misma, verificable solo corriendo `streamlit run`). La pieza
central y nueva es `app_data.puntuar_ofertas`: toma la lista de ofertas que
devuelve `db.cargar_ofertas` (compartida entre todos los usuarios) y el
`Perfil` de una persona, y calcula el puntaje de cada una con
`motor.puntaje.puntuar` en el momento — nada de esto se persiste.

**Tech Stack:** Streamlit, pandas y plotly como dependencias nuevas
(presentación tabular y gráficos — a diferencia de `motor/`, `db.py` y las
fuentes de recolección, que deliberadamente evitan `pandas`, acá sí tiene
sentido: es exactamente lo que `st.dataframe`/`st.multiselect` esperan).
pytest para `app_data.py`; `streamlit run` para verificar `app.py` a mano.

## Global Constraints

- **Proyecto independiente.** No importar, copiar ni depender de nada de
  `mapa-mercado-laboral`. Se lee como referencia para adaptar patrones
  probados (la capa `app_data`/`app` separada, el chequeo
  `es_seleccion_nueva`, el convenio de `key=` por pestaña) — nunca se copia
  lo específico de un perfil (el descarte de plástico, la pestaña Ing.
  Civil Química, el match precalculado y guardado).
- **El match se calcula al vuelo, nunca se guarda.** `oferta_analisis` ya
  guarda solo lo genérico (construido en un plan anterior); esta app agrega
  la última pieza — el puntaje por persona — en memoria, en cada carga de
  página, con `motor.puntaje.puntuar`.
- **Todo widget necesita `key=` único con prefijo por pestaña.** Streamlit
  ejecuta el código de todas las pestañas en cada rerun, no solo la
  visible — dos widgets con el mismo label y sin `key` explícito chocan
  (`DuplicateElementId`). Esto ya le costó dos veces al proyecto de
  referencia, y pytest no lo detecta: cada tarea que agregue una pestaña
  debe probarse con `streamlit run` antes de darse por terminada, no solo
  con la suite automática.
- **Identificación por correo, sin contraseña.** El `usuario_id` es
  literalmente el correo que la persona escribe — sin verificación, sin
  registro separado. La app no se difunde públicamente mientras sea así
  (ya documentado en el spec); este plan no cambia eso.
- **Fuera de alcance de este plan** (ya decidido en el spec): pestaña "Qué
  estudiar", "Ing. Civil Química", "Radar reclutadores", "Panorama" (KPIs
  agregados) — ninguna de las cinco pestañas del spec es esa. Subida de CV.
  Búsqueda en vivo al registrarse (plan aparte).
- **Nombres en español**, consistentes con el resto del proyecto.

---

## Estructura de archivos

```
buscador-empleo-personalizado/
├── app_data.py          consultas/agregaciones, sin streamlit — testeable
├── app.py                la interfaz Streamlit
├── requirements.txt       + streamlit, pandas, plotly
└── tests/
    └── test_app_data.py
```

`app_data.py` importa `db` y `motor` (texto, cargo, habilidades, atributos,
puntaje) — nunca `streamlit`. `app.py` importa `app_data`, `db`
(directamente solo para lo que `app_data` no envuelve) y `streamlit`. Nada
de `motor/`, `db.py` ni las fuentes de recolección importan nada de este
plan — la dependencia va en una sola dirección, de la app hacia el resto.

---

### Task 1: Perfil ↔ `motor.puntaje.Perfil`, y el puntaje al vuelo

La pieza central del plan: construir un `Perfil` desde lo guardado en
`usuarios`, y puntuar una lista de ofertas contra él.

**Files:**
- Create: `app_data.py`
- Test: `tests/test_app_data.py`

**Interfaces:**
- Consumes: `db.engine`, `db.ensure_schema`, `db.cargar_usuario`,
  `db.upsert_usuario`, `db.cargar_ofertas`, `motor.puntaje.Perfil`,
  `motor.puntaje.Aviso`, `motor.puntaje.puntuar`
- Produces:
  - `REGIONES_CHILE: list[str]` — las 16 regiones, para el formulario
  - `cargar_perfil(usuario_id: str, db_path=None) -> Perfil | None`
  - `guardar_perfil(usuario_id: str, perfil: Perfil, ahora: str, db_path=None) -> None`
  - `aviso_desde_oferta(oferta: dict) -> Aviso`
  - `puntuar_ofertas(ofertas: list[dict], perfil: Perfil) -> list[dict]` —
    cada fila de `ofertas` más `match`, `afinidad_cargo`, `ajustes`;
    ordenado por `match` descendente; solo las visibles

- [ ] **Step 1: Escribir la prueba que falla**

Crear `tests/test_app_data.py`:

```python
# -*- coding: utf-8 -*-
import app_data
import db
from motor.puntaje import Aviso, Perfil


def _oferta(**cambios):
    base = dict(job_url="http://x/1", title="Cajero", company="Super X",
                site="trabajando", scrape_date="2026-08-01",
                description="Se busca cajero con experiencia",
                habilidades="[]", areas='["Ventas y retail"]',
                region="Metropolitana", modalidad="Presencial",
                tipo_contrato="Indefinido", anios_experiencia_pedidos=None,
                ingles_excluyente=0, duplicada=0, vigencia_estimada=None)
    base.update(cambios)
    return base


def test_cargar_perfil_inexistente_da_none(tmp_path):
    eng = db.engine(tmp_path / "a.db")
    db.ensure_schema(eng)
    assert app_data.cargar_perfil("ana@x.cl", db_path=tmp_path / "a.db") is None


def test_guardar_y_cargar_perfil_hace_roundtrip(tmp_path):
    perfil = Perfil(cargos_buscados=["cajero"], habilidades=["Excel"],
                    anios_experiencia=2, region="Metropolitana",
                    acepta_remoto=False, evitar=["plástico"])
    app_data.guardar_perfil("ana@x.cl", perfil, "2026-08-03",
                            db_path=tmp_path / "b.db")
    cargado = app_data.cargar_perfil("ana@x.cl", db_path=tmp_path / "b.db")
    assert cargado == perfil


def test_guardar_perfil_no_pisa_creado_en_al_actualizar(tmp_path):
    p1 = Perfil(cargos_buscados=["cajero"])
    app_data.guardar_perfil("ana@x.cl", p1, "2026-08-01", db_path=tmp_path / "c.db")
    p2 = Perfil(cargos_buscados=["guardia"])
    app_data.guardar_perfil("ana@x.cl", p2, "2026-08-05", db_path=tmp_path / "c.db")
    eng = db.engine(tmp_path / "c.db")
    fila = db.cargar_usuario(eng, "ana@x.cl")
    assert fila["creado_en"] == "2026-08-01"
    assert app_data.cargar_perfil("ana@x.cl", db_path=tmp_path / "c.db") == p2


def test_aviso_desde_oferta_mapea_los_campos():
    oferta = _oferta(habilidades='["Excel", "Manejo de caja"]',
                     anios_experiencia_pedidos=2, ingles_excluyente=1)
    aviso = app_data.aviso_desde_oferta(oferta)
    assert aviso.titulo == "Cajero"
    assert aviso.texto == "Se busca cajero con experiencia"
    assert aviso.habilidades == ["Excel", "Manejo de caja"]
    assert aviso.region == "Metropolitana"
    assert aviso.modalidad == "Presencial"
    assert aviso.anios_pedidos == 2
    assert aviso.ingles_excluyente is True


def test_aviso_desde_oferta_sin_habilidades_no_crashea():
    oferta = _oferta(habilidades=None)
    aviso = app_data.aviso_desde_oferta(oferta)
    assert aviso.habilidades == []


def test_puntuar_ofertas_agrega_match_y_ordena():
    ofertas = [
        _oferta(job_url="http://x/1", title="Cajero"),  # calce perfecto
        _oferta(job_url="http://x/2", title="Ingeniero de Procesos"),  # sin relación
    ]
    perfil = Perfil(cargos_buscados=["cajero"])
    resultado = app_data.puntuar_ofertas(ofertas, perfil)
    assert len(resultado) == 1  # el sin relación queda oculto (afinidad baja)
    assert resultado[0]["job_url"] == "http://x/1"
    assert resultado[0]["match"] == 100


def test_puntuar_ofertas_respeta_evitar_del_perfil():
    ofertas = [_oferta(job_url="http://x/1", title="Cajero",
                       description="Fábrica de envases plásticos")]
    perfil = Perfil(cargos_buscados=["cajero"], evitar=["plástico"])
    assert app_data.puntuar_ofertas(ofertas, perfil) == []


def test_puntuar_ofertas_de_un_usuario_no_afecta_a_otro():
    ofertas = [_oferta(job_url="http://x/1", title="Cajero",
                       description="Fábrica de envases plásticos")]
    con_evitar = app_data.puntuar_ofertas(
        ofertas, Perfil(cargos_buscados=["cajero"], evitar=["plástico"]))
    sin_evitar = app_data.puntuar_ofertas(
        ofertas, Perfil(cargos_buscados=["cajero"]))
    assert con_evitar == []
    assert len(sin_evitar) == 1
```

- [ ] **Step 2: Correr la prueba y verificar que falla**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_app_data.py -v
```

Esperado: FAIL con `ModuleNotFoundError: No module named 'app_data'`

- [ ] **Step 3: Implementar**

Crear `app_data.py`:

```python
# -*- coding: utf-8 -*-
"""Consultas y agregaciones para la app — sin dependencia de Streamlit,
para poder probarlas con pytest sin levantar el runtime de la interfaz."""
import json

import db
from motor.puntaje import Aviso, Perfil, puntuar

REGIONES_CHILE = [
    "Arica y Parinacota", "Tarapacá", "Antofagasta", "Atacama", "Coquimbo",
    "Valparaíso", "Metropolitana", "O'Higgins", "Maule", "Ñuble", "Biobío",
    "La Araucanía", "Los Ríos", "Los Lagos", "Aysén", "Magallanes",
]


def cargar_perfil(usuario_id: str, db_path=None) -> Perfil | None:
    eng = db.engine(db_path)
    db.ensure_schema(eng)
    fila = db.cargar_usuario(eng, usuario_id)
    if fila is None:
        return None
    datos = json.loads(fila["perfil_json"])
    return Perfil(
        cargos_buscados=datos.get("cargos_buscados", []),
        habilidades=datos.get("habilidades", []),
        anios_experiencia=datos.get("anios_experiencia"),
        region=datos.get("region"),
        acepta_remoto=datos.get("acepta_remoto", True),
        evitar=datos.get("evitar", []),
    )


def guardar_perfil(usuario_id: str, perfil: Perfil, ahora: str,
                   db_path=None) -> None:
    eng = db.engine(db_path)
    db.ensure_schema(eng)
    datos = {
        "cargos_buscados": perfil.cargos_buscados,
        "habilidades": perfil.habilidades,
        "anios_experiencia": perfil.anios_experiencia,
        "region": perfil.region,
        "acepta_remoto": perfil.acepta_remoto,
        "evitar": perfil.evitar,
    }
    db.upsert_usuario(eng, usuario_id, json.dumps(datos, ensure_ascii=False), ahora)


def aviso_desde_oferta(oferta: dict) -> Aviso:
    habilidades = json.loads(oferta["habilidades"]) if oferta.get("habilidades") else []
    return Aviso(
        titulo=oferta.get("title") or "",
        texto=oferta.get("description") or "",
        habilidades=habilidades,
        region=oferta.get("region") or "Sin especificar",
        modalidad=oferta.get("modalidad") or "Sin especificar",
        anios_pedidos=oferta.get("anios_experiencia_pedidos"),
        ingles_excluyente=bool(oferta.get("ingles_excluyente")),
    )


def puntuar_ofertas(ofertas: list[dict], perfil: Perfil) -> list[dict]:
    """Puntúa cada oferta contra `perfil` al vuelo — nada de esto se
    guarda. Devuelve solo las visibles (afinidad de cargo por encima del
    umbral), ordenadas de mayor a menor match."""
    resultado = []
    for oferta in ofertas:
        aviso = aviso_desde_oferta(oferta)
        puntaje = puntuar(aviso, perfil)
        if not puntaje.visible:
            continue
        fila = dict(oferta)
        fila["match"] = puntaje.total
        fila["afinidad_cargo"] = puntaje.afinidad_cargo
        fila["ajustes"] = puntaje.ajustes
        resultado.append(fila)
    resultado.sort(key=lambda f: f["match"], reverse=True)
    return resultado
```

- [ ] **Step 4: Correr las pruebas y verificar que pasan**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_app_data.py -v
```

Esperado: 8 passed

- [ ] **Step 5: Agregar Streamlit, pandas y plotly a las dependencias**

Agregar a `requirements.txt`:

```
streamlit>=1.49
pandas>=2.2
plotly>=5.20
```

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

- [ ] **Step 6: Commit**

```bash
git add app_data.py tests/test_app_data.py requirements.txt
git commit -m "feat: perfil <-> motor.puntaje.Perfil y puntaje al vuelo"
```

---

### Task 2: Marcas por usuario y selección estable en tablas

Envoltorios delgados sobre lo que `db.py` ya construyó (por usuario), más
el chequeo que evita que Streamlit vuelva a marcar "revisada" una fila solo
porque la tabla se reordenó entre recargas — un bug real del proyecto de
referencia, ya resuelto ahí, que se porta acá antes de que vuelva a pasar.

**Files:**
- Modify: `app_data.py`
- Test: `tests/test_app_data.py`

**Interfaces:**
- Consumes: `db.engine`, `db.ensure_schema`, `db.upsert_marca`,
  `db.cargar_marcas`, `db.CAMPOS_MARCA`
- Produces:
  - `marcas_de(usuario_id: str, db_path=None) -> dict` — igual forma que
    `db.cargar_marcas`
  - `set_marca(usuario_id: str, job_url: str, campo: str, valor: bool, ahora: str, db_path=None) -> None`
  - `es_seleccion_nueva(estado_sesion: dict, key: str, valor: str) -> bool`

- [ ] **Step 1: Escribir la prueba que falla**

Agregar a `tests/test_app_data.py`:

```python
def test_set_marca_y_marcas_de_hacen_roundtrip(tmp_path):
    app_data.set_marca("ana@x.cl", "http://x/1", "favorita", True,
                       "2026-08-03", db_path=tmp_path / "m.db")
    marcas = app_data.marcas_de("ana@x.cl", db_path=tmp_path / "m.db")
    assert marcas["http://x/1"]["favorita"] == 1


def test_marcas_de_un_usuario_no_incluye_las_de_otro(tmp_path):
    app_data.set_marca("ana@x.cl", "http://x/1", "favorita", True,
                       "2026-08-03", db_path=tmp_path / "m2.db")
    app_data.set_marca("beto@x.cl", "http://x/2", "postulada", True,
                       "2026-08-03", db_path=tmp_path / "m2.db")
    assert list(app_data.marcas_de("ana@x.cl", db_path=tmp_path / "m2.db")) == ["http://x/1"]


def test_set_marca_rechaza_campo_invalido(tmp_path):
    try:
        app_data.set_marca("ana@x.cl", "http://x/1", "campo_invalido", True,
                           "2026-08-03", db_path=tmp_path / "m3.db")
        assert False, "debió rechazar el campo"
    except ValueError:
        pass


def test_es_seleccion_nueva_la_primera_vez():
    estado = {}
    assert app_data.es_seleccion_nueva(estado, "tabla1", "http://x/1") is True


def test_es_seleccion_nueva_no_se_repite_para_la_misma_url():
    estado = {}
    app_data.es_seleccion_nueva(estado, "tabla1", "http://x/1")
    assert app_data.es_seleccion_nueva(estado, "tabla1", "http://x/1") is False


def test_es_seleccion_nueva_vuelve_a_ser_true_con_otra_url():
    estado = {}
    app_data.es_seleccion_nueva(estado, "tabla1", "http://x/1")
    assert app_data.es_seleccion_nueva(estado, "tabla1", "http://x/2") is True


def test_es_seleccion_nueva_no_cruza_entre_tablas_distintas():
    estado = {}
    app_data.es_seleccion_nueva(estado, "tabla1", "http://x/1")
    # la misma url, pero en OTRA tabla (key distinta): sigue siendo nueva
    assert app_data.es_seleccion_nueva(estado, "tabla2", "http://x/1") is True
```

- [ ] **Step 2: Correr la prueba y verificar que falla**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_app_data.py -k "marca or seleccion_nueva" -v
```

Esperado: FAIL con `AttributeError: module 'app_data' has no attribute 'marcas_de'`

- [ ] **Step 3: Implementar**

Agregar a `app_data.py` (al final del archivo):

```python
def marcas_de(usuario_id: str, db_path=None) -> dict:
    eng = db.engine(db_path)
    db.ensure_schema(eng)
    return db.cargar_marcas(eng, usuario_id)


def set_marca(usuario_id: str, job_url: str, campo: str, valor: bool,
             ahora: str, db_path=None) -> None:
    if campo not in db.CAMPOS_MARCA:
        raise ValueError(f"campo inválido: {campo}")
    eng = db.engine(db_path)
    db.ensure_schema(eng)
    db.upsert_marca(eng, usuario_id, job_url, campo, valor, ahora)


def es_seleccion_nueva(estado_sesion: dict, key: str, valor: str) -> bool:
    """¿Este valor es una selección genuinamente nueva en esta tabla?

    Streamlit recuerda "la fila en tal posición" seleccionada entre
    recargas (por `key`), pero la lista se reordena todo el tiempo (nuevo
    match, nuevos datos) — así que esa misma posición puede apuntar a OTRA
    oferta en la siguiente recarga. Sin este chequeo, cada recarga volvía a
    marcar como revisada lo que fuera que hubiera en esa fila en ese
    momento, sin que la persona hiciera click. Por eso solo se marca la
    primera vez que ESTE valor en particular queda seleccionado.

    Función pura sobre un dict (en producción, st.session_state) para
    poder probarla sin levantar el runtime de Streamlit."""
    clave = f"_ultima_vista_{key}"
    es_nueva = estado_sesion.get(clave) != valor
    estado_sesion[clave] = valor
    return es_nueva
```

- [ ] **Step 4: Correr las pruebas y verificar que pasan**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_app_data.py -v
```

Esperado: 15 passed

- [ ] **Step 5: Commit**

```bash
git add app_data.py tests/test_app_data.py
git commit -m "feat: marcas por usuario y chequeo de selección estable en tablas"
```

---

### Task 3: Agregaciones genéricas — áreas, habilidades, tendencias, empresas

Las agregaciones para "Tendencias" y "Empresas". Genéricas: nada de
descarte de rubro ni de `areas_objetivo` fijas a un perfil — quien mira la
pestaña ve el mercado completo, no un recorte.

**Files:**
- Modify: `app_data.py`
- Test: `tests/test_app_data.py`

**Interfaces:**
- Consumes: `pandas`
- Produces:
  - `a_dataframe(ofertas: list[dict]) -> pandas.DataFrame` — decodifica
    `habilidades`/`areas` (JSON) a listas Python
  - `conteo_areas(df) -> pandas.Series`
  - `conteo_habilidades(df) -> pandas.DataFrame` — columnas `habilidad`,
    `ofertas`, `pct`
  - `tendencias_por_fecha(df) -> dict | None` — `{"habilidades": DataFrame,
    "areas": DataFrame}` agrupado por `scrape_date`; `None` si hay una sola
    fecha de captura (nada que mostrar como tendencia todavía)
  - `radar_empresas(df) -> pandas.DataFrame` — columnas `empresa`,
    `ofertas`, `areas`, `top_habilidades`
  - `sin_duplicadas(ofertas: list[dict]) -> list[dict]` y
    `estado_vigencia(oferta: dict) -> str` — agregadas en la revisión
    final de rama, ver la sección del final

- [ ] **Step 1: Escribir la prueba que falla**

Agregar a `tests/test_app_data.py`:

```python
def test_a_dataframe_decodifica_habilidades_y_areas():
    ofertas = [_oferta(habilidades='["Excel"]', areas='["Ventas y retail"]')]
    df = app_data.a_dataframe(ofertas)
    assert df.iloc[0]["habilidades"] == ["Excel"]
    assert df.iloc[0]["areas"] == ["Ventas y retail"]


def test_a_dataframe_con_lista_vacia_da_dataframe_vacio():
    df = app_data.a_dataframe([])
    assert len(df) == 0


def test_conteo_areas_cuenta_por_area():
    ofertas = [
        _oferta(job_url="http://x/1", areas='["Ventas y retail"]'),
        _oferta(job_url="http://x/2", areas='["Ventas y retail", "Administración"]'),
    ]
    conteo = app_data.conteo_areas(app_data.a_dataframe(ofertas))
    assert conteo["Ventas y retail"] == 2
    assert conteo["Administración"] == 1


def test_conteo_habilidades_calcula_porcentaje():
    ofertas = [
        _oferta(job_url="http://x/1", habilidades='["Excel"]'),
        _oferta(job_url="http://x/2", habilidades='[]'),
    ]
    tabla = app_data.conteo_habilidades(app_data.a_dataframe(ofertas))
    fila = tabla[tabla["habilidad"] == "Excel"].iloc[0]
    assert fila["ofertas"] == 1
    assert fila["pct"] == 50.0


def test_conteo_habilidades_sin_ninguna_da_tabla_vacia():
    ofertas = [_oferta(job_url="http://x/1", habilidades="[]")]
    tabla = app_data.conteo_habilidades(app_data.a_dataframe(ofertas))
    assert len(tabla) == 0
    assert list(tabla.columns) == ["habilidad", "ofertas", "pct"]


def test_tendencias_por_fecha_none_con_una_sola_fecha():
    ofertas = [_oferta(job_url="http://x/1", scrape_date="2026-08-01")]
    assert app_data.tendencias_por_fecha(app_data.a_dataframe(ofertas)) is None


def test_tendencias_por_fecha_con_varias_fechas():
    ofertas = [
        _oferta(job_url="http://x/1", scrape_date="2026-08-01",
               habilidades='["Excel"]'),
        _oferta(job_url="http://x/2", scrape_date="2026-08-02",
               habilidades='["Excel"]'),
    ]
    resultado = app_data.tendencias_por_fecha(app_data.a_dataframe(ofertas))
    assert resultado is not None
    assert set(resultado["habilidades"]["scrape_date"]) == {"2026-08-01", "2026-08-02"}


def test_radar_empresas_agrupa_por_empresa():
    ofertas = [
        _oferta(job_url="http://x/1", company="Super X",
               habilidades='["Excel"]', areas='["Ventas y retail"]'),
        _oferta(job_url="http://x/2", company="Super X",
               habilidades='["Manejo de caja"]', areas='["Ventas y retail"]'),
    ]
    tabla = app_data.radar_empresas(app_data.a_dataframe(ofertas))
    fila = tabla[tabla["empresa"] == "Super X"].iloc[0]
    assert fila["ofertas"] == 2
    assert "Excel" in fila["top_habilidades"]
```

- [ ] **Step 2: Correr la prueba y verificar que falla**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_app_data.py -k "dataframe or conteo or tendencias or radar" -v
```

Esperado: FAIL con `AttributeError: module 'app_data' has no attribute 'a_dataframe'`

- [ ] **Step 3: Implementar**

Agregar el import al inicio de `app_data.py` (junto a los ya existentes):

```python
import pandas as pd
```

Agregar al final de `app_data.py`:

```python
def _lista_json(valor) -> list:
    # Chequea el tipo y no la verdad del valor: pandas convierte los NULL
    # del LEFT JOIN de db.cargar_ofertas (oferta recolectada pero todavía
    # no analizada) en NaN, y NaN es truthy.
    if not isinstance(valor, str) or not valor:
        return []
    return json.loads(valor)


def a_dataframe(ofertas: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(ofertas)
    if df.empty:
        return df
    df["habilidades"] = df["habilidades"].map(_lista_json)
    df["areas"] = df["areas"].map(_lista_json)
    return df


def conteo_areas(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype="int64")
    return df["areas"].explode().value_counts()


_COLUMNAS_CONTEO_HABILIDADES = {
    "habilidad": "object", "ofertas": "int64", "pct": "float64"}


def conteo_habilidades(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        conteo = pd.Series(dtype="int64")
    else:
        conteo = df["habilidades"].explode().dropna().value_counts()
    if conteo.empty:
        return pd.DataFrame({c: pd.Series(dtype=t)
                             for c, t in _COLUMNAS_CONTEO_HABILIDADES.items()})
    out = conteo.rename_axis("habilidad").reset_index(name="ofertas")
    out["pct"] = (100 * out["ofertas"] / max(1, len(df))).round(1)
    return out


def tendencias_por_fecha(df: pd.DataFrame):
    """None si hay menos de 2 fechas de captura distintas — aún no hay
    tendencia real que mostrar, solo una foto."""
    if df.empty or df["scrape_date"].nunique() < 2:
        return None
    hab = (df.explode("habilidades").dropna(subset=["habilidades"])
           .groupby(["scrape_date", "habilidades"]).size()
           .rename("ofertas").reset_index()
           .rename(columns={"habilidades": "habilidad"}))
    areas = (df.explode("areas").dropna(subset=["areas"])
             .groupby(["scrape_date", "areas"]).size()
             .rename("ofertas").reset_index()
             .rename(columns={"areas": "area"}))
    return {"habilidades": hab, "areas": areas}


def radar_empresas(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["empresa", "ofertas", "areas", "top_habilidades"])
    g = df.groupby("company")
    out = pd.DataFrame({
        "ofertas": g.size(),
        "areas": g["areas"].apply(
            lambda s: ", ".join(sorted({a for row in s for a in row}))),
        "top_habilidades": g["habilidades"].apply(
            lambda s: ", ".join(pd.Series(
                [h for row in s for h in row]).value_counts().head(5).index)),
    })
    return (out.sort_values("ofertas", ascending=False)
            .rename_axis("empresa").reset_index())
```

- [ ] **Step 4: Correr las pruebas y verificar que pasan**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_app_data.py -v
```

Esperado: 23 passed

- [ ] **Step 5: Correr la suite completa**

```powershell
.venv\Scripts\python.exe -m pytest tests -v
```

Esperado: 195 passed (172 de antes + 23 de app_data)

- [ ] **Step 6: Commit**

```bash
git add app_data.py tests/test_app_data.py
git commit -m "feat: agregaciones genéricas para Tendencias y Empresas"
```

---

### Task 4: Pantalla de correo y formulario de perfil

El punto de entrada de la app: pedir el correo, cargar el perfil si ya
existe, o mostrar el formulario si es la primera vez.

**Files:**
- Create: `app.py`

**Interfaces:**
- Consumes: `app_data.cargar_perfil`, `app_data.guardar_perfil`,
  `app_data.REGIONES_CHILE`, `motor.puntaje.Perfil`, `motor.habilidades.CATALOGO`
- Produces:
  - `pantalla_correo() -> str | None` — el correo escrito, o `None` si
    todavía no se envió el formulario
  - `formulario_perfil(perfil_actual: Perfil | None) -> Perfil | None` —
    el perfil armado si se guardó en esta corrida, si no `None`
  - `main()`

Sin pasos de TDD para este archivo: es interfaz de Streamlit, no probable
con pytest de forma significativa (`st.text_input`, `st.form`, etc. no se
ejecutan fuera del runtime de Streamlit). La verificación es manual, con
`streamlit run`, como se detalla en el Step 3.

- [ ] **Step 1: Crear `app.py` con la pantalla de correo y el formulario**

```python
# -*- coding: utf-8 -*-
"""Buscador de empleo personalizado — interfaz Streamlit.

Ejecutar: .venv\\Scripts\\python.exe -m streamlit run app.py
"""
from datetime import datetime, timezone

import streamlit as st

import app_data
from motor.habilidades import CATALOGO
from motor.puntaje import Perfil

st.set_page_config(page_title="Buscador de empleo — Chile",
                   page_icon="🔎", layout="wide")

HABILIDADES_DISPONIBLES = sorted(CATALOGO)


def _ahora() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def pantalla_correo() -> str | None:
    st.title("🔎 Buscador de empleo personalizado")
    st.write("Escribe tu correo para entrar. Si ya armaste tu perfil antes, "
             "lo recuperamos; si no, te lo pedimos ahora.")
    correo = st.text_input("Correo", key="login_correo",
                           placeholder="tu@correo.cl")
    if st.button("Entrar", key="login_entrar") and correo.strip():
        return correo.strip().lower()
    return None


def formulario_perfil(perfil_actual: Perfil | None) -> Perfil | None:
    st.subheader("Tu perfil")
    st.caption("Esto define qué ofertas te mostramos. Podés volver a "
               "editarlo cuando quieras.")
    valores = perfil_actual or Perfil(cargos_buscados=[])
    with st.form("form_perfil", clear_on_submit=False):
        cargos_texto = st.text_area(
            "Cargos que buscás (uno por línea)", key="perfil_cargos",
            value="\n".join(valores.cargos_buscados),
            placeholder="cajero\nasistente contable")
        habilidades = st.multiselect(
            "Habilidades que tenés (opcional)", HABILIDADES_DISPONIBLES,
            key="perfil_habilidades", default=valores.habilidades)
        c1, c2 = st.columns(2)
        anios = c1.number_input(
            "Años de experiencia", key="perfil_anios",
            min_value=0, max_value=50,
            value=valores.anios_experiencia or 0)
        region = c2.selectbox(
            "Región", ["(sin preferencia)"] + app_data.REGIONES_CHILE,
            key="perfil_region",
            index=(["(sin preferencia)"] + app_data.REGIONES_CHILE)
                  .index(valores.region) if valores.region else 0)
        acepta_remoto = st.checkbox(
            "Acepto trabajo remoto", key="perfil_remoto",
            value=valores.acepta_remoto)
        evitar_texto = st.text_area(
            "Qué querés evitar (uno por línea, opcional)",
            key="perfil_evitar", value="\n".join(valores.evitar),
            placeholder="plástico\ncall center")
        enviado = st.form_submit_button("Guardar perfil")

    if not enviado:
        return None

    cargos = [c.strip() for c in cargos_texto.splitlines() if c.strip()]
    if not cargos:
        st.error("Escribí al menos un cargo que estés buscando.")
        return None

    evitar = [e.strip() for e in evitar_texto.splitlines() if e.strip()]
    nuevo = Perfil(
        cargos_buscados=cargos,
        habilidades=list(habilidades),
        # Siempre el valor tal cual está en la caja — un recién egresado
        # que escribe "0" quiere decir "cero años", no "no especificado".
        # `if anios else None` trataría 0 como falsy y lo guardaría como
        # None, con lo que motor.puntaje._queda_grande nunca penalizaría
        # avisos que piden mucha más experiencia que la que la persona
        # realmente declaró.
        anios_experiencia=int(anios),
        region=None if region == "(sin preferencia)" else region,
        acepta_remoto=acepta_remoto,
        evitar=evitar,
    )
    app_data.guardar_perfil(st.session_state["usuario_id"], nuevo, _ahora())
    st.success("Perfil guardado.")
    return nuevo


def main():
    if "usuario_id" not in st.session_state:
        correo = pantalla_correo()
        if correo is None:
            return
        st.session_state["usuario_id"] = correo
        st.rerun()

    usuario_id = st.session_state["usuario_id"]
    st.sidebar.write(f"Sesión: {usuario_id}")
    if st.sidebar.button("Cerrar sesión", key="sidebar_logout"):
        del st.session_state["usuario_id"]
        st.rerun()

    perfil = app_data.cargar_perfil(usuario_id)
    if perfil is None or st.sidebar.checkbox("Editar perfil", key="sidebar_editar"):
        nuevo = formulario_perfil(perfil)
        if nuevo is None:
            if perfil is None:
                return  # primera vez, sin perfil todavía: no hay nada más que mostrar
        else:
            perfil = nuevo


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add app.py
git commit -m "feat: pantalla de correo y formulario de perfil"
```

- [ ] **Step 3: Verificar a mano con streamlit run**

```powershell
.venv\Scripts\python.exe -m streamlit run app.py
```

Comprobar en el navegador:
- Entrar con un correo nuevo muestra el formulario de perfil (no hay
  perfil guardado todavía).
- Escribir al menos un cargo y guardar no tira error.
- Recargar la página y volver a entrar con el mismo correo carga el perfil
  ya guardado (no vuelve a pedir el formulario).
- "Editar perfil" en la barra lateral vuelve a mostrar el formulario con
  los valores ya guardados precargados.
- Dejar "Años de experiencia" en 0 explícitamente y guardar, después
  volver a abrir "Editar perfil": debe seguir mostrando 0, no volver al
  placeholder vacío — confirma que 0 se guarda como cero real, no como
  "sin especificar".
- Ningún error de `DuplicateElementId` en la consola del navegador ni en
  la terminal.

---

### Task 5: Pestaña "Ofertas para ti"

La pestaña principal: las ofertas puntuadas contra el perfil de la
persona, en tarjetas, con marcas.

**Files:**
- Modify: `app.py`

**Interfaces:**
- Consumes: `app_data.puntuar_ofertas`, `app_data.marcas_de`,
  `app_data.set_marca`, `app_data.es_seleccion_nueva`, `db.cargar_ofertas`,
  `db.engine`, `db.ensure_schema`
- Produces:
  - `tab_ofertas(perfil: Perfil, usuario_id: str)`

Todos los `key=` de esta pestaña llevan el prefijo `of_`.

- [ ] **Step 1: Agregar la pestaña a `app.py`**

Agregar antes de `def main():`:

```python
ESTADOS_VIGENCIA = {"activa": "🟢 Activa", "por_vencer": "🟠 Por vencer",
                    "probablemente_cerrada": "⚫ Prob. cerrada",
                    "sin_fecha": "⚪ Sin fecha"}


@st.cache_data(ttl=300)
def _ofertas_crudas(db_path=None):
    import db
    eng = db.engine(db_path)
    db.ensure_schema(eng)
    return db.cargar_ofertas(eng)


def _tarjeta_oferta(oferta: dict, marcas: dict, usuario_id: str, prefijo: str):
    url = oferta["job_url"]
    mk = marcas.get(url, {"revisada": 0, "favorita": 0, "postulada": 0})
    with st.container(border=True):
        st.markdown(f"**{oferta['title']}** — {oferta['company']}")
        st.caption(f"{oferta.get('region') or 'Sin especificar'} · "
                   f"{oferta.get('modalidad') or 'Sin especificar'} · "
                   f"Match: {oferta['match']} · "
                   f"{ESTADOS_VIGENCIA[app_data.estado_vigencia(oferta)]}")
        c1, c2, c3 = st.columns(3)
        favorita = c1.checkbox("⭐ Favorita", value=bool(mk["favorita"]),
                               key=f"{prefijo}_fav_{url}")
        postulada = c2.checkbox("📨 Postulada", value=bool(mk["postulada"]),
                                key=f"{prefijo}_post_{url}")
        revisada = c3.checkbox("✔ Revisada", value=bool(mk["revisada"]),
                               key=f"{prefijo}_rev_{url}")
        if favorita != bool(mk["favorita"]):
            app_data.set_marca(usuario_id, url, "favorita", favorita, _ahora())
        if postulada != bool(mk["postulada"]):
            app_data.set_marca(usuario_id, url, "postulada", postulada, _ahora())
        if revisada != bool(mk["revisada"]):
            app_data.set_marca(usuario_id, url, "revisada", revisada, _ahora())
        with st.expander("Ver descripción"):
            st.write(oferta.get("description") or "(sin descripción)")
            st.caption(f"Fuente: {oferta['site']} · {url}")


def tab_ofertas(perfil, usuario_id: str):
    crudas = _ofertas_crudas()
    if not crudas:
        st.info("Todavía no hay ofertas recolectadas. Vuelve a intentarlo "
                "más tarde.")
        return
    # sin_duplicadas: el mismo aviso republicado en otra fuente aparecería
    # dos veces seguidas, con match idéntico (Hallazgo 2 de la revisión
    # final de rama).
    puntuadas = app_data.puntuar_ofertas(app_data.sin_duplicadas(crudas), perfil)
    if not puntuadas:
        st.info("No encontramos ofertas que calcen con los cargos que "
                "buscás todavía. Probá agregar otro cargo en tu perfil.")
        return
    st.write(f"{len(puntuadas)} ofertas para vos, ordenadas por match.")
    marcas = app_data.marcas_de(usuario_id)
    for oferta in puntuadas[:50]:
        _tarjeta_oferta(oferta, marcas, usuario_id, "of")
```

Modificar `main()` para agregar la pestaña una vez que hay perfil:

```python
def main():
    if "usuario_id" not in st.session_state:
        correo = pantalla_correo()
        if correo is None:
            return
        st.session_state["usuario_id"] = correo
        st.rerun()

    usuario_id = st.session_state["usuario_id"]
    st.sidebar.write(f"Sesión: {usuario_id}")
    if st.sidebar.button("Cerrar sesión", key="sidebar_logout"):
        del st.session_state["usuario_id"]
        st.rerun()

    perfil = app_data.cargar_perfil(usuario_id)
    if perfil is None or st.sidebar.checkbox("Editar perfil", key="sidebar_editar"):
        nuevo = formulario_perfil(perfil)
        if nuevo is None:
            if perfil is None:
                return
        else:
            perfil = nuevo

    if perfil is None:
        return

    (t1,) = st.tabs(["🎯 Ofertas para ti"])
    with t1:
        tab_ofertas(perfil, usuario_id)
```

- [ ] **Step 2: Commit**

```bash
git add app.py
git commit -m "feat: pestaña Ofertas para ti"
```

- [ ] **Step 3: Verificar a mano con streamlit run**

```powershell
.venv\Scripts\python.exe -m streamlit run app.py
```

Comprobar:
- Con un perfil cuyo cargo buscado calza con alguna oferta real (o
  insertada a mano en la base de pruebas), la pestaña muestra tarjetas
  ordenadas de mayor a menor match.
- Marcar "⭐ Favorita" en una tarjeta y recargar la página: la marca sigue
  activa.
- Con un cargo que no calza con nada, se ve el mensaje de "no encontramos
  ofertas", no un error.
- Sin ninguna oferta en la base, se ve el mensaje de "todavía no hay
  ofertas", no un error ni una pantalla en blanco.

---

### Task 6: Pestaña "Filtro avanzado"

Control total sobre cada criterio, independiente del match del perfil.
Esta es exactamente la pestaña que causó el bug de `DuplicateElementId` en
el proyecto de referencia — todo widget lleva `key="av_..."` desde el
primer commit, no como parche después.

**Files:**
- Modify: `app.py`

**Interfaces:**
- Consumes: `app_data.a_dataframe`, `db.cargar_ofertas`

- [ ] **Step 1: Agregar la pestaña a `app.py`**

Agregar antes de `def main():`:

```python
def tab_filtro_avanzado(perfil, usuario_id: str):
    crudas = _ofertas_crudas()
    if not crudas:
        st.info("Todavía no hay ofertas recolectadas.")
        return
    puntuadas = app_data.puntuar_ofertas(crudas, perfil)
    df = app_data.a_dataframe(puntuadas)
    if df.empty:
        st.info("No hay ofertas que calcen con tu perfil todavía.")
        return

    st.caption("Filtro con control total sobre cada criterio — a "
               "diferencia de «Ofertas para ti», acá podés ver también lo "
               "que normalmente queda afuera (duplicadas, con inglés "
               "excluyente, etc.).")

    c1, c2 = st.columns(2)
    match_min, match_max = c1.slider("Rango de match", 0, 100, (0, 100),
                                     key="av_match")
    texto_libre = c2.text_input(
        "Buscar texto (cargo, empresa o descripción)",
        key="av_texto", placeholder="Ej: turno tarde")

    c1, c2, c3, c4, c5 = st.columns(5)
    areas_sel = c1.multiselect(
        "Áreas", sorted(df["areas"].explode().dropna().unique()),
        key="av_areas")
    regiones_sel = c2.multiselect(
        "Región", sorted(df["region"].dropna().unique()), key="av_regiones")
    modalidades_sel = c3.multiselect(
        "Modalidad", sorted(df["modalidad"].dropna().unique()),
        key="av_modalidades")
    contratos_sel = c4.multiselect(
        "Contrato", sorted(df["tipo_contrato"].dropna().unique()),
        key="av_contratos")
    fuentes_sel = c5.multiselect(
        "Fuente", sorted(df["site"].dropna().unique()), key="av_fuentes")

    c1, c2 = st.columns(2)
    incluir_duplicadas = c1.checkbox("Incluir duplicadas", False, key="av_dup")
    incluir_ingles = c2.checkbox("Incluir con inglés excluyente", True,
                                 key="av_ingles")

    sel = df.copy()
    if not incluir_duplicadas:
        sel = sel[sel["duplicada"] != 1]
    if not incluir_ingles:
        sel = sel[sel["ingles_excluyente"] != 1]
    sel = sel[sel["match"].between(match_min, match_max)]
    if texto_libre.strip():
        import re
        from motor.texto import normalizar
        t = normalizar(texto_libre)
        campo = (sel["title"].fillna("").map(normalizar) + " "
                 + sel["company"].fillna("").map(normalizar) + " "
                 + sel["description"].fillna("").map(normalizar))
        sel = sel[campo.str.contains(re.escape(t))]
    if areas_sel:
        objetivo = set(areas_sel)
        sel = sel[sel["areas"].map(lambda a: bool(objetivo & set(a)))]
    if regiones_sel:
        sel = sel[sel["region"].isin(regiones_sel)]
    if modalidades_sel:
        sel = sel[sel["modalidad"].isin(modalidades_sel)]
    if contratos_sel:
        sel = sel[sel["tipo_contrato"].isin(contratos_sel)]
    if fuentes_sel:
        sel = sel[sel["site"].isin(fuentes_sel)]

    st.write(f"{len(sel)} ofertas con estos filtros.")
    st.dataframe(
        sel[["title", "company", "region", "modalidad", "tipo_contrato",
             "match", "site"]].sort_values("match", ascending=False),
        width="stretch", key="av_tabla")
```

Actualizar `st.tabs(...)` en `main()`:

```python
    (t1, t2) = st.tabs(["🎯 Ofertas para ti", "🔬 Filtro avanzado"])
    with t1:
        tab_ofertas(perfil, usuario_id)
    with t2:
        tab_filtro_avanzado(perfil, usuario_id)
```

- [ ] **Step 2: Commit**

```bash
git add app.py
git commit -m "feat: pestaña Filtro avanzado"
```

- [ ] **Step 3: Verificar a mano con streamlit run**

```powershell
.venv\Scripts\python.exe -m streamlit run app.py
```

Comprobar, con ambas pestañas visibles en el navegador (esto es
justamente lo que reveló el bug original — cambiar de pestaña y volver):
- Cambiar cualquier filtro en "Filtro avanzado" no tira
  `DuplicateElementId` ni ningún otro error en la consola.
- Ir a "Ofertas para ti", volver a "Filtro avanzado": los filtros
  mantienen su valor.
- Activar "Incluir duplicadas" muestra más filas que con el filtro
  desactivado (si hay duplicadas en los datos de prueba).
- El buscador de texto libre encuentra una oferta por una palabra de su
  descripción, no solo del título.

---

### Task 7: Pestañas "Tendencias", "Empresas", "Acerca de los datos" y cierre

Las últimas dos pestañas de datos agregados, más una pestaña informativa, y
el cableado final de `main()`.

**Files:**
- Modify: `app.py`

**Interfaces:**
- Consumes: `app_data.a_dataframe`, `app_data.tendencias_por_fecha`,
  `app_data.radar_empresas`, `db.cargar_ofertas`, `plotly.express`

- [ ] **Step 1: Agregar las pestañas a `app.py`**

Agregar el import al inicio del archivo:

```python
import plotly.express as px
```

Agregar antes de `def main():`:

```python
def _foto_del_momento(df):
    """Áreas y habilidades más pedidas en la única corrida que hay."""
    areas = app_data.conteo_areas(df)
    if not areas.empty:
        st.plotly_chart(
            px.bar(x=areas.values, y=areas.index, orientation="h",
                   labels={"x": "ofertas", "y": "área"},
                   title="Ofertas por área"),
            width="stretch", key="td_foto_areas")
    habilidades = app_data.conteo_habilidades(df)
    if habilidades.empty:
        st.caption("Ninguna de las ofertas capturadas menciona habilidades "
                   "del catálogo todavía.")
        return
    st.plotly_chart(
        px.bar(habilidades.head(10), x="ofertas", y="habilidad",
               orientation="h", title="Top 10 habilidades pedidas"),
        width="stretch", key="td_foto_habilidades")
    st.caption("«pct» es el porcentaje de las ofertas capturadas que pide "
               "esa habilidad.")
    st.dataframe(habilidades, width="stretch", key="td_foto_tabla")


def tab_tendencias(perfil, usuario_id: str):
    # sin_duplicadas: contar dos veces el mismo aviso republicado infla la
    # serie de un área o una habilidad sin que haya más demanda detrás.
    crudas = app_data.sin_duplicadas(_ofertas_crudas())
    df = app_data.a_dataframe(crudas)
    if df.empty:
        st.info("Todavía no hay ofertas recolectadas.")
        return
    tendencias = app_data.tendencias_por_fecha(df)
    if tendencias is None:
        # Con una sola corrida no hay serie, pero sí hay algo que mirar.
        # Sin esto la pestaña queda vacía justamente el día 1.
        st.info("Todavía hay una sola fecha de captura, así que no hay "
                "tendencia en el tiempo para mostrar — por ahora, la foto "
                "de lo que se está pidiendo hoy.")
        _foto_del_momento(df)
        return
    st.plotly_chart(
        px.line(tendencias["areas"], x="scrape_date", y="ofertas",
               color="area", title="Ofertas por área en el tiempo"),
        width="stretch", key="td_areas")
    top_habilidades = (tendencias["habilidades"].groupby("habilidad")["ofertas"]
                       .sum().nlargest(10).index)
    hab_top = tendencias["habilidades"][
        tendencias["habilidades"]["habilidad"].isin(top_habilidades)]
    st.plotly_chart(
        px.line(hab_top, x="scrape_date", y="ofertas", color="habilidad",
               title="Top 10 habilidades pedidas en el tiempo"),
        width="stretch", key="td_habilidades")


def tab_empresas(perfil, usuario_id: str):
    crudas = app_data.sin_duplicadas(_ofertas_crudas())
    df = app_data.a_dataframe(crudas)
    if df.empty:
        st.info("Todavía no hay ofertas recolectadas.")
        return
    tabla = app_data.radar_empresas(df)
    st.write(f"{len(tabla)} empresas con avisos publicados.")
    st.dataframe(tabla, width="stretch", key="em_tabla")


def tab_acerca(perfil, usuario_id: str):
    crudas = _ofertas_crudas()
    unicas = len(app_data.sin_duplicadas(crudas))
    st.write(f"**Ofertas en la base:** {len(crudas)}")
    repetidas = len(crudas) - unicas
    if repetidas:
        cuantas = ("Una es" if repetidas == 1
                   else f"{repetidas} son")
        st.caption(f"{cuantas} el mismo aviso publicado en más de una "
                   f"fuente: el resto de las pestañas trabaja con las "
                   f"{unicas} ofertas distintas.")
    if crudas:
        ultima = max((o.get("scrape_date") or "" for o in crudas), default="")
        st.write(f"**Última corrida con datos:** {ultima or 'sin registro'}")
    st.write("**Fuentes:** Get on Board, Computrabajo, Trabajando.cl, "
             "Laborum.cl.")
    st.write("El puntaje de cada oferta se calcula al momento de cargar la "
             "página, contra tu perfil — no se guarda en ningún lado ni se "
             "comparte entre usuarios.")
    st.caption("Mientras el ingreso sea solo por correo, evitá compartir "
               "esta app con desconocidos: cualquiera que escriba tu "
               "correo puede ver tu perfil y tus marcas.")
```

Reemplazar `main()` completo:

```python
def main():
    if "usuario_id" not in st.session_state:
        correo = pantalla_correo()
        if correo is None:
            return
        st.session_state["usuario_id"] = correo
        st.rerun()

    usuario_id = st.session_state["usuario_id"]
    st.sidebar.write(f"Sesión: {usuario_id}")
    if st.sidebar.button("Cerrar sesión", key="sidebar_logout"):
        del st.session_state["usuario_id"]
        st.rerun()

    perfil = app_data.cargar_perfil(usuario_id)
    if perfil is None or st.sidebar.checkbox("Editar perfil", key="sidebar_editar"):
        nuevo = formulario_perfil(perfil)
        if nuevo is None:
            if perfil is None:
                return
        else:
            perfil = nuevo

    if perfil is None:
        return

    t1, t2, t3, t4, t5 = st.tabs(
        ["🎯 Ofertas para ti", "🔬 Filtro avanzado", "📈 Tendencias",
         "🏢 Empresas", "ℹ️ Acerca de los datos"])
    with t1:
        tab_ofertas(perfil, usuario_id)
    with t2:
        tab_filtro_avanzado(perfil, usuario_id)
    with t3:
        tab_tendencias(perfil, usuario_id)
    with t4:
        tab_empresas(perfil, usuario_id)
    with t5:
        tab_acerca(perfil, usuario_id)
```

- [ ] **Step 2: Correr la suite completa del proyecto** (nada de Streamlit
  en la suite automática, pero confirma que `app_data.py` sigue sano)

```powershell
.venv\Scripts\python.exe -m pytest tests -v
```

Esperado: 195 passed, sin regresiones

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: pestañas Tendencias, Empresas, Acerca de los datos y cierre de main()"
```

- [ ] **Step 4: Verificar a mano con streamlit run — las cinco pestañas juntas**

```powershell
.venv\Scripts\python.exe -m streamlit run app.py
```

Este es el chequeo final del plan — con las cinco pestañas coexistiendo,
que es justo el escenario donde aparece `DuplicateElementId` si algún
`key=` quedó repetido:

- Ninguna pestaña tira una excepción visible ni aparece en la consola del
  navegador al cambiar entre las cinco, en cualquier orden.
- Con solo una fecha de captura en los datos de prueba, "Tendencias"
  muestra el mensaje de "todavía hay una sola fecha", no un gráfico vacío
  ni un error.
- "Empresas" muestra una tabla con al menos una fila si hay ofertas en la
  base.
- "Acerca de los datos" muestra un conteo de ofertas coherente con lo que
  se ve en las otras pestañas.
- Redimensionar la ventana del navegador a un ancho angosto (viewport
  móvil, ~375px) no rompe el layout de ninguna pestaña de forma que oculte
  contenido o vuelva inaccesible un botón.
- "Cerrar sesión" en la barra lateral vuelve a la pantalla de correo, y
  volver a entrar con el mismo correo recupera el perfil guardado.

---

## Al terminar

Queda la interfaz completa: pantalla de correo, formulario de perfil, y
las cinco pestañas del spec, con el match calculado al vuelo por persona.
`app_data.py` es la única pieza con pruebas automáticas — `app.py` se
verifica corriendo la app de verdad, como pide el spec.

**Planes siguientes**, en orden (según el spec):

1. **Búsqueda en vivo al registrarse** — cuando el formulario de perfil
   guarda un cargo que la base no cubre (`app_data.puntuar_ofertas` da
   lista vacía para ese cargo), scrapear ese término en el momento con
   las cuatro fuentes ya construidas, tope de 30 segundos, resultados
   parciales.
2. **Despliegue** — GitHub Actions para correr `recolectar.py` en un
   horario fijo, y esta app en Streamlit Cloud. Este es también el momento
   de decidir si la app sigue siendo de identificación abierta por correo
   o si ya conviene agregar `st.login()` — el spec condiciona eso a tener
   usuarios reales pidiéndolo.
3. **Seed de la lista base de ~30 ocupaciones** (ya documentado como
   pendiente en el plan de Recolección) — sin esto, alguien que entra por
   primera vez sin un perfil que calce con nada ve la app vacía hasta que
   la búsqueda en vivo (plan 1) exista.

## Hallazgos de la revisión final de rama (2026-08-02)

Las siete tareas pasaron su revisión individual sin observaciones. La
revisión de toda la rama contra `main` —que es la que en los tres planes
anteriores encontró los bugs de verdad— encontró dos, ambos en el seam
entre la app y la capa de datos ya mergeada. Los bloques de código de
arriba ya están corregidos; esto queda como registro de por qué son así.

**Hallazgo 1 (crítico): una oferta recolectada pero todavía no analizada
tumbaba la página entera.** `db.cargar_ofertas` hace LEFT JOIN contra
`oferta_analisis`, así que esas ofertas llegan con todas las columnas de
análisis en NULL. pandas convierte esos `None` en `NaN`, y `NaN` es
truthy: `json.loads(s) if s else []` en `a_dataframe` le pasaba el `NaN`
a `json` y reventaba con `TypeError`. Como `main()` llama las pestañas en
secuencia, moría en "Filtro avanzado" y Tendencias, Empresas y Acerca ni
llegaban a renderizar. No es un caso de borde: `recolectar.py` inserta
ofertas dentro de su bucle (línea 75) y recién analiza al final (línea
88), así que ése es el estado normal durante toda una corrida, y el
permanente si la corrida se corta. `@st.cache_data(ttl=300)` además
congelaba el estado roto cinco minutos. Arreglado con `_lista_json`, que
chequea el tipo y no la verdad del valor.

**Hallazgo 2 (importante): la deduplicación no la consumía nadie.**
`analizar.py` calcula `duplicada` —y el plan de Recolección ya había
gastado una ronda de revisión en que respetara la región—, pero ninguna
pestaña lo miraba: "Ofertas para ti" mostraba el mismo aviso republicado
dos veces seguidas con match idéntico, y "Empresas" y "Tendencias" lo
contaban dos veces. Justo al revés de lo que promete el texto de "Filtro
avanzado". Medido en una base de prueba: 4 tarjetas en "Ofertas para ti"
contra 3 filas en "Filtro avanzado", sin explicación visible. Arreglado
con `sin_duplicadas`, que trata `duplicada IS NULL` como "todavía no se
sabe" y no como duplicada, para no esconder ofertas recién recolectadas.

**Dos piezas que el plan construyó y nunca cableó.** `vigencia_estimada`
se traía desde la base y `ESTADOS_VIGENCIA` estaba definido desde la Task
5, pero nada lo mostraba; y con una sola fecha de captura —el estado del
día 1— "Tendencias" no mostraba nada más que un mensaje, teniendo
`conteo_areas` y `conteo_habilidades` ya escritas y probadas desde la
Task 3. Ambas cableadas. Ojo con `vigencia_estimada`: lo guardado es el
JSON completo que devuelve `motor.atributos.vigencia`
(`{"dias_publicada", "dias_restantes_est", "estado"}`), no el estado
suelto — de ahí `estado_vigencia`, que lo decodifica y cae en
`"sin_fecha"` ante cualquier cosa ilegible.

`es_seleccion_nueva` quedó sin usar y así se queda: el diseño final usa
checkboxes por tarjeta, no selección de filas en una tabla, así que el
bug que esa función previene no existe en esta app. Si alguna pestaña
futura muestra una tabla con `on_select`, ahí sí se necesita.

La suite quedó en **202 pruebas** (195 heredadas + 7 de esta revisión).
`app.py` se verificó con `streamlit.testing.v1.AppTest`, que corre el
código real contra una base real sin navegador: base sana, base con
oferta sin analizar, base vacía, una y dos fechas de captura, los cuatro
estados de vigencia, y las cinco pestañas juntas sin `DuplicateElementId`.

**Sigue pendiente el chequeo visual en un navegador de verdad** (viewport
móvil ~375px, consola sin errores) — el navegador embebido de la sesión
tuvo una falla de compositing durante todo el trabajo. No es un defecto
conocido del código, es verificación que no se pudo hacer.

## Pendiente de calibración

- El límite de "50 ofertas visibles" en `tab_ofertas` (`puntuadas[:50]`)
  es arbitrario, para no renderizar cientos de tarjetas de una. Revisar
  con volumen real de datos — quizás conviene paginar en vez de cortar.
- `tendencias_por_fecha` agrupa por `scrape_date` porque `snapshots` (la
  tabla pensada para volumen por corrida) todavía no se escribe en
  ningún lado (pendiente ya anotado en el plan de Recolección). Cuando
  esa tabla exista, esta función puede sumar una serie de volumen total
  por fuente, como hacía el proyecto de referencia.
- No hay paginación ni límite en "Filtro avanzado" — con miles de ofertas
  en la base, `st.dataframe` sobre el DataFrame completo puede volverse
  lento. Revisar cuando haya datos reales de volumen.
