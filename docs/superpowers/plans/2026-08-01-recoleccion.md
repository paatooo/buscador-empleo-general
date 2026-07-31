# Recolección — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir el pipeline que trae ofertas reales desde cuatro fuentes
públicas, las analiza con el motor ya construido y las deja disponibles en
la base — consumiendo `terminos_busqueda` en vez de una lista de búsquedas
fija en el código, que es el cambio central respecto del proyecto de
referencia.

**Architecture:** Un parser JSON-LD compartido (`jobposting.py`), cuatro
módulos de fuente (`fuente_getonbrd.py`, `fuente_computrabajo.py`,
`fuente_trabajando.py`, `fuente_laborum.py`) que devuelven `list[dict]` —no
`DataFrame`, para no agregar `pandas` como dependencia—, dos piezas nuevas en
`motor/` (clasificador de áreas y estimación de vigencia, ambas puras), un
analizador (`analizar.py`) que corre el motor sobre las ofertas guardadas y
escribe `oferta_analisis`, y un orquestador (`recolectar.py`) que reparte un
presupuesto de tiempo entre los términos pendientes, en el orden de
prioridad que ya calcula `db.terminos_pendientes`.

**Tech Stack:** Python 3.11+, `requests` (nueva dependencia — HTTP), el
resto biblioteca estándar más lo ya instalado (`sqlalchemy`). pytest con
`unittest.mock.patch` para simular HTTP — sin agregar una librería de
mocking nueva.

## Global Constraints

- **Proyecto independiente.** No importar, copiar ni depender de nada de
  `mapa-mercado-laboral`. Se lee como referencia para adaptar el enfoque
  probado de cada fuente — nunca se copia tal cual el código, porque cada
  fuente del proyecto de referencia tiene listas de búsqueda o palabras
  clave **fijas al perfil de una persona** (`SEARCHES_GETONBRD`,
  `SEARCHES_CT`, `KEYWORDS_SLUG`). Acá esas listas salen de
  `terminos_busqueda` — es el cambio de diseño que hace viable la
  recolección mixta del spec.
- **Sin `pandas`.** Las fuentes devuelven `list[dict]`, compatible
  directamente con `db.upsert_ofertas(eng, filas: list[dict], columnas)`.
  El proyecto de referencia usa `DataFrame` en todas partes; acá no hace
  falta y evita una dependencia pesada.
- **`oferta_analisis` sigue sin nada dependiente de un perfil.** El
  analizador escribe habilidades, áreas, región, modalidad, tipo de
  contrato, años pedidos, inglés excluyente, duplicada y vigencia —nunca un
  puntaje ni nada que dependa de qué persona lo esté viendo.
- **Presupuesto de tiempo, no tope de términos** (ya decidido en el spec):
  el orquestador corta la corrida a los ~45 minutos, no después de N
  términos.
- **Cortesía con los sitios**: mantener las pausas entre pedidos
  (`time.sleep`) del proyecto de referencia — son la razón por la que esas
  fuentes siguen funcionando sin bloquear la IP.
- **Nombres en español**, consistentes con el resto del proyecto.
- **HTTP se simula en las pruebas.** Nada de esta suite pega a un sitio
  real — eso rompería en CI y depende de que el sitio no cambie su HTML.
  Se usa `unittest.mock.patch("requests.get", ...)`, sin agregar
  `responses` ni `requests-mock`.

---

## Estructura de archivos

```
buscador-empleo-personalizado/
├── jobposting.py              parser JSON-LD schema.org/JobPosting
├── fuente_getonbrd.py         API pública de Get on Board
├── fuente_computrabajo.py     scraping HTML de Computrabajo
├── fuente_trabajando.py       sitemap + JSON-LD de Trabajando.cl
├── fuente_laborum.py          sitemap + JSON-LD de Laborum.cl
├── motor/
│   ├── areas.py                CATALOGO_AREAS, clasificar()
│   └── atributos.py             + vigencia()  (se extiende, no se crea)
├── analizar.py                 corre el motor sobre `ofertas`, escribe
│                                oferta_analisis
├── recolectar.py               orquestador con presupuesto de tiempo
├── requirements.txt             + requests
└── tests/
    ├── test_jobposting.py
    ├── test_fuente_getonbrd.py
    ├── test_fuente_computrabajo.py
    ├── test_fuente_trabajando.py
    ├── test_fuente_laborum.py
    ├── test_areas.py
    ├── test_atributos.py        (se extiende con vigencia())
    ├── test_analizar.py
    └── test_recolectar.py
```

`jobposting.py` no depende de nada del proyecto. Cada `fuente_*.py` importa
`jobposting` cuando necesita parsear JSON-LD (`trabajando`, `laborum`) y
`requests`; ninguna importa `db` ni `motor` — siguen siendo capas de
recolección pura, igual que en el proyecto de referencia. `motor/areas.py`
y la nueva función en `motor/atributos.py` son puras, sin red ni base de
datos, siguiendo la misma disciplina que el resto de `motor/`.
`analizar.py` importa `db` y `motor`; `recolectar.py` importa `db` y las
cuatro fuentes, y llama a `analizar.py` al final de cada corrida.

---

### Task 1: Parser JSON-LD compartido

Ya existe en el proyecto de referencia y es completamente genérico —no
depende de ningún perfil—, así que se porta casi sin cambios. Lo usan las
fuentes que scrapean páginas de detalle con datos estructurados
(`trabajando`, `laborum`).

**Files:**
- Create: `jobposting.py`
- Test: `tests/test_jobposting.py`

**Interfaces:**
- Consumes: nada
- Produces:
  - `extraer(html: str) -> dict | None` — bloque JSON-LD `JobPosting`, o
    `None` si no hay
  - `texto(html_desc: str) -> str` — HTML a texto plano, preservando
    párrafos y viñetas
  - `ubicacion(d: dict) -> str` — dirección legible desde `jobLocation`
  - `a_fila(d: dict, url: str, site: str) -> dict` — el `JobPosting` ya
    parseado, convertido a la fila que espera `db.upsert_ofertas`

- [ ] **Step 1: Escribir la prueba que falla**

Crear `tests/test_jobposting.py`:

```python
# -*- coding: utf-8 -*-
import jobposting

HTML_CON_JOBPOSTING = """
<html><head>
<script type="application/ld+json">
{"@context": "https://schema.org", "@type": "JobPosting",
 "title": "Cajero/a", "description": "<p>Se busca cajero.</p><ul><li>Turno tarde</li></ul>",
 "datePosted": "2026-07-01", "validThrough": "2026-08-01T00:00:00",
 "employmentType": "FULL_TIME",
 "hiringOrganization": {"@type": "Organization", "name": "Supermercado X"},
 "jobLocation": {"@type": "Place", "address": {"@type": "PostalAddress",
   "streetAddress": "Av. Principal 123", "addressLocality": "Santiago",
   "addressRegion": "Metropolitana"}},
 "jobLocationType": "TELECOMMUTE"}
</script>
</head><body></body></html>
"""

HTML_SIN_JOBPOSTING = "<html><body><p>Sin datos estructurados</p></body></html>"


def test_extraer_encuentra_el_bloque_jobposting():
    d = jobposting.extraer(HTML_CON_JOBPOSTING)
    assert d is not None
    assert d["title"] == "Cajero/a"


def test_extraer_sin_bloque_da_none():
    assert jobposting.extraer(HTML_SIN_JOBPOSTING) is None


def test_extraer_ignora_bloques_ld_json_de_otro_tipo():
    html = """<script type="application/ld+json">
    {"@type": "Organization", "name": "X"}
    </script>"""
    assert jobposting.extraer(html) is None


def test_texto_convierte_parrafos_y_listas():
    resultado = jobposting.texto("<p>Se busca cajero.</p><ul><li>Turno tarde</li></ul>")
    assert "Se busca cajero." in resultado
    assert "- Turno tarde" in resultado


def test_texto_con_html_vacio_da_cadena_vacia():
    assert jobposting.texto("") == ""


def test_texto_con_none_da_cadena_vacia():
    assert jobposting.texto(None) == ""


def test_ubicacion_arma_direccion_legible():
    loc = {"address": {"streetAddress": "Av. Principal 123",
                       "addressLocality": "Santiago",
                       "addressRegion": "Metropolitana"}}
    assert jobposting.ubicacion({"jobLocation": loc}) == \
        "Av. Principal 123, Santiago, Metropolitana"


def test_ubicacion_sin_direccion_da_chile():
    assert jobposting.ubicacion({}) == "Chile"


def test_a_fila_arma_la_fila_completa():
    d = jobposting.extraer(HTML_CON_JOBPOSTING)
    fila = jobposting.a_fila(d, "http://x/1", "trabajando")
    assert fila["site"] == "trabajando"
    assert fila["job_url"] == "http://x/1"
    assert fila["title"] == "Cajero/a"
    assert fila["company"] == "Supermercado X"
    assert fila["date_posted"] == "2026-07-01"
    assert fila["is_remote"] == "True"
    assert "Postulación vigente hasta 2026-08-01" in fila["description"]
    assert "Se busca cajero." in fila["description"]


def test_a_fila_sin_empresa_da_no_informada():
    d = {"title": "Cajero", "description": ""}
    fila = jobposting.a_fila(d, "http://x/2", "laborum")
    assert fila["company"] == "No informada"
```

