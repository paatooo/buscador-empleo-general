# Búsqueda en vivo al registrarse — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cuando un perfil recién guardado no calza con ninguna oferta ya
recolectada, scrapear los cargos de ese perfil en el momento (tope de 30
segundos, resultados parciales) en vez de dejar la app vacía hasta la
próxima corrida programada.

**Architecture:** Un módulo nuevo, `buscar_en_vivo.py`, con la misma
separación que el resto del proyecto — funciones puras sobre `Engine` +
listas de cargos, testeables con pytest mockeando `fetch_all` de las
cuatro fuentes (igual que `recolectar.py`/`test_recolectar.py`). Reusa
`db.upsert_ofertas`, `db.agregar_termino`, `db.registrar_corrida_termino`
tal cual, y suma dos piezas nuevas y pequeñas: `db.termino_reciente`
(encapsula el chequeo de 24h que ya usa `terminos_pendientes`, sin
exponer su constante privada a otro módulo) y `analizar.run_urls`
(análisis acotado a un set de URLs, para no reprocesar la tabla completa
dentro del presupuesto de 30s). `app.py` solo invoca `buscar_en_vivo.buscar`
desde `formulario_perfil` con una barra de progreso.

**Tech Stack:** Nada nuevo — mismas dependencias que ya tiene el
proyecto (`requests` vía las cuatro fuentes, `streamlit` para la barra de
progreso). pytest con `unittest.mock.patch` para todo lo testeable;
`streamlit run` para verificar el enganche en `app.py`.

## Global Constraints

- **El match nunca se guarda** — igual que siempre, `puntuar_ofertas` se
  sigue calculando al vuelo; la búsqueda en vivo solo agrega ofertas y su
  análisis genérico, nunca un puntaje.
- **Presupuesto de 30 segundos total**, no por cargo ni por fuente — con
  varios cargos sin cubrir, cada uno recibe menos tiempo, nunca se
  extiende el total.
- **Orden de fuentes por velocidad esperada**: Get on Board (API) →
  Trabajando → Laborum (sitemap) → Computrabajo (HTML paginado, la más
  lenta). Antes de empezar cada fuente se chequea el tiempo restante; si
  no alcanza, se salta esa fuente y las que quedan.
- **Reutilización con el mismo umbral de 24h** que ya usa
  `db.terminos_pendientes` (`db._HORAS_MIN_ENTRE_CORRIDAS`) — un cargo
  corrido hace menos de 24h, en vivo o programada, no se vuelve a
  scrapear.
- **Concurrencia: máximo 3 búsquedas en vivo simultáneas**, contador en
  memoria del proceso (`threading.Semaphore`, no hace falta coordinar
  entre procesos — Streamlit Cloud corre una sola instancia). La 4ta
  llamada no scrapea nada: el cargo queda registrado para la corrida
  programada, y el perfil se guarda igual — este guardarraíl nunca
  bloquea el guardado.
- **Un cargo donde ninguna fuente respondió no se registra como
  corrido** — mismo criterio que el fix de `recolectar.py` (commit
  `8203005`): si las cuatro fuentes fallan, el cargo queda pendiente para
  reintentar, no se descarta ni se marca estéril.
- **Caso vacío honesto**: si después del presupuesto sigue sin haber
  nada, se muestra "todavía no tenemos ofertas de X, las seguimos
  buscando" — nunca una lista con match bajo para simular resultados.
- **Nombres en español**, consistentes con el resto del proyecto.
- Spec de referencia:
  [`docs/superpowers/specs/2026-08-07-busqueda-en-vivo-design.md`](../specs/2026-08-07-busqueda-en-vivo-design.md).

---

## Estructura de archivos

```
buscador-empleo-personalizado/
├── db.py                 + termino_reciente
├── analizar.py            + run_urls (refactor interno de run())
├── buscar_en_vivo.py      nuevo — orquestador de búsqueda en vivo
├── app.py                 + enganche en formulario_perfil
└── tests/
    ├── test_db.py         + pruebas de termino_reciente
    ├── test_analizar.py   + pruebas de run_urls
    └── test_buscar_en_vivo.py   nuevo
```

`buscar_en_vivo.py` importa `db`, `analizar` y las cuatro `fuente_*` —
nunca `streamlit`. `app.py` importa `buscar_en_vivo` solo donde se usa
(mismo estilo que ya usa para `db` dentro de `_ofertas_crudas`).

---

### Task 1: `db.termino_reciente`

Encapsula el chequeo de 24h que ya hace `terminos_pendientes`, para que
`buscar_en_vivo.py` no tenga que leer la constante privada
`db._HORAS_MIN_ENTRE_CORRIDAS` desde otro módulo.