- [ ] **Step 2: Correr la prueba y verificar que falla**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_jobposting.py -v
```

Esperado: FAIL con `ModuleNotFoundError: No module named 'jobposting'`

- [ ] **Step 3: Implementar**

Crear `jobposting.py`:

```python
# -*- coding: utf-8 -*-
"""Parser de datos estructurados schema.org/JobPosting (JSON-LD),
compartido por las fuentes que scrapean páginas de detalle. Genérico —no
depende de ningún perfil."""
import html as html_mod
import json
import re


def extraer(html: str) -> dict | None:
    for bloque in re.findall(
            r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
        try:
            d = json.loads(bloque)
        except json.JSONDecodeError:
            continue
        if isinstance(d, list):
            d = next((x for x in d if isinstance(x, dict)
                      and x.get("@type") == "JobPosting"), None)
        if isinstance(d, dict) and d.get("@type") == "JobPosting":
            return d
    return None


def texto(html_desc: str) -> str:
    """HTML → texto plano preservando estructura: párrafos, títulos y viñetas."""
    t = html_desc or ""
    t = re.sub(r"<\s*(br|/p|/div|/h[1-6]|/ul|/ol|/tr)\s*/?>", "\n", t, flags=re.I)
    t = re.sub(r"<\s*li[^>]*>", "\n- ", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html_mod.unescape(t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r" ?\n ?", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def ubicacion(d: dict) -> str:
    loc = d.get("jobLocation") or {}
    if isinstance(loc, list):
        loc = loc[0] if loc else {}
    dir_ = loc.get("address") or {}
    if not isinstance(dir_, dict):
        return str(dir_) or "Chile"
    partes = [dir_.get(k) for k in
              ("streetAddress", "addressLocality", "addressRegion")]
    return ", ".join(str(p) for p in partes if p) or "Chile"


def a_fila(d: dict, url: str, site: str) -> dict:
    """JobPosting → fila con el esquema de columnas de `ofertas`."""
    vence = str(d.get("validThrough") or "")[:10]
    desc = texto(d.get("description", ""))
    if vence:
        desc = f"Postulación vigente hasta {vence}. " + desc
    org = d.get("hiringOrganization") or {}
    return {
        "site": site,
        "job_url": url,
        "title": d.get("title"),
        "company": (org.get("name") if isinstance(org, dict) else str(org))
                   or "No informada",
        "location": ubicacion(d),
        "date_posted": str(d.get("datePosted") or "")[:10] or None,
        "job_type": d.get("employmentType"),
        "is_remote": str("TELECOMMUTE" in str(d.get("jobLocationType", ""))),
        "min_amount": None, "max_amount": None,
        "currency": None, "interval": None,
        "description": desc,
    }
```

- [ ] **Step 4: Correr las pruebas y verificar que pasan**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_jobposting.py -v
```

Esperado: 10 passed

- [ ] **Step 5: Commit**

```bash
git add jobposting.py tests/test_jobposting.py
git commit -m "feat: parser JSON-LD compartido para avisos con datos estructurados"
```

---

### Task 2: Fuente Get on Board

API pública, liviana. Es la fuente más simple y la primera candidata para
la búsqueda en vivo (plan futuro) porque responde en segundos.

**Files:**
- Create: `fuente_getonbrd.py`
- Test: `tests/test_fuente_getonbrd.py`

**Interfaces:**
- Consumes: `jobposting.texto`
- Produces:
  - `fetch(query: str, per_page: int = 50) -> list[dict]`
  - `fetch_all(terminos: list[str], excluir_urls: set | None = None, per_page: int = 50) -> tuple[list[dict], set[str], str | None]`
    — `(filas_nuevas, urls_vigentes, error_o_none)`

- [ ] **Step 1: Escribir la prueba que falla**

Crear `tests/test_fuente_getonbrd.py`:

```python
# -*- coding: utf-8 -*-
from unittest.mock import MagicMock, patch

import fuente_getonbrd

RESPUESTA_API = {
    "data": [
        {
            "links": {"public_url": "https://www.getonbrd.com/jobs/cajero-1"},
            "attributes": {
                "title": "Cajero/a",
                "countries": ["Chile"],
                "remote": False,
                "remote_modality": "no_remote",
                "published_at": 1751328000,  # 2025-07-01
                "min_salary": None, "max_salary": None,
                "description": "<p>Se busca cajero</p>",
                "company": {"data": {"attributes": {"name": "Empresa X"}}},
            },
        },
        {
            "links": {"public_url": "https://www.getonbrd.com/jobs/dev-2"},
            "attributes": {
                "title": "Developer", "countries": ["Argentina"],
                "remote": False, "remote_modality": "no_remote",
                "published_at": None, "description": "",
                "company": {"data": {"attributes": {"name": "Otra"}}},
            },
        },
    ]
}


def _respuesta_mock(json_data, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


def test_fetch_devuelve_filas_de_chile():
    with patch("requests.get", return_value=_respuesta_mock(RESPUESTA_API)):
        filas = fuente_getonbrd.fetch("cajero")
    assert len(filas) == 1
    assert filas[0]["title"] == "Cajero/a"
    assert filas[0]["site"] == "getonbrd"
    assert filas[0]["job_url"] == "https://www.getonbrd.com/jobs/cajero-1"


def test_fetch_descarta_ofertas_fuera_de_chile_y_no_remotas():
    with patch("requests.get", return_value=_respuesta_mock(RESPUESTA_API)):
        filas = fuente_getonbrd.fetch("cajero")
    urls = {f["job_url"] for f in filas}
    assert "https://www.getonbrd.com/jobs/dev-2" not in urls


def test_fetch_sin_resultados_da_lista_vacia():
    with patch("requests.get", return_value=_respuesta_mock({"data": []})):
        assert fuente_getonbrd.fetch("cargo-inexistente") == []


def test_fetch_all_usa_los_terminos_recibidos_no_una_lista_fija():
    # Requisito central del proyecto: los términos vienen de la base, no
    # de una constante en el código.
    with patch("requests.get", return_value=_respuesta_mock(RESPUESTA_API)) as m:
        fuente_getonbrd.fetch_all(["soldador", "garzon"])
    llamadas = [c.kwargs["params"]["query"] for c in m.call_args_list]
    assert llamadas == ["soldador", "garzon"]


def test_fetch_all_devuelve_urls_vigentes_y_sin_error():
    with patch("requests.get", return_value=_respuesta_mock(RESPUESTA_API)):
        filas, vigentes, error = fuente_getonbrd.fetch_all(["cajero"])
    assert len(filas) == 1
    assert vigentes == {"https://www.getonbrd.com/jobs/cajero-1"}
    assert error is None


def test_fetch_all_captura_error_sin_interrumpir_los_demas_terminos():
    def side_effect(*args, **kwargs):
        if kwargs["params"]["query"] == "falla":
            raise ConnectionError("timeout")
        return _respuesta_mock(RESPUESTA_API)

    with patch("requests.get", side_effect=side_effect):
        filas, vigentes, error = fuente_getonbrd.fetch_all(["falla", "cajero"])
    assert error is not None
    assert len(filas) == 1  # el segundo término sí funcionó
```

- [ ] **Step 2: Correr la prueba y verificar que falla**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_fuente_getonbrd.py -v
```

Esperado: FAIL con `ModuleNotFoundError: No module named 'fuente_getonbrd'`

- [ ] **Step 3: Implementar**

Crear `fuente_getonbrd.py`:

```python
# -*- coding: utf-8 -*-
"""Fuente Get on Board (getonbrd.com) — API pública.

A diferencia del proyecto de referencia, los términos de búsqueda no están
fijos en el código: los pasa quien llama (`recolectar.py`), leídos de
`terminos_busqueda`. Devuelve `list[dict]`, no `DataFrame` — compatible
directo con `db.upsert_ofertas`.
"""
import time
from datetime import datetime, timezone

import requests

import jobposting

API = "https://www.getonbrd.com/api/v0/search/jobs"
HEADERS = {"User-Agent": "Mozilla/5.0 (buscador-empleo-personalizado; uso personal)"}

# Textos en español para que el motor detecte la modalidad desde la descripción
_MODALIDAD = {
    "hybrid": "Modalidad de trabajo híbrida.",
    "remote": "Trabajo remoto.",
    "fully_remote": "Trabajo 100% remoto.",
    "remote_local": "Trabajo remoto local.",
    "no_remote": "Trabajo presencial.",
}


def fetch(query: str, per_page: int = 50) -> list[dict]:
    resp = requests.get(
        API, headers=HEADERS, timeout=30,
        params={"query": query, "per_page": per_page, "expand": '["company"]'},
    )
    resp.raise_for_status()
    filas = []
    for item in resp.json().get("data", []):
        a = item.get("attributes", {})
        countries = a.get("countries") or ""
        if isinstance(countries, (list, tuple)):
            countries = ", ".join(str(c) for c in countries)
        remoto = bool(a.get("remote"))
        if "Chile" not in countries and not remoto:
            continue  # solo Chile o remoto postulable desde Chile
        try:
            company = a["company"]["data"]["attributes"]["name"]
        except (KeyError, TypeError):
            company = ""
        publicada = None
        if a.get("published_at"):
            publicada = datetime.fromtimestamp(
                a["published_at"], tz=timezone.utc).date().isoformat()
        descripcion = "\n\n".join(
            jobposting.texto(a.get(campo)) for campo in
            ("description", "functions", "desirable", "projects") if a.get(campo)
        )

        def _num(v):
            return v if isinstance(v, (int, float)) else None

        job_url = str(item.get("links", {}).get("public_url") or "")
        if not job_url:
            continue
        filas.append({
            "site": "getonbrd",
            "job_url": job_url,
            "title": str(a.get("title") or ""),
            "company": str(company or ""),
            "location": str(countries or "Chile"),
            "date_posted": publicada,
            "job_type": None,
            "is_remote": str(remoto),
            "min_amount": _num(a.get("min_salary")),
            "max_amount": _num(a.get("max_salary")),
            "currency": "USD" if _num(a.get("min_salary")) else None,
            "interval": "monthly" if _num(a.get("min_salary")) else None,
            "description": _MODALIDAD.get(str(a.get("remote_modality")), "")
                           + " " + descripcion,
        })
    return filas


def fetch_all(terminos: list[str], excluir_urls=None,
              per_page: int = 50) -> tuple[list[dict], set, str | None]:
    """Itera los términos recibidos; retorna (filas, urls_vigentes,
    error_o_None). Trae siempre el resultado completo (la API es liviana),
    por lo que las urls vigentes son las del propio resultado."""
    filas, error = [], None
    for q in terminos:
        try:
            encontradas = fetch(q, per_page)
            for f in encontradas:
                f["search_term"] = q
            filas.extend(encontradas)
            print(f"[OK] getonbrd   '{q}': {len(encontradas)} ofertas")
        except Exception as e:
            error = str(e)[:300]
            print(f"[ERROR] getonbrd '{q}': {e}")
        time.sleep(1)
    vigentes = {f["job_url"] for f in filas}
    return filas, vigentes, error
```

- [ ] **Step 4: Correr las pruebas y verificar que pasan**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_fuente_getonbrd.py -v
```

Esperado: 6 passed

- [ ] **Step 5: Commit**

```bash
git add fuente_getonbrd.py tests/test_fuente_getonbrd.py
git commit -m "feat: fuente Get on Board, términos desde la base en vez de fijos"
```

---

### Task 3: Fuente Computrabajo

Scraping HTML: listado por término (con paginación) más detalle de cada
oferta nueva.

**Files:**
- Create: `fuente_computrabajo.py`
- Test: `tests/test_fuente_computrabajo.py`

**Interfaces:**
- Consumes: `jobposting.texto`
- Produces:
  - `fetch_all(terminos: list[str], excluir_urls: set | None = None, max_detalles: int = 100) -> tuple[list[dict], set[str], str | None]`

- [ ] **Step 1: Escribir la prueba que falla**

Crear `tests/test_fuente_computrabajo.py`:

```python
# -*- coding: utf-8 -*-
from unittest.mock import MagicMock, patch

import fuente_computrabajo

HTML_LISTADO = """
<article class="box_offer">
  <a href="/ofertas-de-trabajo/oferta-cajero-1234.html" class="js-o-link">
    Cajero/a supermercado
  </a>
  <p class="dFlex">Supermercado Los Andes</p>
  <span class="mr10">Santiago</span>
  <p class="fs13">Hace 2 días</p>
</article>
"""

HTML_DETALLE = """
<p class="mbB">Se busca cajero con experiencia en atención a público.</p>
<ul class="disc"><li>Turno tarde</li><li>Disponibilidad inmediata</li></ul>
"""


def _resp(text, status=200):
    r = MagicMock()
    r.status_code = status
    r.text = text
    r.raise_for_status = MagicMock()
    return r


def test_fetch_all_parsea_el_listado():
    with patch("requests.get", return_value=_resp(HTML_LISTADO)):
        filas, vigentes, error = fuente_computrabajo.fetch_all(["cajero"])
    assert len(filas) >= 1
    fila = filas[0]
    assert fila["title"] == "Cajero/a supermercado"
    assert fila["company"] == "Supermercado Los Andes"
    assert fila["job_url"].endswith("oferta-cajero-1234.html")


def test_fetch_all_usa_los_terminos_recibidos():
    urls_pedidas = []

    def side_effect(url, **kwargs):
        urls_pedidas.append(url)
        return _resp(HTML_LISTADO if "trabajo-de-" in url else HTML_DETALLE)

    with patch("requests.get", side_effect=side_effect):
        fuente_computrabajo.fetch_all(["soldador", "garzon"])
    listados = [u for u in urls_pedidas if "trabajo-de-" in u]
    assert any("trabajo-de-soldador" in u for u in listados)
    assert any("trabajo-de-garzon" in u for u in listados)


def test_fetch_all_trae_la_descripcion_del_detalle():
    def side_effect(url, **kwargs):
        return _resp(HTML_LISTADO if "trabajo-de-" in url else HTML_DETALLE)

    with patch("requests.get", side_effect=side_effect):
        filas, _, _ = fuente_computrabajo.fetch_all(["cajero"])
    assert "atención a público" in filas[0]["description"].lower()


def test_fetch_all_excluye_urls_ya_conocidas_del_detalle():
    llamadas_detalle = []

    def side_effect(url, **kwargs):
        if "trabajo-de-" in url:
            return _resp(HTML_LISTADO)
        llamadas_detalle.append(url)
        return _resp(HTML_DETALLE)

    conocida = "https://cl.computrabajo.com/ofertas-de-trabajo/oferta-cajero-1234.html"
    with patch("requests.get", side_effect=side_effect):
        fuente_computrabajo.fetch_all(["cajero"], excluir_urls={conocida})
    assert llamadas_detalle == []  # no se pidió el detalle de una oferta ya conocida


def test_fetch_all_captura_error_de_listado_sin_interrumpir():
    def side_effect(url, **kwargs):
        if "trabajo-de-falla" in url:
            raise ConnectionError("timeout")
        return _resp(HTML_LISTADO if "trabajo-de-" in url else HTML_DETALLE)

    with patch("requests.get", side_effect=side_effect):
        filas, _, error = fuente_computrabajo.fetch_all(["falla", "cajero"])
    assert error is not None
    assert len(filas) >= 1  # el segundo término sí funcionó
```

- [ ] **Step 2: Correr la prueba y verificar que falla**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_fuente_computrabajo.py -v
```

Esperado: FAIL con `ModuleNotFoundError: No module named 'fuente_computrabajo'`

- [ ] **Step 3: Implementar**

Crear `fuente_computrabajo.py`:

```python
# -*- coding: utf-8 -*-
"""Fuente Computrabajo Chile (cl.computrabajo.com) — scraping HTML.

Los términos de búsqueda vienen de `terminos_busqueda`, no de una lista
fija: se convierten a slug (espacios → guiones) antes de armar la URL.
"""
import html as html_mod
import re
import time
from datetime import date, timedelta

import requests

import jobposting

BASE = "https://cl.computrabajo.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
           "Accept-Language": "es-CL,es;q=0.9"}

PAGINAS_POR_BUSQUEDA = 2
MAX_DETALLES_POR_CORRIDA = 100


def _slug(termino: str) -> str:
    return re.sub(r"\s+", "-", termino.strip().lower())


def _limpia(html: str) -> str:
    texto = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()
    return html_mod.unescape(texto)


def _fecha_relativa(texto: str, hoy: date) -> str | None:
    """'Hace 3 días', 'Hace 5 horas', 'Ayer', 'Hoy' → fecha ISO."""
    t = texto.lower()
    if "hoy" in t or "hora" in t or "minuto" in t:
        return hoy.isoformat()
    if "ayer" in t:
        return (hoy - timedelta(days=1)).isoformat()
    m = re.search(r"hace\s+(\d+)\s+d[ií]as?", t)
    if m:
        return (hoy - timedelta(days=int(m.group(1)))).isoformat()
    m = re.search(r"hace\s+m[aá]s de\s+(\d+)\s+d[ií]as?", t)
    if m:
        return (hoy - timedelta(days=int(m.group(1)))).isoformat()
    return None


def _parse_listado(html: str, hoy: date) -> list[dict]:
    ofertas = []
    for art in re.findall(r"<article[^>]*box_offer.*?</article>", html, re.S):
        link = re.search(r'href="(/ofertas-de-trabajo/[^"#]+)', art)
        titulo = re.search(r'js-o-link[^>]*>\s*([^<]{3,120})', art)
        if not (link and titulo):
            continue
        empresa = re.search(r'<p class="dFlex[^"]*"[^>]*>(.*?)</p>', art, re.S)
        lugar = re.search(r'<span class="mr10">\s*([^<]{3,80})', art)
        fecha = re.search(r'<p class="fs13[^"]*"[^>]*>\s*([^<]{3,40})<', art)
        ofertas.append({
            "job_url": BASE + link.group(1).strip(),
            "title": _limpia(titulo.group(1)),
            "company": _limpia(empresa.group(1)) if empresa else "No informada",
            "location": _limpia(lugar.group(1)) if lugar else "Chile",
            "date_posted": _fecha_relativa(fecha.group(1), hoy) if fecha else None,
        })
    return ofertas


def _descripcion_detalle(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=25)
    parrafos = re.findall(r'<p class="mbB[^"]*"[^>]*>(.*?)</p>', r.text, re.S)
    listas = re.findall(r'<ul class="disc[^"]*"[^>]*>(.*?)</ul>', r.text, re.S)
    partes = [jobposting.texto(p) for p in parrafos]
    partes += [jobposting.texto(f"<ul>{u}</ul>") for u in listas]
    return "\n\n".join(x for x in partes if x)[:8000]


def fetch_all(terminos: list[str], excluir_urls=None,
              max_detalles: int = MAX_DETALLES_POR_CORRIDA
              ) -> tuple[list[dict], set, str | None]:
    excluir_urls = excluir_urls or set()
    hoy = date.today()
    vistas, filas, error = set(), [], None
    for q in terminos:
        slug = _slug(q)
        for pagina in range(1, PAGINAS_POR_BUSQUEDA + 1):
            url = f"{BASE}/trabajo-de-{slug}" + (f"?p={pagina}" if pagina > 1 else "")
            try:
                r = requests.get(url, headers=HEADERS, timeout=30)
                r.raise_for_status()
                for o in _parse_listado(r.text, hoy):
                    if o["job_url"] not in vistas:
                        o["search_term"] = q
                        vistas.add(o["job_url"])
                        filas.append(o)
            except Exception as e:
                error = str(e)[:200]
                print(f"[ERROR] computrabajo '{q}' p{pagina}: {e}")
            time.sleep(1)

    nuevas = [f for f in filas if f["job_url"] not in excluir_urls][:max_detalles]
    for f in nuevas:
        try:
            f["description"] = _descripcion_detalle(f["job_url"])
        except Exception as e:
            f["description"] = ""
            error = str(e)[:200]
        time.sleep(0.8)

    for f in nuevas:
        f["site"] = "computrabajo"
        for col, val in (("job_type", None), ("is_remote", "False"),
                         ("min_amount", None), ("max_amount", None),
                         ("currency", None), ("interval", None)):
            f[col] = val

    print(f"[OK] computrabajo: {len(nuevas)} ofertas nuevas "
          f"({len(filas)} vistas en listados)")
    return nuevas, vistas, error
```

- [ ] **Step 4: Correr las pruebas y verificar que pasan**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_fuente_computrabajo.py -v
```

Esperado: 5 passed

- [ ] **Step 5: Commit**

```bash
git add fuente_computrabajo.py tests/test_fuente_computrabajo.py
git commit -m "feat: fuente Computrabajo, slug de término desde la base"
```

---

### Task 4: Fuentes Trabajando y Laborum

Mismo patrón en ambas: sitemap con miles de URLs, filtrado por si el slug
contiene alguno de los términos pendientes, y solo se visita el detalle de
las URLs nuevas. A diferencia del proyecto de referencia (`KEYWORDS_SLUG`
fijo al perfil), el filtro sale de los términos recibidos.

**Files:**
- Create: `fuente_trabajando.py`
- Create: `fuente_laborum.py`
- Test: `tests/test_fuente_trabajando.py`
- Test: `tests/test_fuente_laborum.py`

**Interfaces:**
- Consumes: `jobposting.extraer`, `jobposting.a_fila`
- Produces:
  - `fuente_trabajando.fetch_all(terminos: list[str], excluir_urls: set | None = None, cap: int = 120) -> tuple[list[dict], set[str], str | None]`
  - `fuente_laborum.fetch_all(terminos: list[str], excluir_urls: set | None = None, cap: int = 100) -> tuple[list[dict], set[str], str | None]`

- [ ] **Step 1: Escribir la prueba que falla**

Crear `tests/test_fuente_trabajando.py`:

```python
# -*- coding: utf-8 -*-
from unittest.mock import MagicMock, patch

import fuente_trabajando

SITEMAP_XML = """<?xml version="1.0"?>
<urlset>
  <url><loc>https://www.trabajando.cl/ofertas/cajero-supermercado-1</loc></url>
  <url><loc>https://www.trabajando.cl/ofertas/desarrollador-web-2</loc></url>
  <url><loc>https://www.trabajando.cl/ofertas/soldador-industrial-3</loc></url>
</urlset>
"""

HTML_DETALLE = """
<script type="application/ld+json">
{"@type": "JobPosting", "title": "Cajero/a", "description": "<p>Texto</p>",
 "hiringOrganization": {"name": "Empresa X"}}
</script>
"""


def _resp(text, status=200):
    r = MagicMock()
    r.status_code = status
    r.text = text
    r.raise_for_status = MagicMock()
    return r


def test_fetch_all_filtra_por_los_terminos_recibidos():
    def side_effect(url, **kwargs):
        return _resp(SITEMAP_XML) if "sitemap" in url else _resp(HTML_DETALLE)

    with patch("requests.get", side_effect=side_effect):
        filas, vigentes, error = fuente_trabajando.fetch_all(["cajero"])
    # Solo la URL con "cajero" en el slug debe considerarse afín
    assert vigentes == {"https://www.trabajando.cl/ofertas/cajero-supermercado-1"}
    assert len(filas) == 1
    assert filas[0]["title"] == "Cajero/a"


def test_fetch_all_varios_terminos_amplían_lo_afin():
    def side_effect(url, **kwargs):
        return _resp(SITEMAP_XML) if "sitemap" in url else _resp(HTML_DETALLE)

    with patch("requests.get", side_effect=side_effect):
        filas, vigentes, error = fuente_trabajando.fetch_all(["cajero", "soldador"])
    assert vigentes == {
        "https://www.trabajando.cl/ofertas/cajero-supermercado-1",
        "https://www.trabajando.cl/ofertas/soldador-industrial-3",
    }
    assert len(filas) == 2


def test_fetch_all_excluye_urls_ya_conocidas():
    llamadas_detalle = []

    def side_effect(url, **kwargs):
        if "sitemap" in url:
            return _resp(SITEMAP_XML)
        llamadas_detalle.append(url)
        return _resp(HTML_DETALLE)

    conocida = "https://www.trabajando.cl/ofertas/cajero-supermercado-1"
    with patch("requests.get", side_effect=side_effect):
        fuente_trabajando.fetch_all(["cajero"], excluir_urls={conocida})
    assert llamadas_detalle == []


def test_fetch_all_respeta_el_cap():
    sitemap_grande = "<urlset>" + "".join(
        f"<url><loc>https://www.trabajando.cl/ofertas/cajero-{i}</loc></url>"
        for i in range(10)
    ) + "</urlset>"

    def side_effect(url, **kwargs):
        return _resp(sitemap_grande) if "sitemap" in url else _resp(HTML_DETALLE)

    with patch("requests.get", side_effect=side_effect):
        filas, _, _ = fuente_trabajando.fetch_all(["cajero"], cap=3)
    assert len(filas) == 3


def test_fetch_all_error_de_sitemap_no_interrumpe():
    with patch("requests.get", side_effect=ConnectionError("timeout")):
        filas, vigentes, error = fuente_trabajando.fetch_all(["cajero"])
    assert filas == []
    assert vigentes == set()
    assert error is not None
```

Crear `tests/test_fuente_laborum.py` (mismos casos, apuntando a `fuente_laborum` y URLs `laborum.cl`):

```python
# -*- coding: utf-8 -*-
from unittest.mock import MagicMock, patch

import fuente_laborum

SITEMAP_XML = """<?xml version="1.0"?>
<urlset>
  <url><loc>https://www.laborum.cl/empleos/cajero-supermercado-1</loc></url>
  <url><loc>https://www.laborum.cl/empleos/desarrollador-web-2</loc></url>
</urlset>
"""

HTML_DETALLE = """
<script type="application/ld+json">
{"@type": "JobPosting", "title": "Cajero/a", "description": "<p>Texto</p>",
 "hiringOrganization": {"name": "Empresa X"}}
</script>
"""


def _resp(text, status=200):
    r = MagicMock()
    r.status_code = status
    r.text = text
    r.raise_for_status = MagicMock()
    return r


def test_fetch_all_filtra_por_los_terminos_recibidos():
    def side_effect(url, **kwargs):
        return _resp(SITEMAP_XML) if "sitemap" in url else _resp(HTML_DETALLE)

    with patch("requests.get", side_effect=side_effect):
        filas, vigentes, error = fuente_laborum.fetch_all(["cajero"])
    assert vigentes == {"https://www.laborum.cl/empleos/cajero-supermercado-1"}
    assert len(filas) == 1


def test_fetch_all_excluye_urls_ya_conocidas():
    llamadas_detalle = []

    def side_effect(url, **kwargs):
        if "sitemap" in url:
            return _resp(SITEMAP_XML)
        llamadas_detalle.append(url)
        return _resp(HTML_DETALLE)

    conocida = "https://www.laborum.cl/empleos/cajero-supermercado-1"
    with patch("requests.get", side_effect=side_effect):
        fuente_laborum.fetch_all(["cajero"], excluir_urls={conocida})
    assert llamadas_detalle == []


def test_fetch_all_error_de_sitemap_no_interrumpe():
    with patch("requests.get", side_effect=ConnectionError("timeout")):
        filas, vigentes, error = fuente_laborum.fetch_all(["cajero"])
    assert filas == []
    assert error is not None
```

- [ ] **Step 2: Correr la prueba y verificar que falla**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_fuente_trabajando.py tests/test_fuente_laborum.py -v
```

Esperado: FAIL con `ModuleNotFoundError`

- [ ] **Step 3: Implementar**

Crear `fuente_trabajando.py`:

```python
# -*- coding: utf-8 -*-
"""Fuente Trabajando.cl — sitemap de ofertas + datos estructurados JobPosting.

Estrategia: el sitemap lista miles de ofertas con slug descriptivo; se
filtran por los términos que pasa quien llama (desde `terminos_busqueda`,
no una lista fija al perfil) y se visitan solo las URLs nuevas."""
import re
import time

import requests

import jobposting

SITEMAP = "https://www.trabajando.cl/sitemap-ofertas.xml"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
           "Accept-Language": "es-CL,es;q=0.9"}

CAP_POR_CORRIDA = 120


def _slug_contiene_algun_termino(slug: str, terminos: list[str]) -> bool:
    palabras = [re.sub(r"\s+", "-", t.strip().lower()) for t in terminos]
    return any(p and p in slug for p in palabras)


def fetch_all(terminos: list[str], excluir_urls=None,
              cap: int = CAP_POR_CORRIDA) -> tuple[list[dict], set, str | None]:
    """Retorna (filas_nuevas, urls_vigentes, error_o_None).

    urls_vigentes: toda URL afín presente hoy en el sitemap (siga o no
    siendo nueva) — sirve para actualizar last_seen sin re-visitar cada
    página."""
    excluir_urls = excluir_urls or set()
    try:
        r = requests.get(SITEMAP, headers=HEADERS, timeout=30)
        r.raise_for_status()
        urls = re.findall(r"<loc>([^<]+)</loc>", r.text)
    except Exception as e:
        return [], set(), f"sitemap: {str(e)[:200]}"

    afines = [u for u in urls
              if _slug_contiene_algun_termino(u.rsplit("/", 1)[-1], terminos)]
    candidatas = [u for u in afines if u not in excluir_urls][:cap]
    filas, error = [], None
    for u in candidatas:
        try:
            det = requests.get(u, headers=HEADERS, timeout=25)
            d = jobposting.extraer(det.text)
            if d:
                filas.append(jobposting.a_fila(d, u, "trabajando"))
        except Exception as e:
            error = str(e)[:200]
        time.sleep(0.6)
    print(f"[OK] trabajando: {len(filas)} ofertas nuevas "
          f"({len(afines)} afines vigentes en el sitemap)")
    return filas, set(afines), error
```

Crear `fuente_laborum.py`:

```python
# -*- coding: utf-8 -*-
"""Fuente Laborum.cl — sitemap de avisos + JobPosting (JSON-LD).

Mismo enfoque que `fuente_trabajando.py`: los términos vienen de
`terminos_busqueda`, no de una lista fija al perfil."""
import re
import time

import requests

import jobposting

SITEMAP = "https://www.laborum.cl/sitemap_avisos_bum.xml"
HEADERS = {"User-Agent":
           "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"}

CAP_POR_CORRIDA = 100


def _slug_contiene_algun_termino(slug: str, terminos: list[str]) -> bool:
    palabras = [re.sub(r"\s+", "-", t.strip().lower()) for t in terminos]
    return any(p and p in slug for p in palabras)


def fetch_all(terminos: list[str], excluir_urls=None,
              cap: int = CAP_POR_CORRIDA) -> tuple[list[dict], set, str | None]:
    excluir_urls = excluir_urls or set()
    try:
        r = requests.get(SITEMAP, headers=HEADERS, timeout=30)
        r.raise_for_status()
        urls = re.findall(r"<loc>([^<]+)</loc>", r.text)
    except Exception as e:
        return [], set(), f"sitemap: {str(e)[:200]}"

    afines = [u for u in urls
              if _slug_contiene_algun_termino(u.rsplit("/", 1)[-1], terminos)]
    candidatas = [u for u in afines if u not in excluir_urls][:cap]
    filas, error = [], None
    for u in candidatas:
        try:
            det = requests.get(u, headers=HEADERS, timeout=25)
            d = jobposting.extraer(det.text)
            if d:
                filas.append(jobposting.a_fila(d, u, "laborum"))
        except Exception as e:
            error = str(e)[:200]
        time.sleep(0.6)
    print(f"[OK] laborum: {len(filas)} ofertas nuevas "
          f"({len(afines)} afines vigentes en el sitemap)")
    return filas, set(afines), error
```

- [ ] **Step 4: Correr las pruebas y verificar que pasan**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_fuente_trabajando.py tests/test_fuente_laborum.py -v
```

Esperado: 8 passed (5 de trabajando + 3 de laborum)

- [ ] **Step 5: Commit**

```bash
git add fuente_trabajando.py fuente_laborum.py tests/test_fuente_trabajando.py tests/test_fuente_laborum.py
git commit -m "feat: fuentes Trabajando y Laborum, filtro por términos desde la base"
```

---

### Task 5: Áreas y vigencia en el motor

Dos piezas que faltan en `motor/` para poder llenar `oferta_analisis`
completo: un clasificador de áreas (multi-rubro, como el catálogo de
habilidades — no solo industria/procesos) y una estimación de vigencia.
Ambas puras, sin base de datos ni red, siguiendo la misma disciplina que el
resto de `motor/`.

**Files:**
- Create: `motor/areas.py`
- Modify: `motor/atributos.py`
- Test: `tests/test_areas.py`
- Test: `tests/test_atributos.py` (se extiende)

**Interfaces:**
- Consumes: `motor.texto.normalizar`
- Produces:
  - `motor.areas.CATALOGO_AREAS: dict[str, str]`
  - `motor.areas.clasificar(texto) -> list[str]` — una o más áreas, o
    `["Otra/Sin clasificar"]` si ninguna calza
  - `motor.atributos.vigencia(date_posted, last_seen, hoy: date, ultima_corrida: str | None, ventana: int = 30) -> dict`
    — `{"dias_publicada", "dias_restantes_est", "estado"}`

- [ ] **Step 1: Escribir la prueba que falla**

Crear `tests/test_areas.py`:

```python
# -*- coding: utf-8 -*-
from motor.areas import CATALOGO_AREAS, clasificar


def test_clasifica_ventas_y_retail():
    assert "Ventas y retail" in clasificar("Se busca cajero para supermercado")


def test_clasifica_administracion():
    assert "Administración" in clasificar("Asistente contable, manejo de facturación")


def test_clasifica_tecnologia():
    assert "Tecnología y datos" in clasificar("Desarrollador Python, SQL")


def test_clasifica_oficios_y_construccion():
    assert "Oficios y construcción" in clasificar("Soldador con experiencia en planos")


def test_clasifica_salud_y_educacion():
    assert "Salud y educación" in clasificar("TENS para clínica")


def test_sin_calce_da_otra_sin_clasificar():
    assert clasificar("xyz sin ninguna coincidencia") == ["Otra/Sin clasificar"]


def test_puede_calzar_mas_de_un_area():
    areas = clasificar("Analista de ventas con manejo de Excel y Power BI")
    assert len(areas) >= 1  # al menos una calza; no exige exclusividad


def test_catalogo_cubre_varios_rubros():
    assert len(CATALOGO_AREAS) >= 8
```

Agregar a `tests/test_atributos.py`:

```python
def test_vigencia_activa_dentro_de_la_ventana():
    from datetime import date
    resultado = vigencia("2026-07-01", "2026-07-20", date(2026, 7, 20),
                         "2026-07-20", ventana=30)
    assert resultado["estado"] == "activa"
    assert resultado["dias_publicada"] == 19


def test_vigencia_por_vencer_cerca_del_limite():
    from datetime import date
    resultado = vigencia("2026-07-01", "2026-07-25", date(2026, 7, 25),
                         "2026-07-25", ventana=30)
    assert resultado["estado"] == "por_vencer"


def test_vigencia_probablemente_cerrada_si_no_aparecio_en_la_ultima_corrida():
    from datetime import date
    # last_seen es anterior a la última corrida completa: no se vio hoy
    resultado = vigencia("2026-07-01", "2026-07-10", date(2026, 7, 25),
                         "2026-07-25", ventana=30)
    assert resultado["estado"] == "probablemente_cerrada"


def test_vigencia_sin_fecha_publicada():
    from datetime import date
    resultado = vigencia(None, "2026-07-25", date(2026, 7, 25), "2026-07-25")
    assert resultado["estado"] == "sin_fecha"
    assert resultado["dias_publicada"] is None


def test_vigencia_sin_ultima_corrida_no_marca_cerrada():
    from datetime import date
    resultado = vigencia("2026-07-01", "2026-07-20", date(2026, 7, 20), None)
    assert resultado["estado"] == "activa"
```

Y agregar el import correspondiente al inicio de `tests/test_atributos.py`:
```python
from motor.atributos import vigencia
```
(junto a los imports ya existentes de `anios_experiencia`, `ingles_excluyente`, etc.)

- [ ] **Step 2: Correr la prueba y verificar que falla**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_areas.py tests/test_atributos.py -v
```

Esperado: FAIL — `ModuleNotFoundError: No module named 'motor.areas'` y
`ImportError: cannot import name 'vigencia'`

- [ ] **Step 3: Implementar**

Crear `motor/areas.py`:

```python
# -*- coding: utf-8 -*-
"""Clasificador de áreas ocupacionales. Multi-rubro, como el catálogo de
habilidades — no solo industria/procesos. Un aviso puede calzar con más de
un área; si no calza con ninguna, es "Otra/Sin clasificar"."""
import re

from motor.texto import normalizar

CATALOGO_AREAS = {
    "Ventas y retail": r"venta|vendedor|cajero|reponedor|retail|tienda",
    "Administración": r"administrativ|contable|facturacion|recepcion|"
                       r"remuneraciones|rrhh|recursos humanos",
    "Logística y transporte": r"bodega|logistic|conductor|despacho|"
                               r"transporte|reparto|picking",
    "Servicios": r"guardia|seguridad|aseo|limpieza|garzon|cocinero|"
                 r"gastronomia|hoteleria",
    "Salud y educación": r"tens|enfermer|medic|salud|profesor|docente|"
                          r"educadora|parvulo|colegio",
    "Construcción y oficios": r"maestro|electric|soldador|gasfiter|obra|"
                               r"construccion|planos|albanil",
    "Industria": r"operario|produccion|mantenimiento|mantencion|"
                 r"supervisor de produccion|planta|maquinaria",
    "Tecnología y datos": r"desarrollador|programador|software|sql|python|"
                           r"power ?bi|analista de datos|soporte ti|"
                           r"help ?desk",
    "Atención al cliente": r"call ?center|atencion al cliente|telemarketing",
}

_COMPILADO = {nombre: re.compile(patron) for nombre, patron in CATALOGO_AREAS.items()}


def clasificar(texto) -> list[str]:
    normalizado = normalizar(texto)
    encontradas = [n for n, p in _COMPILADO.items() if p.search(normalizado)]
    return encontradas or ["Otra/Sin clasificar"]
```

Agregar a `motor/atributos.py` (al final del archivo):

```python
def vigencia(date_posted, last_seen, hoy, ultima_corrida: str | None,
            ventana: int = 30) -> dict:
    """Estado estimado de una oferta y días de vigencia restante.

    "probablemente_cerrada": la oferta no apareció en la última corrida
    completa de recolección (su last_seen es anterior), lo que sugiere que
    ya no está publicada aunque siga en la base."""
    posted = _parse_fecha_iso(date_posted)
    seen = _parse_fecha_iso(last_seen)
    corrida = _parse_fecha_iso(ultima_corrida) if ultima_corrida else None
    out = {"dias_publicada": None, "dias_restantes_est": None, "estado": "sin_fecha"}
    if seen and corrida and seen < corrida:
        out["estado"] = "probablemente_cerrada"
        if posted:
            out["dias_publicada"] = (hoy - posted).days
        return out
    if not posted:
        return out
    dias = (hoy - posted).days
    restantes = max(0, ventana - dias)
    out.update(
        dias_publicada=dias,
        dias_restantes_est=restantes,
        estado="por_vencer" if restantes <= 7 else "activa",
    )
    return out


def _parse_fecha_iso(s):
    from datetime import date as _date
    if not s:
        return None
    try:
        return _date.fromisoformat(str(s)[:10])
    except ValueError:
        return None
```

- [ ] **Step 4: Correr las pruebas y verificar que pasan**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_areas.py tests/test_atributos.py -v
```

Esperado: `test_areas.py` 8 passed; `test_atributos.py` 27 passed (22
existentes + 5 nuevas de vigencia)

- [ ] **Step 5: Correr la suite completa**

```powershell
.venv\Scripts\python.exe -m pytest tests -v
```

Esperado: 151 passed (109 de antes de este plan + 10 de jobposting + 6 de
getonbrd + 5 de computrabajo + 8 de trabajando/laborum + 8 de areas + 5
nuevas de vigencia en atributos)

- [ ] **Step 6: Commit**

```bash
git add motor/areas.py motor/atributos.py tests/test_areas.py tests/test_atributos.py
git commit -m "feat: clasificador de áreas y estimación de vigencia en el motor"
```

---

### Task 6: Analizador genérico

Corre el motor sobre las ofertas ya guardadas y escribe `oferta_analisis`.
Reemplaza a `analyze.py` del proyecto de referencia, pero sin nada
dependiente de un perfil: ni match, ni `cargo_no_afin`, ni descarte de
rubro.

**Files:**
- Create: `analizar.py`
- Test: `tests/test_analizar.py`

**Interfaces:**
- Consumes: `db.engine`, `db.ensure_schema`, `db.consultar`,
  `db.upsert_oferta_analisis`, `motor.habilidades.detectar`,
  `motor.areas.clasificar`, `motor.atributos.region/modalidad/`
  `tipo_contrato/anios_experiencia/ingles_excluyente/vigencia`,
  `motor.texto.normalizar`
- Produces:
  - `run(eng, db_path=None) -> dict` — resumen: `{"analizadas": int,
    "duplicadas": int}`

- [ ] **Step 1: Escribir la prueba que falla**

Crear `tests/test_analizar.py`:

```python
# -*- coding: utf-8 -*-
import json

import analizar
import db


def _con_ofertas(eng, filas):
    db.ensure_schema(eng)
    for f in filas:
        base = dict(job_url="", site="trabajando", search_term="", title="",
                    company="", location="Chile", date_posted=None,
                    job_type=None, is_remote="False", min_amount=None,
                    max_amount=None, currency=None, interval=None,
                    description="", scrape_date="2026-08-01", last_seen="2026-08-01")
        base.update(f)
        cols = list(base)
        vals = ", ".join(f":{c}" for c in cols)
        colsql = ", ".join(f'"{c}"' for c in cols)
        db.ejecutar(eng, f"INSERT INTO ofertas ({colsql}) VALUES ({vals})", base)


def test_run_escribe_analisis_generico(tmp_path):
    eng = db.engine(tmp_path / "a.db")
    _con_ofertas(eng, [{
        "job_url": "http://x/1", "title": "Cajero", "company": "Super X",
        "description": "Se busca cajero, manejo de caja.", "date_posted": "2026-07-30",
    }])
    resumen = analizar.run(eng)
    assert resumen["analizadas"] == 1
    filas = db.consultar(eng, "SELECT habilidades, areas, region FROM oferta_analisis"
                              " WHERE job_url = 'http://x/1'")
    habilidades, areas, region = filas[0]
    assert "Manejo de caja" in json.loads(habilidades)
    assert "Ventas y retail" in json.loads(areas)


def test_run_no_escribe_columnas_dependientes_de_perfil(tmp_path):
    eng = db.engine(tmp_path / "a2.db")
    _con_ofertas(eng, [{"job_url": "http://x/1", "title": "Cajero",
                        "company": "X", "description": "Se busca cajero"}])
    analizar.run(eng)
    from sqlalchemy import inspect
    columnas = {c["name"] for c in inspect(eng).get_columns("oferta_analisis")}
    assert columnas.isdisjoint({"match", "cargo_no_afin", "electrico", "detalle"})


def test_run_marca_duplicadas_por_titulo_y_empresa(tmp_path):
    eng = db.engine(tmp_path / "a3.db")
    _con_ofertas(eng, [
        {"job_url": "http://x/1", "site": "trabajando", "title": "Cajero/a",
         "company": "Super X", "description": "texto", "scrape_date": "2026-07-01"},
        {"job_url": "http://x/2", "site": "computrabajo", "title": "CAJERO/A",
         "company": "super x", "description": "texto", "scrape_date": "2026-07-02"},
    ])
    resumen = analizar.run(eng)
    assert resumen["duplicadas"] == 1
    fila1 = db.consultar(eng, "SELECT duplicada FROM oferta_analisis"
                              " WHERE job_url = 'http://x/1'")[0][0]
    fila2 = db.consultar(eng, "SELECT duplicada FROM oferta_analisis"
                              " WHERE job_url = 'http://x/2'")[0][0]
    assert fila1 == 0  # se queda con la primera capturada (scrape_date más antiguo)
    assert fila2 == 1


def test_run_calcula_vigencia_con_ultima_corrida_global(tmp_path):
    eng = db.engine(tmp_path / "a4.db")
    _con_ofertas(eng, [{
        "job_url": "http://x/1", "title": "Cajero", "company": "X",
        "description": "texto", "date_posted": "2026-07-25",
        "last_seen": "2026-08-01",  # coincide con la corrida más reciente
    }])
    analizar.run(eng)
    vigencia = json.loads(db.consultar(
        eng, "SELECT vigencia_estimada FROM oferta_analisis"
             " WHERE job_url = 'http://x/1'")[0][0])
    assert vigencia["estado"] in ("activa", "por_vencer")


def test_run_sin_ofertas_da_resumen_vacio(tmp_path):
    eng = db.engine(tmp_path / "a5.db")
    db.ensure_schema(eng)
    resumen = analizar.run(eng)
    assert resumen == {"analizadas": 0, "duplicadas": 0}


def test_run_es_atomico_no_deja_tabla_a_medio_escribir(tmp_path):
    # Reusa la garantía ya probada de db.upsert_oferta_analisis: si algo
    # falla, no debe quedar una fila a medias. Se corre dos veces seguidas
    # para confirmar que es idempotente (no duplica ni falla la segunda vez).
    eng = db.engine(tmp_path / "a6.db")
    _con_ofertas(eng, [{"job_url": "http://x/1", "title": "Cajero",
                        "company": "X", "description": "texto"}])
    analizar.run(eng)
    analizar.run(eng)
    assert db.escalar(eng, "SELECT COUNT(*) FROM oferta_analisis") == 1
```

- [ ] **Step 2: Correr la prueba y verificar que falla**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_analizar.py -v
```

Esperado: FAIL con `ModuleNotFoundError: No module named 'analizar'`

- [ ] **Step 3: Implementar**

Crear `analizar.py`:

```python
# -*- coding: utf-8 -*-
"""Analiza las ofertas guardadas y escribe `oferta_analisis`.

Todo lo que calcula es genérico —no depende de ningún perfil—: habilidades,
áreas, región, modalidad, tipo de contrato, años pedidos, inglés
excluyente, si es duplicada, y vigencia estimada. El puntaje contra un
perfil se calcula al vuelo en una capa posterior (la app), con
motor.puntaje.puntuar."""
import json
from datetime import date

from motor.atributos import (anios_experiencia, ingles_excluyente, modalidad,
                             region, tipo_contrato, vigencia)
from motor.areas import clasificar as clasificar_areas
from motor.habilidades import detectar
from motor.texto import normalizar

import db


def run(eng, db_path=None) -> dict:
    db.ensure_schema(eng)
    filas_ofertas = db.consultar(eng, "SELECT job_url, site, title, company,"
                                      " location, date_posted, is_remote,"
                                      " description, scrape_date, last_seen"
                                      " FROM ofertas")
    if not filas_ofertas:
        return {"analizadas": 0, "duplicadas": 0}

    hoy = date.today()
    ultima_corrida = max(
        (f[8] for f in filas_ofertas if f[8]), default=hoy.isoformat())

    # Deduplicación por contenido: misma oferta publicada varias veces
    # (distinto link o distinta fuente). Se conserva la primera capturada.
    ordenadas = sorted(filas_ofertas, key=lambda f: (f[8] or "", f[0]))
    vistas_clave = set()
    duplicada_por_url = {}
    for f in ordenadas:
        job_url, _, title, company = f[0], f[1], f[2], f[3]
        clave = f"{normalizar(title)}|{normalizar(company)}"
        duplicada_por_url[job_url] = clave in vistas_clave
        vistas_clave.add(clave)

    filas_analisis = []
    for f in filas_ofertas:
        (job_url, site, title, company, location, date_posted, is_remote,
         description, scrape_date, last_seen) = f
        texto_completo = f"{title} {company} {description}"
        habilidades = detectar(texto_completo)
        areas = clasificar_areas(texto_completo)
        es_remoto = str(is_remote).lower() == "true"
        vig = vigencia(date_posted, last_seen, hoy, ultima_corrida)
        filas_analisis.append({
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
        })

    db.upsert_oferta_analisis(eng, filas_analisis)

    return {
        "analizadas": len(filas_analisis),
        "duplicadas": sum(1 for v in duplicada_por_url.values() if v),
    }


if __name__ == "__main__":
    eng = db.engine()
    resumen = run(eng)
    print(f"Ofertas analizadas: {resumen['analizadas']} "
          f"(duplicadas: {resumen['duplicadas']})")
```

- [ ] **Step 4: Correr las pruebas y verificar que pasan**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_analizar.py -v
```

Esperado: 6 passed

- [ ] **Step 5: Commit**

```bash
git add analizar.py tests/test_analizar.py
git commit -m "feat: analizador genérico de ofertas, sin nada dependiente de perfil"
```

---

### Task 7: Orquestador de recolección

Junta todo: reparte un presupuesto de tiempo entre los términos
pendientes (en el orden de prioridad que ya calcula
`db.terminos_pendientes`), llama a las cuatro fuentes, guarda lo nuevo,
registra la corrida de cada término, y llama al analizador al final.

**Files:**
- Create: `recolectar.py`
- Test: `tests/test_recolectar.py`

**Interfaces:**
- Consumes: `db.terminos_pendientes`, `db.registrar_corrida_termino`,
  `db.upsert_ofertas`, `db.ensure_schema`, `db.engine`, `analizar.run`,
  las cuatro `fuente_*.fetch_all`
- Produces:
  - `run(eng, presupuesto_segundos: int = 2700, db_path=None) -> dict` —
    resumen: `{"terminos_corridos": int, "ofertas_nuevas": int,
    "analizadas": int}`

- [ ] **Step 1: Escribir la prueba que falla**

Crear `tests/test_recolectar.py`:

```python
# -*- coding: utf-8 -*-
from unittest.mock import patch

import db
import recolectar

COLUMNAS_OFERTA = ("job_url", "site", "search_term", "title", "company",
                   "location", "date_posted", "job_type", "is_remote",
                   "min_amount", "max_amount", "currency", "interval",
                   "description", "scrape_date")


def _fila_falsa(url, termino):
    return {"job_url": url, "site": "getonbrd", "search_term": termino,
            "title": "Cajero", "company": "X", "location": "Chile",
            "date_posted": "2026-08-01", "job_type": None,
            "is_remote": "False", "min_amount": None, "max_amount": None,
            "currency": None, "interval": None, "description": "texto",
            "scrape_date": "2026-08-01"}


def test_run_consulta_terminos_pendientes_y_corre_las_cuatro_fuentes(tmp_path):
    eng = db.engine(tmp_path / "r.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "cajero", "usuario", "2026-08-01T00:00:00")

    with patch("fuente_getonbrd.fetch_all",
               return_value=([_fila_falsa("http://gb/1", "cajero")], set(), None)) as m_gb, \
         patch("fuente_computrabajo.fetch_all",
               return_value=([], set(), None)) as m_ct, \
         patch("fuente_trabajando.fetch_all",
               return_value=([], set(), None)) as m_tb, \
         patch("fuente_laborum.fetch_all",
               return_value=([], set(), None)) as m_lb, \
         patch("analizar.run", return_value={"analizadas": 0, "duplicadas": 0}):
        resumen = recolectar.run(eng)

    m_gb.assert_called_once()
    m_ct.assert_called_once()
    m_tb.assert_called_once()
    m_lb.assert_called_once()
    assert resumen["terminos_corridos"] == 1
    assert resumen["ofertas_nuevas"] == 1


def test_run_guarda_las_ofertas_encontradas(tmp_path):
    eng = db.engine(tmp_path / "r2.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "cajero", "usuario", "2026-08-01T00:00:00")

    with patch("fuente_getonbrd.fetch_all",
               return_value=([_fila_falsa("http://gb/1", "cajero")], set(), None)), \
         patch("fuente_computrabajo.fetch_all", return_value=([], set(), None)), \
         patch("fuente_trabajando.fetch_all", return_value=([], set(), None)), \
         patch("fuente_laborum.fetch_all", return_value=([], set(), None)), \
         patch("analizar.run", return_value={"analizadas": 1, "duplicadas": 0}):
        recolectar.run(eng)

    assert db.escalar(eng, "SELECT COUNT(*) FROM ofertas") == 1


def test_run_registra_la_corrida_de_cada_termino(tmp_path):
    eng = db.engine(tmp_path / "r3.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "cajero", "usuario", "2026-08-01T00:00:00")

    with patch("fuente_getonbrd.fetch_all",
               return_value=([_fila_falsa("http://gb/1", "cajero")], set(), None)), \
         patch("fuente_computrabajo.fetch_all", return_value=([], set(), None)), \
         patch("fuente_trabajando.fetch_all", return_value=([], set(), None)), \
         patch("fuente_laborum.fetch_all", return_value=([], set(), None)), \
         patch("analizar.run", return_value={"analizadas": 1, "duplicadas": 0}):
        recolectar.run(eng)

    fila = db.consultar(eng, "SELECT ultima_corrida, ofertas_ultimas"
                             " FROM terminos_busqueda WHERE termino = 'cajero'")[0]
    assert fila[0] is not None
    assert fila[1] == 1


def test_run_corta_por_presupuesto_de_tiempo(tmp_path):
    eng = db.engine(tmp_path / "r4.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "termino1", "usuario", "2026-08-01T00:00:00")
    db.agregar_termino(eng, "termino2", "usuario", "2026-08-01T00:00:00")

    llamados = []

    def fake_getonbrd(terminos, **kwargs):
        llamados.append(terminos[0] if terminos else None)
        return [], set(), None

    with patch("fuente_getonbrd.fetch_all", side_effect=fake_getonbrd), \
         patch("fuente_computrabajo.fetch_all", return_value=([], set(), None)), \
         patch("fuente_trabajando.fetch_all", return_value=([], set(), None)), \
         patch("fuente_laborum.fetch_all", return_value=([], set(), None)), \
         patch("analizar.run", return_value={"analizadas": 0, "duplicadas": 0}), \
         patch("time.monotonic", side_effect=[0, 0, 100, 100, 9999]):
        # El segundo chequeo de tiempo (100s) ya no debe alcanzar para un
        # presupuesto de 50s: solo se corre el primer término.
        resumen = recolectar.run(eng, presupuesto_segundos=50)

    assert resumen["terminos_corridos"] == 1


def test_run_sin_terminos_pendientes_no_falla(tmp_path):
    eng = db.engine(tmp_path / "r5.db")
    db.ensure_schema(eng)
    with patch("analizar.run", return_value={"analizadas": 0, "duplicadas": 0}):
        resumen = recolectar.run(eng)
    assert resumen["terminos_corridos"] == 0


def test_run_llama_al_analizador_al_final(tmp_path):
    eng = db.engine(tmp_path / "r6.db")
    db.ensure_schema(eng)
    with patch("analizar.run", return_value={"analizadas": 3, "duplicadas": 1}) as m:
        resumen = recolectar.run(eng)
    m.assert_called_once()
    assert resumen["analizadas"] == 3
```

- [ ] **Step 2: Correr la prueba y verificar que falla**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_recolectar.py -v
```

Esperado: FAIL con `ModuleNotFoundError: No module named 'recolectar'`

- [ ] **Step 3: Implementar**

Crear `recolectar.py`:

```python
# -*- coding: utf-8 -*-
"""Orquestador de recolección: reparte un presupuesto de tiempo entre los
términos pendientes, en el orden de prioridad de `db.terminos_pendientes`.

Un término por iteración —no un lote grande al inicio— para que el
presupuesto de tiempo pueda cortar la corrida entre términos sin dejar
trabajo a medias en ninguna tabla (cada oferta se guarda con upserts
atómicos, así que cortar entre términos nunca deja la base inconsistente).
"""
import time
from datetime import datetime, timezone

import analizar
import db
import fuente_computrabajo
import fuente_getonbrd
import fuente_laborum
import fuente_trabajando

PRESUPUESTO_SEGUNDOS_DEFECTO = 45 * 60

FUENTES = (
    ("getonbrd", fuente_getonbrd),
    ("computrabajo", fuente_computrabajo),
    ("trabajando", fuente_trabajando),
    ("laborum", fuente_laborum),
)

COLUMNAS_OFERTA = ("job_url", "site", "search_term", "title", "company",
                   "location", "date_posted", "job_type", "is_remote",
                   "min_amount", "max_amount", "currency", "interval",
                   "description", "scrape_date", "last_seen")


def run(eng, presupuesto_segundos: int = PRESUPUESTO_SEGUNDOS_DEFECTO,
        db_path=None) -> dict:
    db.ensure_schema(eng)
    hoy = datetime.now(timezone.utc).replace(tzinfo=None).date().isoformat()
    ahora_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    terminos = db.terminos_pendientes(eng)
    inicio = time.monotonic()
    terminos_corridos = 0
    ofertas_nuevas = 0
    conocidas = {f["job_url"] for f in db.cargar_ofertas(eng)}

    for termino in terminos:
        if time.monotonic() - inicio > presupuesto_segundos:
            break

        total_termino = 0
        for _nombre_fuente, modulo in FUENTES:
            # `modulo.fetch_all` se resuelve recién acá, no al construir
            # FUENTES: si se guardara la función ya resuelta en la tupla,
            # unittest.mock.patch("fuente_x.fetch_all", ...) en las
            # pruebas no tendría efecto — patch reemplaza el atributo en
            # el módulo, pero una referencia capturada al importar ya
            # apunta a la función vieja. Late binding real de Python.
            try:
                filas, _vigentes, _error = modulo.fetch_all([termino], excluir_urls=conocidas)
            except Exception:
                filas = []
            if filas:
                for f in filas:
                    f.setdefault("scrape_date", hoy)
                    f.setdefault("last_seen", hoy)
                columnas = [c for c in COLUMNAS_OFERTA if c in filas[0]]
                insertadas = db.upsert_ofertas(eng, filas, columnas)
                ofertas_nuevas += insertadas
                total_termino += insertadas
                conocidas |= {f["job_url"] for f in filas}

        db.registrar_corrida_termino(eng, termino, total_termino, ahora_iso)
        terminos_corridos += 1

    resumen_analisis = analizar.run(eng)

    return {
        "terminos_corridos": terminos_corridos,
        "ofertas_nuevas": ofertas_nuevas,
        "analizadas": resumen_analisis["analizadas"],
    }


if __name__ == "__main__":
    eng = db.engine()
    resumen = run(eng)
    print(f"Términos corridos: {resumen['terminos_corridos']} | "
          f"Ofertas nuevas: {resumen['ofertas_nuevas']} | "
          f"Analizadas: {resumen['analizadas']}")
```

- [ ] **Step 4: Correr las pruebas y verificar que pasan**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_recolectar.py -v
```

Esperado: 6 passed

- [ ] **Step 5: Correr la suite completa del proyecto**

```powershell
.venv\Scripts\python.exe -m pytest tests -v
```

Esperado: 163 passed (151 al cierre de la Task 5 + 6 de analizar + 6 de
recolectar)

- [ ] **Step 6: Agregar `requests` a las dependencias**

Agregar a `requirements.txt`:

```
requests>=2.31
```

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

- [ ] **Step 7: Commit**

```bash
git add recolectar.py tests/test_recolectar.py requirements.txt
git commit -m "feat: orquestador de recolección con presupuesto de tiempo"
```

---

## Al terminar

Queda un pipeline completo: cuatro fuentes que consumen términos desde la
base (no una lista fija al perfil de nadie), un analizador que llena
`oferta_analisis` con el motor ya construido, y un orquestador que reparte
un presupuesto de ~45 minutos entre los términos pendientes en el orden de
prioridad ya calculado. Nada de esto calcula un puntaje contra un perfil —
eso sigue siendo trabajo de una capa posterior (la app), con
`motor.puntaje.puntuar`.

**Planes siguientes**, en orden (según el spec):

1. **App Streamlit** — pantalla de correo, formulario de perfil, pestañas
   (Ofertas para ti, Filtro avanzado, Tendencias, Empresas), marcas por
   usuario. Este plan es el primer consumidor real de `db.cargar_ofertas` +
   `db.cargar_usuario` + `motor.puntaje.puntuar`.
2. **Búsqueda en vivo** — scraping al registrarse con tope de 30 segundos y
   resultados parciales, usando las cuatro fuentes de este plan (solo
   Get on Board, Trabajando, Laborum y Computrabajo — nada de Indeed ni
   LinkedIn, que no forman parte de este proyecto).
3. **Despliegue** — GitHub Actions para correr `recolectar.py` en un
   horario fijo (equivalente al `actualizar.py` del proyecto de
   referencia), y la app en Streamlit Cloud.

## Pendiente de calibración

- `PRESUPUESTO_SEGUNDOS_DEFECTO = 45 * 60` en `recolectar.py` sale
  directo del spec, no de datos reales de cuánto tarda cada fuente. Ajustar
  una vez que haya corridas reales para medir.
- Las cuatro fuentes heredan los `time.sleep()` de cortesía del proyecto de
  referencia sin cambios — no están recalibrados para el volumen de
  términos que traerá la recolección mixta (base + usuarios). Si el
  catálogo de términos crece mucho, revisar si el presupuesto de tiempo
  alcanza para una rotación razonable.
- `motor/areas.py`'s `CATALOGO_AREAS` es un punto de partida, igual que el
  catálogo de habilidades — crece con lo que efectivamente aparezca en los
  avisos reales.
- La lista base de ~30 ocupaciones (mencionada en el spec, sección 3) no se
  carga en este plan. Falta un paso de seed inicial —insertar los
  primeros términos con `db.agregar_termino(eng, t, "base", ahora)`— antes
  de la primera corrida real; no hay nada que lo impida técnicamente, solo
  falta decidir la lista definitiva contra las categorías de los portales,
  como ya se explicó en el spec.
- **`recolectar.py` re-descarga el sitemap completo de Trabajando y
  Laborum una vez por cada término procesado en la corrida**, en vez de
  una sola vez por corrida. Esto pasa porque el orquestador llama a
  `fetch_all([termino])` dentro del bucle por término (necesario para
  cortar por presupuesto y registrar la corrida de cada término por
  separado), y esas dos fuentes hacen su propio fetch del sitemap dentro
  de `fetch_all`. No es un bug de corrección —los datos que trae siguen
  siendo correctos— pero es ancho de banda desperdiciado y, con muchos
  términos pendientes, un patrón de pedidos repetidos que podría leerse
  como abuso desde el lado del sitio. Arreglarlo bien requiere que
  `fetch_all` separe "traer y filtrar el sitemap" de "visitar el detalle
  de una URL", para poder cachear lo primero por corrida — pero atribuir
  cada oferta encontrada a UN término específico se vuelve ambiguo cuando
  el slug de una URL calza con varios términos a la vez (el diseño actual
  no necesita resolver esa ambigüedad porque re-filtra desde cero por
  término). Postergado hasta tener corridas reales que muestren cuánto
  pesa esto en la práctica frente al presupuesto de 45 minutos.