**Files:**
- Modify: `db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `db.consultar`, `db._HORAS_MIN_ENTRE_CORRIDAS` (interno)
- Produces: `termino_reciente(eng: Engine, termino: str, ahora: str) -> bool`

- [ ] **Step 1: Escribir la prueba que falla**

Agregar a `tests/test_db.py` (después de los tests de
`terminos_pendientes`):

```python
def test_termino_reciente_da_false_si_nunca_se_corrio(tmp_path):
    eng = db.engine(tmp_path / "tr1.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "cajero", "base", "2026-07-01T00:00:00")
    assert db.termino_reciente(eng, "cajero", "2026-08-01T00:00:00") is False


def test_termino_reciente_da_true_dentro_de_24_horas(tmp_path):
    eng = db.engine(tmp_path / "tr2.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "cajero", "base", "2026-07-01T00:00:00")
    db.registrar_corrida_termino(eng, "cajero", 5, "2026-08-01T09:00:00")
    assert db.termino_reciente(eng, "cajero", "2026-08-01T11:00:00") is True


def test_termino_reciente_da_false_pasadas_24_horas(tmp_path):
    eng = db.engine(tmp_path / "tr3.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "cajero", "base", "2026-07-01T00:00:00")
    db.registrar_corrida_termino(eng, "cajero", 5, "2026-08-01T09:00:00")
    assert db.termino_reciente(eng, "cajero", "2026-08-02T10:00:00") is False


def test_termino_reciente_da_false_si_el_termino_no_existe(tmp_path):
    eng = db.engine(tmp_path / "tr4.db")
    db.ensure_schema(eng)
    assert db.termino_reciente(eng, "inexistente", "2026-08-01T00:00:00") is False
```

- [ ] **Step 2: Correr la prueba y verificar que falla**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_db.py -k termino_reciente -v
```

Esperado: FAIL con `AttributeError: module 'db' has no attribute 'termino_reciente'`

- [ ] **Step 3: Implementar**

Agregar a `db.py`, después de `terminos_pendientes` (línea ~274):

```python
def termino_reciente(eng: Engine, termino: str, ahora: str) -> bool:
    """True si `termino` se corrió (en vivo o programada) hace menos de
    `_HORAS_MIN_ENTRE_CORRIDAS` horas. Mismo umbral y misma comparación
    lexicográfica de cadenas ISO que ya usa `terminos_pendientes` — un
    término nunca corrido da False."""
    from datetime import datetime, timedelta

    fila = consultar(eng, "SELECT ultima_corrida FROM terminos_busqueda"
                          " WHERE termino = :t", {"t": termino})
    if not fila or fila[0][0] is None:
        return False
    corte = (datetime.fromisoformat(ahora)
             - timedelta(hours=_HORAS_MIN_ENTRE_CORRIDAS)).isoformat()
    return fila[0][0] >= corte
```

- [ ] **Step 4: Correr las pruebas y verificar que pasan**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_db.py -v
```

Esperado: todas pasan (las de antes + las 4 nuevas)

- [ ] **Step 5: Commit**

```bash
git add db.py tests/test_db.py
git commit -m "feat: db.termino_reciente para reutilizacion de busqueda en vivo"
```

---

### Task 2: `analizar.run_urls`

Análisis acotado a un set de URLs — la deduplicación sigue mirando la
tabla completa (necesita ver lo ya existente para no perderse un
duplicado contra una oferta vieja), pero el cálculo pesado por oferta
(habilidades, áreas, texto) y el `upsert_oferta_analisis` solo corren
para las URLs pedidas. Requiere refactorizar `run()` en piezas
compartidas — su comportamiento externo no cambia (las pruebas ya
existentes de `run()` deben seguir pasando tal cual).

**Files:**
- Modify: `analizar.py`
- Test: `tests/test_analizar.py`

**Interfaces:**
- Consumes: `db.consultar`, `db.upsert_oferta_analisis`, `db.ensure_schema`,
  `motor.atributos.*`, `motor.areas.clasificar`, `motor.habilidades.detectar`,
  `motor.texto.normalizar`
- Produces: `run_urls(eng, urls: list[str]) -> dict` — mismas claves que
  `run()` (`analizadas`, `duplicadas`)

- [ ] **Step 1: Escribir la prueba que falla**

Agregar a `tests/test_analizar.py` (usa el helper `_con_ofertas` que ya
existe en el archivo):

```python
def test_run_urls_analiza_solo_las_pedidas(tmp_path):
    eng = db.engine(tmp_path / "au1.db")
    _con_ofertas(eng, [
        {"job_url": "http://x/1", "title": "Cajero", "company": "Super X",
         "description": "Se busca cajero, manejo de caja.", "scrape_date": "2026-08-01"},
        {"job_url": "http://x/2", "title": "Guardia", "company": "Segura Ltda",
         "description": "Guardia de seguridad turno noche.", "scrape_date": "2026-08-01"},
    ])
    resumen = analizar.run_urls(eng, ["http://x/1"])
    assert resumen["analizadas"] == 1
    filas = db.consultar(eng, "SELECT job_url FROM oferta_analisis")
    assert [f[0] for f in filas] == ["http://x/1"]


def test_run_urls_detecta_duplicado_contra_oferta_vieja_ya_analizada(tmp_path):
    eng = db.engine(tmp_path / "au2.db")
    _con_ofertas(eng, [
        {"job_url": "http://x/1", "site": "trabajando", "title": "Cajero/a",
         "company": "Super X", "description": "texto", "scrape_date": "2026-08-01"},
    ])
    analizar.run(eng)  # deja http://x/1 analizada y marcada "no duplicada"

    _con_ofertas(eng, [
        {"job_url": "http://x/2", "site": "computrabajo", "title": "CAJERO/A",
         "company": "super x", "description": "texto", "scrape_date": "2026-08-02"},
    ])
    resumen = analizar.run_urls(eng, ["http://x/2"])
    assert resumen["analizadas"] == 1
    assert resumen["duplicadas"] == 1
    duplicada = db.consultar(eng, "SELECT duplicada FROM oferta_analisis"
                                  " WHERE job_url = 'http://x/2'")[0][0]
    assert duplicada == 1
    original = db.consultar(eng, "SELECT duplicada FROM oferta_analisis"
                                 " WHERE job_url = 'http://x/1'")[0][0]
    assert original == 0


def test_run_urls_sin_urls_no_hace_nada(tmp_path):
    eng = db.engine(tmp_path / "au3.db")
    db.ensure_schema(eng)
    assert analizar.run_urls(eng, []) == {"analizadas": 0, "duplicadas": 0}


def test_run_urls_no_reescribe_lo_no_pedido(tmp_path):
    eng = db.engine(tmp_path / "au4.db")
    _con_ofertas(eng, [
        {"job_url": "http://x/1", "title": "Cajero", "company": "X",
         "description": "texto", "scrape_date": "2026-08-01"},
        {"job_url": "http://x/2", "title": "Guardia", "company": "Y",
         "description": "texto", "scrape_date": "2026-08-01"},
    ])
    analizar.run_urls(eng, ["http://x/1"])
    assert db.escalar(eng, "SELECT COUNT(*) FROM oferta_analisis") == 1
```

- [ ] **Step 2: Correr la prueba y verificar que falla**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_analizar.py -k run_urls -v
```

Esperado: FAIL con `AttributeError: module 'analizar' has no attribute 'run_urls'`

- [ ] **Step 3: Implementar**

Reemplazar el cuerpo de `analizar.py` completo (mantiene `run()` con el
mismo comportamiento externo, extrae piezas compartidas, y agrega
`run_urls`):

```python
# -*- coding: utf-8 -*-
"""Analiza las ofertas guardadas y escribe `oferta_analisis`.

Todo lo que calcula es genérico —no depende de ningún perfil—: habilidades,
áreas, región, modalidad, tipo de contrato, años pedidos, inglés
excluyente, si es duplicada, y vigencia estimada. El puntaje contra un
perfil se calcula al vuelo en una capa posterior (la app), con
motor.puntaje.puntuar."""
import json
from datetime import datetime, timezone

from motor.atributos import (anios_experiencia, ingles_excluyente, modalidad,
                             region, tipo_contrato, vigencia)
from motor.areas import clasificar as clasificar_areas
from motor.habilidades import detectar
from motor.texto import normalizar

import db


def _cargar_filas_ofertas(eng):
    return db.consultar(eng, "SELECT job_url, site, title, company,"
                             " location, date_posted, is_remote,"
                             " description, scrape_date, last_seen"
                             " FROM ofertas")


def _duplicada_por_url(filas_ofertas):
    """Clave de deduplicación por contenido: misma oferta publicada varias
    veces (distinto link o distinta fuente). Se conserva la primera
    capturada. Se calcula siempre sobre TODAS las filas recibidas, para
    que una URL nueva se compare también contra ofertas viejas."""
    ordenadas = sorted(filas_ofertas, key=lambda f: (f[8] or "", f[0]))
    vistas_clave = set()
    duplicada_por_url = {}
    for f in ordenadas:
        job_url, _, title, company, location = f[0], f[1], f[2], f[3], f[4]
        clave = f"{normalizar(title)}|{normalizar(company)}|{region(location)}"
        duplicada_por_url[job_url] = clave in vistas_clave
        vistas_clave.add(clave)
    return duplicada_por_url


def _analizar_fila(f, hoy, ultima_corrida, duplicada_por_url):
    (job_url, site, title, company, location, date_posted, is_remote,
     description, scrape_date, last_seen) = f
    texto_completo = f"{title} {company} {description}"
    habilidades = detectar(texto_completo)
    areas = clasificar_areas(texto_completo)
    es_remoto = str(is_remote).lower() == "true"
    vig = vigencia(date_posted, last_seen, hoy, ultima_corrida)
    return {
        "job_url": job_url,
        "habilidades": json.dumps(habilidades, ensure_ascii=False),
        "areas": json.dumps(areas, ensure_ascii=False),
        "region": region(location),
        "modalidad": modalidad(texto_completo, es_remoto=es_remoto),
        "tipo_contrato": tipo_contrato(texto_completo),
        "anios_experiencia_pedidos": anios_experiencia(texto_completo),
        "ingles_excluyente": int(ingles_excluyente(texto_completo)),
        "duplicada": int(duplicada_por_url.get(job_url, False)),
        "vigencia_estimada": json.dumps(vig, ensure_ascii=False),
        "analizado_en": hoy.isoformat(),
    }


def run(eng, db_path=None) -> dict:
    db.ensure_schema(eng)
    filas_ofertas = _cargar_filas_ofertas(eng)
    if not filas_ofertas:
        return {"analizadas": 0, "duplicadas": 0}

    hoy = datetime.now(timezone.utc).date()
    ultima_corrida = max(
        (f[9] for f in filas_ofertas if f[9]), default=hoy.isoformat())
    duplicada_por_url = _duplicada_por_url(filas_ofertas)

    filas_analisis = [_analizar_fila(f, hoy, ultima_corrida, duplicada_por_url)
                      for f in filas_ofertas]
    db.upsert_oferta_analisis(eng, filas_analisis)

    return {
        "analizadas": len(filas_analisis),
        "duplicadas": sum(1 for v in duplicada_por_url.values() if v),
    }


def run_urls(eng, urls: list[str]) -> dict:
    """Igual que run(), pero solo calcula y guarda el análisis pesado
    (habilidades, áreas, etc.) para `urls` — pensado para la búsqueda en
    vivo, que no puede pagar el costo de reanalizar toda la tabla dentro
    de su presupuesto de tiempo. La deduplicación sigue mirando la base
    completa: una URL nueva puede ser duplicado de una oferta vieja que
    no está en `urls`."""
    db.ensure_schema(eng)
    if not urls:
        return {"analizadas": 0, "duplicadas": 0}

    filas_ofertas = _cargar_filas_ofertas(eng)
    if not filas_ofertas:
        return {"analizadas": 0, "duplicadas": 0}

    hoy = datetime.now(timezone.utc).date()
    ultima_corrida = max(
        (f[9] for f in filas_ofertas if f[9]), default=hoy.isoformat())
    duplicada_por_url = _duplicada_por_url(filas_ofertas)

    urls_pedidas = set(urls)
    filas_pedidas = [f for f in filas_ofertas if f[0] in urls_pedidas]
    filas_analisis = [_analizar_fila(f, hoy, ultima_corrida, duplicada_por_url)
                      for f in filas_pedidas]
    db.upsert_oferta_analisis(eng, filas_analisis)

    return {
        "analizadas": len(filas_analisis),
        "duplicadas": sum(1 for u in urls_pedidas if duplicada_por_url.get(u, False)),
    }


if __name__ == "__main__":
    eng = db.engine()
    resumen = run(eng)
    print(f"Ofertas analizadas: {resumen['analizadas']} "
          f"(duplicadas: {resumen['duplicadas']})")
```

- [ ] **Step 4: Correr las pruebas y verificar que pasan, sin regresiones**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_analizar.py -v
```

Esperado: todas pasan — las pruebas de `run()` que ya existían (no
tocadas) más las 4 nuevas de `run_urls`.

- [ ] **Step 5: Correr la suite completa**

```powershell
.venv\Scripts\python.exe -m pytest tests -v
```

Esperado: sin regresiones en el resto del proyecto (`recolectar.py`
sigue llamando `analizar.run(eng)` tal cual, sin cambios).

- [ ] **Step 6: Commit**

```bash
git add analizar.py tests/test_analizar.py
git commit -m "feat: analizar.run_urls, analisis acotado para busqueda en vivo"
```

---

### Task 3: `buscar_en_vivo.py`

El orquestador completo: reutilización, scraping con presupuesto de
tiempo repartido entre cargos y fuentes, persistencia, análisis acotado,
y el guardarraíl de concurrencia. Mismo patrón que `recolectar.py`
(módulos de fuente resueltos en el momento de la llamada, no capturados
antes, para que los mocks de los tests tengan efecto).

**Files:**
- Create: `buscar_en_vivo.py`
- Test: `tests/test_buscar_en_vivo.py`

**Interfaces:**
- Consumes: `db.agregar_termino`, `db.termino_reciente`,
  `db.registrar_corrida_termino`, `db.upsert_ofertas`, `db.cargar_ofertas`,
  `analizar.run_urls`, `fuente_getonbrd.fetch_all`,
  `fuente_trabajando.fetch_all`, `fuente_laborum.fetch_all`,
  `fuente_computrabajo.fetch_all` (misma firma en las cuatro:
  `fetch_all(terminos: list[str], excluir_urls=None) -> tuple[list[dict], set, str | None]`)
- Produces:
  - `buscar(eng, cargos: list[str], presupuesto_segundos: int = 30, ahora: str | None = None, on_progreso: callable | None = None) -> dict`
    — devuelve `{"buscados": list[str], "reutilizados": list[str],
    "en_cola": list[str], "ofertas_nuevas": dict[str, int], "agotado": bool}`
  - `MAX_SIMULTANEAS = 3`

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_buscar_en_vivo.py`:

```python
# -*- coding: utf-8 -*-
from unittest.mock import patch

import buscar_en_vivo
import db


def _fila_falsa(url, cargo, site="getonbrd"):
    return {"job_url": url, "site": site, "search_term": cargo,
            "title": "Cajero", "company": "X", "location": "Chile",
            "date_posted": "2026-08-01", "job_type": None,
            "is_remote": "False", "min_amount": None, "max_amount": None,
            "currency": None, "interval": None, "description": "texto de cajero",
            "scrape_date": "2026-08-07"}


def test_buscar_persiste_lo_encontrado_y_lo_deja_analizado(tmp_path):
    eng = db.engine(tmp_path / "b1.db")
    db.ensure_schema(eng)
    with patch("fuente_getonbrd.fetch_all",
               return_value=([_fila_falsa("http://gb/1", "cajero")],
                             {"http://gb/1"}, None)), \
         patch("fuente_trabajando.fetch_all", return_value=([], set(), None)), \
         patch("fuente_laborum.fetch_all", return_value=([], set(), None)), \
         patch("fuente_computrabajo.fetch_all", return_value=([], set(), None)):
        resumen = buscar_en_vivo.buscar(eng, ["cajero"],
                                        ahora="2026-08-07T10:00:00")

    assert resumen["buscados"] == ["cajero"]
    assert resumen["ofertas_nuevas"] == {"cajero": 1}
    assert resumen["reutilizados"] == []
    assert resumen["en_cola"] == []
    assert db.escalar(eng, "SELECT COUNT(*) FROM ofertas") == 1
    fila = db.consultar(eng, "SELECT habilidades FROM oferta_analisis"
                             " WHERE job_url = 'http://gb/1'")
    assert fila, "la oferta nueva debe quedar analizada, no solo insertada"


def test_buscar_registra_la_corrida_del_cargo(tmp_path):
    eng = db.engine(tmp_path / "b2.db")
    db.ensure_schema(eng)
    with patch("fuente_getonbrd.fetch_all",
               return_value=([_fila_falsa("http://gb/1", "cajero")],
                             {"http://gb/1"}, None)), \
         patch("fuente_trabajando.fetch_all", return_value=([], set(), None)), \
         patch("fuente_laborum.fetch_all", return_value=([], set(), None)), \
         patch("fuente_computrabajo.fetch_all", return_value=([], set(), None)):
        buscar_en_vivo.buscar(eng, ["cajero"], ahora="2026-08-07T10:00:00")

    fila = db.consultar(eng, "SELECT origen, ultima_corrida, ofertas_ultimas"
                             " FROM terminos_busqueda WHERE termino = 'cajero'")[0]
    assert fila[0] == "usuario"
    assert fila[1] == "2026-08-07T10:00:00"
    assert fila[2] == 1


def test_buscar_cargo_reciente_no_vuelve_a_scrapear(tmp_path):
    eng = db.engine(tmp_path / "b3.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "cajero", "base", "2026-08-06T00:00:00")
    db.registrar_corrida_termino(eng, "cajero", 5, "2026-08-06T10:00:00")

    with patch("fuente_getonbrd.fetch_all") as m_gb, \
         patch("fuente_trabajando.fetch_all") as m_tb, \
         patch("fuente_laborum.fetch_all") as m_lb, \
         patch("fuente_computrabajo.fetch_all") as m_ct:
        # "ahora" es 12 horas después de la corrida: sigue dentro de 24h
        resumen = buscar_en_vivo.buscar(eng, ["cajero"],
                                        ahora="2026-08-06T22:00:00")

    m_gb.assert_not_called()
    m_tb.assert_not_called()
    m_lb.assert_not_called()
    m_ct.assert_not_called()
    assert resumen["reutilizados"] == ["cajero"]
    assert resumen["buscados"] == []


def test_buscar_cargo_corrido_hace_mas_de_24h_si_vuelve_a_scrapear(tmp_path):
    eng = db.engine(tmp_path / "b4.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "cajero", "base", "2026-08-04T00:00:00")
    db.registrar_corrida_termino(eng, "cajero", 0, "2026-08-04T10:00:00")

    with patch("fuente_getonbrd.fetch_all",
               return_value=([], set(), None)) as m_gb, \
         patch("fuente_trabajando.fetch_all", return_value=([], set(), None)), \
         patch("fuente_laborum.fetch_all", return_value=([], set(), None)), \
         patch("fuente_computrabajo.fetch_all", return_value=([], set(), None)):
        resumen = buscar_en_vivo.buscar(eng, ["cajero"],
                                        ahora="2026-08-06T22:00:00")

    m_gb.assert_called_once()
    assert resumen["buscados"] == ["cajero"]


def test_buscar_ninguna_fuente_responde_no_registra_la_corrida(tmp_path):
    eng = db.engine(tmp_path / "b5.db")
    db.ensure_schema(eng)

    def falla(*a, **k):
        return [], set(), "boom: la red se cayó"

    with patch("fuente_getonbrd.fetch_all", falla), \
         patch("fuente_trabajando.fetch_all", falla), \
         patch("fuente_laborum.fetch_all", falla), \
         patch("fuente_computrabajo.fetch_all", falla):
        buscar_en_vivo.buscar(eng, ["cajero"], ahora="2026-08-07T10:00:00")

    fila = db.consultar(eng, "SELECT ultima_corrida FROM terminos_busqueda"
                             " WHERE termino = 'cajero'")[0]
    assert fila[0] is None, "no debe quedar marcado como corrido"


def test_buscar_corta_fuentes_por_presupuesto_dentro_de_un_cargo(tmp_path):
    eng = db.engine(tmp_path / "b6.db")
    db.ensure_schema(eng)

    with patch("fuente_getonbrd.fetch_all",
               return_value=([], set(), None)) as m_gb, \
         patch("fuente_trabajando.fetch_all",
               return_value=([], set(), None)) as m_tb, \
         patch("fuente_laborum.fetch_all",
               return_value=([], set(), None)) as m_lb, \
         patch("fuente_computrabajo.fetch_all",
               return_value=([], set(), None)) as m_ct, \
         patch("time.monotonic", side_effect=[0, 0, 0, 0, 100]):
        # inicio=0; chequeo antes del cargo=0 (ok); antes de getonbrd=0
        # (ok, corre); antes de trabajando=0 (ok, corre); antes de
        # laborum=100 (excede presupuesto de 50s, corta ahí).
        resumen = buscar_en_vivo.buscar(eng, ["cajero"], presupuesto_segundos=50,
                                        ahora="2026-08-07T10:00:00")

    m_gb.assert_called_once()
    m_tb.assert_called_once()
    m_lb.assert_not_called()
    m_ct.assert_not_called()
    assert resumen["agotado"] is True
    assert resumen["buscados"] == ["cajero"]


def test_buscar_dos_cargos_el_segundo_queda_en_cola_por_presupuesto(tmp_path):
    eng = db.engine(tmp_path / "b7.db")
    db.ensure_schema(eng)

    with patch("fuente_getonbrd.fetch_all", return_value=([], set(), None)), \
         patch("fuente_trabajando.fetch_all", return_value=([], set(), None)), \
         patch("fuente_laborum.fetch_all", return_value=([], set(), None)), \
         patch("fuente_computrabajo.fetch_all", return_value=([], set(), None)), \
         patch("time.monotonic", side_effect=[0, 0, 0, 0, 0, 0, 100]):
        # inicio=0; cargo1: chequeo=0(ok), 4 fuentes con chequeo=0 cada
        # una (todas corren); cargo2: chequeo=100 (excede, no llega a
        # scrapear, queda en cola).
        resumen = buscar_en_vivo.buscar(eng, ["cajero", "reponedor"],
                                        presupuesto_segundos=50,
                                        ahora="2026-08-07T10:00:00")

    assert resumen["buscados"] == ["cajero"]
    assert resumen["en_cola"] == ["reponedor"]
    assert resumen["agotado"] is True
    # el que quedó en cola igual se registra para la corrida programada
    assert db.escalar(
        eng, "SELECT COUNT(*) FROM terminos_busqueda WHERE termino = 'reponedor'"
    ) == 1


def test_buscar_llama_on_progreso_por_cada_cargo(tmp_path):
    eng = db.engine(tmp_path / "b8.db")
    db.ensure_schema(eng)
    llamadas = []

    with patch("fuente_getonbrd.fetch_all", return_value=([], set(), None)), \
         patch("fuente_trabajando.fetch_all", return_value=([], set(), None)), \
         patch("fuente_laborum.fetch_all", return_value=([], set(), None)), \
         patch("fuente_computrabajo.fetch_all", return_value=([], set(), None)):
        buscar_en_vivo.buscar(eng, ["cajero", "reponedor"],
                              ahora="2026-08-07T10:00:00",
                              on_progreso=lambda i, t, c: llamadas.append((i, t, c)))

    assert llamadas == [(1, 2, "cajero"), (2, 2, "reponedor")]


def test_semaforo_permite_hasta_max_simultaneas():
    adquiridos = [buscar_en_vivo._semaforo.acquire(blocking=False)
                 for _ in range(buscar_en_vivo.MAX_SIMULTANEAS)]
    try:
        assert all(adquiridos)
        assert buscar_en_vivo._semaforo.acquire(blocking=False) is False
    finally:
        for ok in adquiridos:
            if ok:
                buscar_en_vivo._semaforo.release()


def test_buscar_con_el_cupo_lleno_no_scrapea_y_encola(tmp_path):
    eng = db.engine(tmp_path / "b9.db")
    db.ensure_schema(eng)
    for _ in range(buscar_en_vivo.MAX_SIMULTANEAS):
        buscar_en_vivo._semaforo.acquire()
    try:
        with patch("fuente_getonbrd.fetch_all") as m_gb, \
             patch("fuente_trabajando.fetch_all") as m_tb, \
             patch("fuente_laborum.fetch_all") as m_lb, \
             patch("fuente_computrabajo.fetch_all") as m_ct:
            resumen = buscar_en_vivo.buscar(eng, ["cajero"],
                                            ahora="2026-08-07T10:00:00")
        m_gb.assert_not_called()
        m_tb.assert_not_called()
        m_lb.assert_not_called()
        m_ct.assert_not_called()
        assert resumen == {"buscados": [], "reutilizados": [],
                           "en_cola": ["cajero"], "ofertas_nuevas": {},
                           "agotado": False}
        assert db.escalar(
            eng, "SELECT COUNT(*) FROM terminos_busqueda WHERE termino = 'cajero'"
        ) == 1
    finally:
        for _ in range(buscar_en_vivo.MAX_SIMULTANEAS):
            buscar_en_vivo._semaforo.release()
```

- [ ] **Step 2: Correr las pruebas y verificar que fallan**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_buscar_en_vivo.py -v
```

Esperado: FAIL con `ModuleNotFoundError: No module named 'buscar_en_vivo'`

- [ ] **Step 3: Implementar**

Crear `buscar_en_vivo.py`:

```python
# -*- coding: utf-8 -*-
"""Búsqueda en vivo: cuando un perfil recién guardado no calza con nada
de lo recolectado, scrapea los cargos de ese perfil en el momento (tope
de tiempo, resultados parciales) en vez de dejar la app vacía hasta la
próxima corrida programada.

Reusa el mismo camino de persistencia que `recolectar.py` — mismas
tablas, mismo criterio de "corrida fallida no se registra" — así que un
cargo buscado en vivo entra a la rotación normal de
`db.terminos_pendientes` igual que cualquier otro, sin trato especial."""
import threading
import time
from datetime import datetime, timezone

import analizar
import db
import fuente_computrabajo
import fuente_getonbrd
import fuente_laborum
import fuente_trabajando

PRESUPUESTO_SEGUNDOS_DEFECTO = 30

MAX_SIMULTANEAS = 3

# Orden de velocidad esperada, NO el orden de recolectar.py: acá interesa
# maximizar lo que llega antes del corte de 30s, así que la fuente más
# lenta (computrabajo, HTML paginado) va al final — la primera en
# quedarse sin tiempo si hay que cortar. Se guardan los módulos, no
# `modulo.fetch_all` ya resuelto, por la misma razón que en
# recolectar.py: así los mocks de los tests tienen efecto.
FUENTES = (
    ("getonbrd", fuente_getonbrd),
    ("trabajando", fuente_trabajando),
    ("laborum", fuente_laborum),
    ("computrabajo", fuente_computrabajo),
)

COLUMNAS_OFERTA = ("job_url", "site", "search_term", "title", "company",
                   "location", "date_posted", "job_type", "is_remote",
                   "min_amount", "max_amount", "currency", "interval",
                   "description", "scrape_date", "last_seen")

_semaforo = threading.Semaphore(MAX_SIMULTANEAS)


def buscar(eng, cargos: list[str],
          presupuesto_segundos: int = PRESUPUESTO_SEGUNDOS_DEFECTO,
          ahora: str | None = None, on_progreso=None) -> dict:
    """Busca en vivo los `cargos` que lo necesiten contra las cuatro
    fuentes, con un presupuesto de tiempo total. `on_progreso`, si se
    pasa, se llama como `on_progreso(indice, total, cargo)` después de
    procesar cada cargo (buscado o reutilizado) — para que `app.py`
    pueda mostrar una barra de progreso sin que este módulo dependa de
    streamlit."""
    db.ensure_schema(eng)
    ahora = ahora or datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    if not _semaforo.acquire(blocking=False):
        # Cupo lleno: no se scrapea nada, pero el cargo igual queda
        # registrado para la corrida programada — este guardarraíl nunca
        # bloquea el guardado del perfil.
        for cargo in cargos:
            db.agregar_termino(eng, cargo, "usuario", ahora)
        return {"buscados": [], "reutilizados": [], "en_cola": list(cargos),
                "ofertas_nuevas": {}, "agotado": False}
    try:
        return _buscar_con_cupo(eng, cargos, presupuesto_segundos, ahora,
                                on_progreso)
    finally:
        _semaforo.release()


def _buscar_con_cupo(eng, cargos, presupuesto_segundos, ahora, on_progreso) -> dict:
    hoy = ahora[:10]
    for cargo in cargos:
        db.agregar_termino(eng, cargo, "usuario", ahora)

    inicio = time.monotonic()
    buscados, reutilizados, en_cola = [], [], []
    ofertas_nuevas = {}
    urls_nuevas_totales = []
    conocidas = {f["job_url"] for f in db.cargar_ofertas(eng)}
    agotado = False

    for i, cargo in enumerate(cargos):
        if db.termino_reciente(eng, cargo, ahora):
            reutilizados.append(cargo)
            if on_progreso:
                on_progreso(i + 1, len(cargos), cargo)
            continue

        if time.monotonic() - inicio > presupuesto_segundos:
            agotado = True
            en_cola.extend(cargos[i:])
            break

        total_cargo = 0
        alguna_respondio = False
        urls_nuevas_cargo = []
        for nombre_fuente, modulo in FUENTES:
            if time.monotonic() - inicio > presupuesto_segundos:
                agotado = True
                break
            try:
                filas, vigentes, error = modulo.fetch_all(
                    [cargo], excluir_urls=conocidas)
            except Exception as e:
                filas, vigentes, error = [], set(), str(e)[:300]
            vigentes = vigentes or set()
            total_cargo += len(vigentes)
            if filas:
                for f in filas:
                    f.setdefault("scrape_date", hoy)
                    f.setdefault("last_seen", hoy)
                    f.setdefault("search_term", cargo)
                columnas = [c for c in COLUMNAS_OFERTA if c in filas[0]]
                try:
                    db.upsert_ofertas(eng, filas, columnas)
                except Exception as e:
                    print(f"[ERROR] guardando ofertas de {nombre_fuente}"
                         f" '{cargo}': {e}")
                nuevas = {f["job_url"] for f in filas} - conocidas
                urls_nuevas_cargo.extend(nuevas)
                conocidas |= nuevas
            if error:
                print(f"[ERROR] {nombre_fuente} '{cargo}': {error}")
            else:
                alguna_respondio = True

        # Mismo criterio que recolectar.py (commit 8203005): una corrida
        # donde ninguna fuente respondió no es información sobre el
        # cargo, es información sobre la red — no se registra, para que
        # pueda reintentarse.
        if alguna_respondio:
            db.registrar_corrida_termino(eng, cargo, total_cargo, ahora)
        buscados.append(cargo)
        ofertas_nuevas[cargo] = len(urls_nuevas_cargo)
        urls_nuevas_totales.extend(urls_nuevas_cargo)
        if on_progreso:
            on_progreso(i + 1, len(cargos), cargo)

    if urls_nuevas_totales:
        analizar.run_urls(eng, urls_nuevas_totales)

    return {"buscados": buscados, "reutilizados": reutilizados,
            "en_cola": en_cola, "ofertas_nuevas": ofertas_nuevas,
            "agotado": agotado}
```

- [ ] **Step 4: Correr las pruebas y verificar que pasan**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_buscar_en_vivo.py -v
```

Esperado: todas pasan (11 pruebas)

- [ ] **Step 5: Correr la suite completa**

```powershell
.venv\Scripts\python.exe -m pytest tests -v
```

Esperado: sin regresiones

- [ ] **Step 6: Commit**

```bash
git add buscar_en_vivo.py tests/test_buscar_en_vivo.py
git commit -m "feat: buscar_en_vivo, orquestador de busqueda en vivo con presupuesto y reutilizacion"
```

---

### Task 4: Enganche en `app.py`

Cuando `formulario_perfil` guarda un perfil cuyo resultado en
`puntuar_ofertas` da vacío, se llama `buscar_en_vivo.buscar` con una
barra de progreso, y se invalida la caché de `_ofertas_crudas` si hubo
resultados nuevos.

**Files:**
- Modify: `app.py`

**Interfaces:**
- Consumes: `buscar_en_vivo.buscar`, `app_data.puntuar_ofertas`,
  `app_data.sin_duplicadas`, `_ofertas_crudas` (ya existe en `app.py`)

- [ ] **Step 1: Modificar `formulario_perfil` en `app.py`**

Reemplazar el final de `formulario_perfil` (desde `app_data.guardar_perfil`
hasta el `return nuevo`):

```python
    app_data.guardar_perfil(st.session_state["usuario_id"], nuevo, _ahora())
    st.success("Perfil guardado.")

    crudas = _ofertas_crudas()
    if not app_data.puntuar_ofertas(app_data.sin_duplicadas(crudas), nuevo):
        _buscar_en_vivo_con_progreso(nuevo.cargos_buscados)

    return nuevo
```

Agregar la función nueva antes de `formulario_perfil` (o después, el
orden no importa mientras esté al nivel de módulo):

```python
def _buscar_en_vivo_con_progreso(cargos: list[str]) -> None:
    """Ningún cargo del perfil recién guardado calza con nada — busca en
    vivo contra las cuatro fuentes (tope 30s, resultados parciales) en
    vez de dejar a la persona con la app vacía hasta la corrida
    programada de mañana."""
    import buscar_en_vivo
    import db

    # st.progress no es un widget con estado (no acepta key=) — es un
    # elemento de despliegue puro, así que no le aplica el problema de
    # DuplicateElementId que sí afecta a los widgets interactivos.
    barra = st.progress(
        0.0, text="Todavía no tenemos ofertas para tu perfil — buscando en "
                  "vivo (esta es una primera pasada; mañana habrá más).")

    def avance(indice, total, cargo):
        barra.progress(indice / total, text=f"Buscando «{cargo}»"
                       f" ({indice}/{total})...")

    eng = db.engine()
    resumen = buscar_en_vivo.buscar(eng, cargos, on_progreso=avance)
    barra.empty()

    if any(resumen["ofertas_nuevas"].values()):
        _ofertas_crudas.clear()
    else:
        st.info("Todavía no encontramos ofertas publicadas para lo que "
                "buscás — seguimos intentando en las próximas corridas.")
```

- [ ] **Step 2: Commit**

```bash
git add app.py
git commit -m "feat: enganchar busqueda en vivo al guardar un perfil sin ofertas"
```

- [ ] **Step 3: Correr la suite completa**

```powershell
.venv\Scripts\python.exe -m pytest tests -v
```

Esperado: sin regresiones (este archivo no tiene pruebas automáticas
propias — `app.py` se verifica corriendo la app de verdad, como el resto
del proyecto).

- [ ] **Step 4: Verificar a mano con streamlit run**

```powershell
.venv\Scripts\python.exe -m streamlit run app.py
```

Comprobar, con la base real ya sembrada (`data/buscador.db` tiene los 26
términos base y sus ofertas — ver `docs/HANDOFF-2026-08-01.md` sobre
`REQUESTS_CA_BUNDLE` si las fuentes fallan por certificado en esta
máquina):

- Guardar un perfil con un cargo que **sí** calza con algo ya recolectado
  (ej. "cajero") no dispara ninguna barra de progreso — va directo a las
  pestañas.
- Guardar un perfil con un cargo real pero deliberadamente raro y no
  cubierto (ej. "operador de grúa horquilla" o cualquier cargo que no
  esté entre los 26 sembrados) dispara la barra de progreso, corre hasta
  30 segundos como máximo, y termina mostrando las pestañas — con
  ofertas si encontró algo, con el mensaje honesto si no.
- Si encontró algo: entrar a "Ofertas para ti" muestra las ofertas
  nuevas sin tener que recargar la página ni esperar (confirma que la
  caché se invalidó).
- Volver a guardar el mismo perfil (o entrar con otro usuario con el
  mismo cargo) dentro de la media hora siguiente no dispara la barra de
  progreso de nuevo — reutiliza lo ya buscado.
- Ningún error de `DuplicateElementId` ni excepción visible en la
  consola del navegador ni en la terminal.

---

## Al terminar

`buscar_en_vivo.py` completa el ciclo: perfil sin ofertas → búsqueda en
vivo con presupuesto y guardarraíles → mismas tablas que alimenta
`recolectar.py` → visible de inmediato para quien lo pidió, y disponible
sin esperar para cualquier otra persona que declare el mismo cargo
después.

**Revisión final de rama antes de mergear** — como en los cuatro planes
anteriores, la revisión de toda la rama contra `main` es la que
encuentra los bugs de integración que ninguna revisión por tarea puede
ver. Puntos de atención específicos para esta rama, dado lo que ya pasó
en las anteriores:

- ¿`_buscar_en_vivo_con_progreso` se dispara también al **editar** un
  perfil existente (no solo la primera vez), si el cargo nuevo no calza
  con nada? Debe — el chequeo está en `formulario_perfil`, que es el
  mismo camino para alta y edición.
- ¿Qué pasa si `buscar()` se llama con `cargos=[]` (perfil guardado sin
  cargos)? No debería llegar a pasar (`formulario_perfil` ya valida "al
  menos un cargo" antes), pero vale la pena confirmarlo con
  `AppTest` si surge duda.
- ¿El semáforo se libera correctamente si `_buscar_con_cupo` lanza una
  excepción no capturada (ej. `db.upsert_ofertas` con un error de
  schema)? El `try/finally` en `buscar()` debería cubrirlo — probarlo
  con un mock que lance.
- Confirmar con `AppTest` que las cinco pestañas siguen coexistiendo sin
  `DuplicateElementId` con la barra de progreso en el medio del flujo.

## Pendiente de calibración

- El tope de 3 búsquedas simultáneas y el presupuesto de 30s son los
  números del spec, sin datos reales de cuánta demanda concurrente tiene
  la app. Revisar cuando haya usuarios reales.
- `run_urls` sigue leyendo la tabla `ofertas` completa para construir las
  claves de deduplicación (aunque solo escribe análisis para las URLs
  pedidas) — con volumen mucho mayor al actual (miles de ofertas), esa
  lectura podría volverse el costo dominante dentro del presupuesto de
  30s. No es un problema con el volumen de hoy (~3.500 filas).
