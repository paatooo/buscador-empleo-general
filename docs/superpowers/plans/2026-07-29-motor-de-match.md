# Motor de match "cargo primero" — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir el motor puro que puntúa una oferta de trabajo contra el
perfil de una persona, con el cargo como señal dominante, de modo que
funcione igual para un ingeniero que para un cajero.

**Architecture:** Un paquete `motor/` de funciones puras, sin base de datos,
sin red y sin Streamlit. Cinco módulos con una responsabilidad cada uno:
normalización de texto, afinidad de cargo, detección de habilidades,
extracción de atributos del aviso, y la combinación final del puntaje. Todo
se prueba con pytest sin levantar nada.

**Tech Stack:** Python 3.11+, biblioteca estándar únicamente (`re`,
`unicodedata`, `difflib`, `dataclasses`). pytest para las pruebas.

## Global Constraints

- **Proyecto independiente.** No importar, copiar ni depender de nada de
  `mapa-mercado-laboral`. Ese repo no se toca.
- **El motor es puro.** Ningún módulo de `motor/` puede importar SQLAlchemy,
  Streamlit, requests ni tocar disco.
- **Sin dependencias nuevas.** Solo biblioteca estándar. pytest es la única
  dependencia de desarrollo.
- **Las habilidades nunca anulan el puntaje.** Si un aviso no menciona
  ninguna habilidad detectable, el puntaje sigue siendo válido, sostenido en
  la afinidad de cargo. Este es el requisito central del spec.
- **El umbral de visibilidad se aplica sobre la afinidad de cargo sola,
  nunca sobre el puntaje final.**
- **El umbral vive en una sola constante**, marcada como provisional con un
  comentario, para calibrarla contra datos reales.
- **Nombres en español**, consistentes con el spec.

## Estructura de archivos

```
buscador-empleo-personalizado/
├── motor/
│   ├── __init__.py       exporta Perfil, Aviso, Puntaje, puntuar
│   ├── texto.py          normalizar(), tokens()
│   ├── cargo.py          afinidad() — la señal dominante
│   ├── habilidades.py    CATALOGO, detectar()
│   ├── atributos.py      region(), modalidad(), tipo_contrato(),
│   │                     anios_experiencia(), ingles_excluyente()
│   └── puntaje.py        Perfil, Aviso, Puntaje, puntuar()
├── tests/
│   ├── test_texto.py
│   ├── test_cargo.py
│   ├── test_habilidades.py
│   ├── test_atributos.py
│   └── test_puntaje.py
└── requirements-dev.txt
```

`texto.py` no depende de nadie. `cargo.py`, `habilidades.py` y
`atributos.py` dependen solo de `texto.py`. `puntaje.py` los combina. La
dependencia va en una sola dirección, sin ciclos.

---

### Task 1: Normalización de texto

Toda comparación posterior opera sobre texto normalizado. Sin esto,
"Cajero/a" y "cajero" son cadenas distintas.

**Files:**
- Create: `motor/__init__.py` (vacío por ahora)
- Create: `motor/texto.py`
- Create: `tests/test_texto.py`
- Create: `requirements-dev.txt`

**Interfaces:**
- Consumes: nada
- Produces:
  - `normalizar(s) -> str` — minúsculas, sin tildes, espacios colapsados
  - `tokens(s) -> list[str]` — palabras significativas del texto normalizado

- [ ] **Step 1: Crear el entorno y la estructura**

```powershell
cd "C:\Users\Pato\Claude code pruebas\buscador-empleo-personalizado"
python -m venv .venv
New-Item -ItemType Directory -Force motor, tests
if (-not (Test-Path motor\__init__.py)) { New-Item -ItemType File motor\__init__.py }
```

Crear `requirements-dev.txt`:

```
pytest>=8.0
```

Instalar:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

- [ ] **Step 2: Escribir la prueba que falla**

Crear `tests/test_texto.py`:

```python
from motor.texto import normalizar, tokens


def test_normalizar_quita_tildes_y_mayusculas():
    assert normalizar("Ingeniería QUÍMICA") == "ingenieria quimica"


def test_normalizar_colapsa_espacios():
    assert normalizar("  cajero   part  time ") == "cajero part time"


def test_normalizar_tolera_none():
    assert normalizar(None) == ""


def test_tokens_separa_por_no_alfanumerico():
    assert tokens("Cajero/a supermercado") == ["cajero", "supermercado"]


def test_tokens_descarta_palabras_vacias():
    assert tokens("ingeniero de procesos") == ["ingeniero", "procesos"]


def test_tokens_descarta_letras_sueltas():
    # la "a" de "Cajero/a" no aporta significado
    assert "a" not in tokens("Cajero/a")
```

- [ ] **Step 3: Correr la prueba y verificar que falla**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_texto.py -v
```

Esperado: FAIL con `ModuleNotFoundError: No module named 'motor.texto'`

- [ ] **Step 4: Implementar**

Crear `motor/texto.py`:

```python
# -*- coding: utf-8 -*-
"""Normalización de texto. Base de toda comparación del motor."""
import re
import unicodedata

# Palabras sin carga semántica para comparar cargos: aparecen en casi
# cualquier título y sumarían ruido a la afinidad.
VACIAS = {
    "de", "del", "la", "el", "los", "las", "y", "o", "en", "para", "con",
    "a", "un", "una", "por", "al", "e", "u",
}


def normalizar(s) -> str:
    """Minúsculas, sin tildes, espacios colapsados. None → cadena vacía."""
    texto = unicodedata.normalize("NFKD", str(s or "").lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).strip()


def tokens(s) -> list[str]:
    """Palabras significativas: sin vacías y sin letras sueltas."""
    crudos = re.findall(r"[a-z0-9]+", normalizar(s))
    return [t for t in crudos if t not in VACIAS and len(t) > 1]
```

- [ ] **Step 5: Correr las pruebas y verificar que pasan**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_texto.py -v
```

Esperado: 6 passed

- [ ] **Step 6: Commit**

```bash
git add motor/ tests/test_texto.py requirements-dev.txt
git commit -m "feat: normalización de texto y tokenización"
```

---

### Task 2: Afinidad de cargo

La señal dominante del motor. Decide si un aviso tiene algo que ver con lo
que la persona busca, antes de mirar habilidades.

**Files:**
- Create: `motor/cargo.py`
- Create: `tests/test_cargo.py`

**Interfaces:**
- Consumes: `motor.texto.tokens`
- Produces:
  - `afinidad(cargos_buscados: list[str], titulo: str) -> float` — 0.0 a 1.0
  - `UMBRAL_VISIBILIDAD: float` — bajo esto, el aviso no se muestra

- [ ] **Step 1: Escribir la prueba que falla**

Crear `tests/test_cargo.py`:

```python
from motor.cargo import UMBRAL_VISIBILIDAD, afinidad


def test_cargo_exacto_da_afinidad_maxima():
    assert afinidad(["cajero"], "Cajero/a supermercado turno tarde") == 1.0


def test_cargo_sin_relacion_da_cero():
    assert afinidad(["cajero"], "Ingeniero de Procesos Senior") == 0.0


def test_tolera_plural():
    # "cajeros" y "cajero" son el mismo cargo
    assert afinidad(["cajero"], "Se buscan cajeros") >= UMBRAL_VISIBILIDAD


def test_tolera_genero():
    # "cajera" y "cajero" también. Este caso obliga a que el umbral de
    # similitud entre palabras no pase de 0.80.
    assert afinidad(["cajero"], "Cajera de local") >= UMBRAL_VISIBILIDAD


def test_todas_las_palabras_del_cargo_cuentan():
    # "asistente contable" contra un título que solo trae "asistente":
    # media afinidad, no afinidad total
    valor = afinidad(["asistente contable"], "Asistente administrativo")
    assert 0.4 < valor < 0.75


def test_toma_el_mejor_de_varios_cargos_buscados():
    assert afinidad(["cajero", "ingeniero de procesos"],
                    "Ingeniero de Procesos") == 1.0


def test_sin_cargos_buscados_da_cero():
    assert afinidad([], "Cajero") == 0.0


def test_titulo_vacio_da_cero():
    assert afinidad(["cajero"], "") == 0.0
```

- [ ] **Step 2: Correr la prueba y verificar que falla**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_cargo.py -v
```

Esperado: FAIL con `ModuleNotFoundError: No module named 'motor.cargo'`

- [ ] **Step 3: Implementar**

Crear `motor/cargo.py`:

```python
# -*- coding: utf-8 -*-
"""Afinidad entre los cargos que busca una persona y el título de un aviso.

Es la señal dominante del motor: reemplaza la noción de "cargo afín"
codificada a un perfil concreto por una comparación que sale del perfil de
cada usuario.
"""
from difflib import SequenceMatcher

from motor.texto import tokens

# Bajo esta afinidad el aviso no se muestra: es ruido, no un match malo.
# Equivale a "al menos la mitad de las palabras significativas del cargo
# buscado aparecen en el título".
# PROVISIONAL: calibrar contra datos reales apenas haya usuarios.
UMBRAL_VISIBILIDAD = 0.5

# Dos palabras se consideran la misma por encima de esta similitud. Cubre
# plurales y género ("cajero"/"cajeros"/"cajera") sin emparejar palabras
# distintas que comparten letras. No subirlo a 0.85: ahí "cajero" y
# "cajera" quedan en 0.833 y dejan de calzar, que es justo lo que no
# queremos. "cajero" contra "ingeniero" da 0.4, muy lejos del umbral.
_UMBRAL_TOKEN = 0.80


def afinidad(cargos_buscados: list[str], titulo: str) -> float:
    """0.0 a 1.0. Se queda con el mejor de los cargos buscados."""
    del_titulo = tokens(titulo)
    if not cargos_buscados or not del_titulo:
        return 0.0
    return max(_afinidad_de_uno(tokens(c), del_titulo) for c in cargos_buscados)


def _afinidad_de_uno(del_cargo: list[str], del_titulo: list[str]) -> float:
    """Fracción de las palabras del cargo que aparecen en el título."""
    if not del_cargo:
        return 0.0
    encontradas = sum(_mejor_coincidencia(p, del_titulo) for p in del_cargo)
    return encontradas / len(del_cargo)


def _mejor_coincidencia(palabra: str, candidatas: list[str]) -> float:
    """1.0 si calza exacto; si no, la mejor similitud que supere el umbral."""
    mejor = 0.0
    for c in candidatas:
        if c == palabra:
            return 1.0
        similitud = SequenceMatcher(None, palabra, c).ratio()
        mejor = max(mejor, similitud)
    return mejor if mejor >= _UMBRAL_TOKEN else 0.0
```

- [ ] **Step 4: Correr las pruebas y verificar que pasan**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_cargo.py -v
```

Esperado: 8 passed

- [ ] **Step 5: Commit**

```bash
git add motor/cargo.py tests/test_cargo.py
git commit -m "feat: afinidad de cargo como señal dominante del match"
```

---

### Task 3: Catálogo y detección de habilidades

Refinamiento, no requisito. Un aviso sin habilidades detectables debe seguir
puntuando.

**Files:**
- Create: `motor/habilidades.py`
- Create: `tests/test_habilidades.py`

**Interfaces:**
- Consumes: `motor.texto.normalizar`
- Produces:
  - `CATALOGO: dict[str, str]` — nombre visible → patrón regex
  - `detectar(texto) -> list[str]` — habilidades presentes en el texto

- [ ] **Step 1: Escribir la prueba que falla**

Crear `tests/test_habilidades.py`:

```python
from motor.habilidades import CATALOGO, detectar


def test_detecta_habilidad_simple():
    assert "Excel" in detectar("Manejo de Excel nivel intermedio")


def test_detecta_sin_importar_tildes_ni_mayusculas():
    assert "Atención a público" in detectar("ATENCION A PUBLICO")


def test_no_detecta_lo_que_no_esta():
    assert "Soldadura" not in detectar("Manejo de Excel")


def test_aviso_sin_habilidades_devuelve_lista_vacia():
    assert detectar("Se busca persona responsable y puntual") == []


def test_catalogo_cubre_varios_rubros():
    # el motor debe servir más allá de perfiles industriales
    esperadas = {"Excel", "Manejo de caja", "Soldadura", "Atención a público"}
    assert esperadas.issubset(set(CATALOGO))


def test_todos_los_patrones_compilan():
    import re
    for nombre, patron in CATALOGO.items():
        re.compile(patron)  # lanza si el patrón está mal escrito
```

- [ ] **Step 2: Correr la prueba y verificar que falla**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_habilidades.py -v
```

Esperado: FAIL con `ModuleNotFoundError: No module named 'motor.habilidades'`

- [ ] **Step 3: Implementar**

Crear `motor/habilidades.py`:

```python
# -*- coding: utf-8 -*-
"""Catálogo de habilidades y su detección en el texto de un aviso.

Las habilidades refinan el puntaje, no lo determinan: un aviso que no
menciona ninguna sigue puntuando por afinidad de cargo. El catálogo cubre
varios rubros a propósito — el motor sirve a cualquier ocupación, no solo a
perfiles industriales. Crece con el uso.

Los patrones se evalúan sobre texto ya normalizado (minúsculas, sin tildes).
"""
import re

from motor.texto import normalizar

CATALOGO = {
    # Transversales
    "Excel": r"\bexcel\b",
    "Office": r"\boffice\b|word y excel",
    "Atención a público": r"atencion a (publico|clientes?)|servicio al cliente",
    "Trabajo en equipo": r"trabajo en equipo",
    "Inglés": r"\bingles\b|\benglish\b",
    "Licencia de conducir": r"licencia de conducir|licencia clase",
    # Comercio y retail
    "Manejo de caja": r"manejo de caja|caja registradora|cuadratura de caja",
    "Ventas": r"\bventas?\b|fuerza de venta",
    "Reposición": r"reposicion|reponedor",
    "Inventario": r"inventario|toma de inventario",
    # Administración y finanzas
    "Contabilidad": r"contabilidad|contable",
    "Facturación": r"facturacion|boletas? y facturas?",
    "Remuneraciones": r"remuneraciones|liquidaciones de sueldo",
    "SAP": r"\bsap\b",
    "ERP": r"\berp\b",
    # Datos y tecnología
    "SQL": r"\bsql\b",
    "Python": r"\bpython\b",
    "Power BI": r"power\s*bi",
    "Soporte TI": r"soporte (tecnico|ti)|mesa de ayuda|help ?desk",
    "Desarrollo web": r"desarrollo web|javascript|\breact\b|\bhtml\b",
    # Logística y transporte
    "Manejo de grúa horquilla": r"grua horquilla|montacargas",
    "Picking y packing": r"picking|packing|preparacion de pedidos",
    "Despacho": r"despacho|reparto|ultima milla",
    # Oficios y construcción
    "Soldadura": r"soldadura|soldador",
    "Electricidad": r"electricidad|instalaciones electricas|electrico",
    "Gasfitería": r"gasfiteria|gasfiter",
    "Lectura de planos": r"lectura de planos|interpretacion de planos",
    "AutoCAD": r"autocad",
    # Industria
    "Mantenimiento": r"mantenimiento|mantencion",
    "Operación de maquinaria": r"operacion de maquinaria|operar maquinas",
    "Mejora continua": r"mejora continua|\blean\b|six sigma|kaizen",
    "Control de calidad": r"control de calidad|aseguramiento de calidad",
    "ISO 9001": r"iso\s*9001",
    "Prevención de riesgos": r"prevencion de riesgos|\bsso\b|seguridad y salud",
    # Alimentación y servicios
    "Manipulación de alimentos": r"manipulacion de alimentos|resolucion sanitaria",
    "HACCP": r"haccp",
    "Cocina": r"\bcocina\b|cocinero|garzon",
    "Aseo y limpieza": r"\baseo\b|limpieza|sanitizacion",
    # Salud y educación
    "Cuidado de pacientes": r"cuidado de pacientes|atencion de pacientes",
    "Toma de signos vitales": r"signos vitales",
    "Planificación de clases": r"planificacion de clases|planificaciones",
}

_COMPILADO = {nombre: re.compile(patron) for nombre, patron in CATALOGO.items()}


def detectar(texto) -> list[str]:
    """Habilidades del catálogo presentes en el texto. Lista vacía si ninguna."""
    normalizado = normalizar(texto)
    return [n for n, p in _COMPILADO.items() if p.search(normalizado)]
```

- [ ] **Step 4: Correr las pruebas y verificar que pasan**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_habilidades.py -v
```

Esperado: 6 passed

- [ ] **Step 5: Commit**

```bash
git add motor/habilidades.py tests/test_habilidades.py
git commit -m "feat: catálogo multi-rubro de habilidades y su detección"
```

---

### Task 4: Atributos del aviso

Datos que se extraen del texto y no dependen de ningún perfil: dónde es, en
qué modalidad, qué contrato, cuántos años piden, si el inglés es excluyente.

**Files:**
- Create: `motor/atributos.py`
- Create: `tests/test_atributos.py`

**Interfaces:**
- Consumes: `motor.texto.normalizar`
- Produces:
  - `region(ubicacion) -> str` — nombre de región o `"Sin especificar"`
  - `modalidad(texto, es_remoto=None) -> str` — `"Remoto" | "Híbrido" | "Presencial" | "Sin especificar"`
  - `tipo_contrato(texto) -> str` — `"Indefinido" | "Plazo fijo" | "Part-time" | "Honorarios" | "No especificado"`
  - `anios_experiencia(texto) -> int | None` — `None` si el aviso no lo dice
  - `ingles_excluyente(texto) -> bool`

- [ ] **Step 1: Escribir la prueba que falla**

Crear `tests/test_atributos.py`:

```python
from motor.atributos import (anios_experiencia, ingles_excluyente, modalidad,
                             region, tipo_contrato)


def test_region_desde_ciudad():
    assert region("Antofagasta, Chile") == "Antofagasta"


def test_region_reconoce_comuna_de_santiago():
    assert region("Las Condes") == "Metropolitana"


def test_region_desconocida():
    assert region("Ciudad Inventada") == "Sin especificar"


def test_modalidad_remoto_por_bandera():
    assert modalidad("trabajo de oficina", es_remoto=True) == "Remoto"


def test_modalidad_hibrida_desde_texto():
    assert modalidad("modalidad hibrida, 3 dias presencial") == "Híbrido"


def test_modalidad_presencial_por_defecto_si_lo_dice():
    assert modalidad("trabajo 100% presencial") == "Presencial"


def test_contrato_part_time():
    assert tipo_contrato("Contrato part time fin de semana") == "Part-time"


def test_contrato_no_especificado():
    assert tipo_contrato("Buscamos personal") == "No especificado"


def test_anios_numero_explicito():
    assert anios_experiencia("Se requieren 3 años de experiencia") == 3


def test_anios_escritos_con_palabra():
    assert anios_experiencia("mínimo dos años de experiencia") == 2


def test_anios_toma_el_menor_de_un_rango():
    assert anios_experiencia("de 2 a 4 años de experiencia") == 2


def test_anios_ausente_es_none():
    # nunca penalizar por omisión
    assert anios_experiencia("Buscamos vendedor proactivo") is None


def test_ingles_excluyente_verdadero():
    assert ingles_excluyente("inglés avanzado excluyente") is True


def test_ingles_deseable_no_es_excluyente():
    assert ingles_excluyente("inglés deseable, no excluyente") is False


def test_sin_mencion_de_ingles():
    assert ingles_excluyente("Se busca cajero") is False
```

- [ ] **Step 2: Correr la prueba y verificar que falla**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_atributos.py -v
```

Esperado: FAIL con `ModuleNotFoundError: No module named 'motor.atributos'`

- [ ] **Step 3: Implementar**

Crear `motor/atributos.py`:

```python
# -*- coding: utf-8 -*-
"""Atributos que se leen del aviso y no dependen de ningún perfil.

Todo lo de acá se puede precalcular y guardar una sola vez por oferta,
compartido entre todos los usuarios.
"""
import re

from motor.texto import normalizar

_REGIONES = {
    "Arica y Parinacota": r"arica|parinacota",
    "Tarapacá": r"iquique|tarapaca|alto hospicio",
    "Antofagasta": r"antofagasta|calama|tocopilla|mejillones",
    "Atacama": r"copiapo|atacama|vallenar|caldera",
    "Coquimbo": r"la serena|coquimbo|ovalle|illapel",
    "Valparaíso": r"valparaiso|vina del mar|quilpue|concon|quillota"
                  r"|san antonio|los andes|villa alemana|quintero",
    "Metropolitana": r"santiago|metropolitana|quilicura|maipu|las condes"
                     r"|providencia|pudahuel|colina|san bernardo|puente alto"
                     r"|renca|huechuraba|nunoa|vitacura|cerrillos|la florida"
                     r"|macul|penalolen|lo barnechea|recoleta|conchali"
                     r"|estacion central|quinta normal|melipilla|talagante"
                     r"|buin|la reina|san miguel|independencia",
    "O'Higgins": r"rancagua|o'?higgins|machali|rengo|san fernando",
    "Maule": r"\btalca\b|maule|curico|linares|constitucion",
    "Ñuble": r"chillan|nuble",
    "Biobío": r"concepcion|biobio|bio bio|talcahuano|coronel|hualpen"
              r"|los angeles|san pedro de la paz|penco",
    "La Araucanía": r"temuco|araucania|angol|villarrica",
    "Los Ríos": r"valdivia|los rios|la union",
    "Los Lagos": r"puerto montt|osorno|los lagos|castro|puerto varas",
    "Aysén": r"coyhaique|aysen",
    "Magallanes": r"punta arenas|magallanes|puerto natales",
}

_EXIGENCIA = r"excluyente|indispensable|requisito|obligatorio|fluido|avanzado"
_SUAVIZA = r"deseable|idealmente|no excluyente|plus\b|valorable"

_NUM_PALABRA = {
    "un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4,
    "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
}
_NUM = r"(\d{1,2}|" + "|".join(_NUM_PALABRA) + r")"


def region(ubicacion) -> str:
    texto = normalizar(ubicacion)
    for nombre, patron in _REGIONES.items():
        if re.search(patron, texto):
            return nombre
    return "Sin especificar"


def modalidad(texto, es_remoto=None) -> str:
    if es_remoto:
        return "Remoto"
    normalizado = normalizar(texto)
    if re.search(r"hibrid", normalizado):
        return "Híbrido"
    if re.search(r"remoto|teletrabajo|home ?office", normalizado):
        return "Remoto"
    if re.search(r"presencial", normalizado):
        return "Presencial"
    return "Sin especificar"


def tipo_contrato(texto) -> str:
    normalizado = normalizar(texto)
    if re.search(r"part[ -]?time|media jornada|jornada parcial", normalizado):
        return "Part-time"
    if re.search(r"indefinido", normalizado):
        return "Indefinido"
    if re.search(r"plazo fijo|reemplazo|temporal", normalizado):
        return "Plazo fijo"
    if re.search(r"honorarios|boleta de honorarios", normalizado):
        return "Honorarios"
    return "No especificado"


def anios_experiencia(texto) -> int | None:
    """Años pedidos, o None si el aviso no los menciona.

    Ante un rango se toma el menor: es el mínimo real para postular.
    Nunca inventa un valor — la omisión no debe penalizar a nadie.
    """
    normalizado = normalizar(texto)
    patrones = [
        rf"de {_NUM} a {_NUM} anos",
        rf"entre {_NUM} y {_NUM} anos",
        rf"{_NUM}\+? anos? de experiencia",
        rf"minimo {_NUM} anos?",
        rf"al menos {_NUM} anos?",
        rf"experiencia (?:minima )?de {_NUM} anos?",
    ]
    for patron in patrones:
        encontrado = re.search(patron, normalizado)
        if encontrado:
            return _a_numero(encontrado.group(1))
    return None


def _a_numero(s: str) -> int:
    return int(s) if s.isdigit() else _NUM_PALABRA[s]


def ingles_excluyente(texto) -> bool:
    """True solo si se exige inglés. "Deseable" no cuenta como exigencia."""
    normalizado = normalizar(texto)
    for encontrado in re.finditer(r"\bingles\b|\benglish\b", normalizado):
        ventana = normalizado[max(0, encontrado.start() - 60):encontrado.end() + 60]
        if re.search(_SUAVIZA, ventana):
            continue
        if re.search(_EXIGENCIA, ventana):
            return True
    return False
```

- [ ] **Step 4: Correr las pruebas y verificar que pasan**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_atributos.py -v
```

Esperado: 15 passed

- [ ] **Step 5: Commit**

```bash
git add motor/atributos.py tests/test_atributos.py
git commit -m "feat: extracción de atributos del aviso (región, modalidad, contrato, años, inglés)"
```

---

### Task 5: Puntaje combinado

Junta las capas. Acá vive el requisito central: un aviso sin habilidades
detectables debe puntuar igual de bien si el cargo calza.

**Files:**
- Create: `motor/puntaje.py`
- Modify: `motor/__init__.py`
- Create: `tests/test_puntaje.py`

**Interfaces:**
- Consumes: `motor.cargo.afinidad`, `motor.cargo.UMBRAL_VISIBILIDAD`,
  `motor.texto.normalizar`
- Produces:
  - `Perfil(cargos_buscados, habilidades, anios_experiencia, region, acepta_remoto, evitar)`
  - `Aviso(titulo, texto, habilidades, region, modalidad, anios_pedidos, ingles_excluyente)`
  - `Puntaje(total, afinidad_cargo, ajustes, visible, motivo_oculto)`
  - `puntuar(aviso: Aviso, perfil: Perfil) -> Puntaje`

- [ ] **Step 1: Escribir la prueba que falla**

Crear `tests/test_puntaje.py`:

```python
import pytest

from motor.puntaje import Aviso, Perfil, puntuar


def aviso(**cambios):
    base = dict(titulo="Cajero/a supermercado", texto="Se busca cajero",
                habilidades=[], region="Metropolitana", modalidad="Presencial",
                anios_pedidos=None, ingles_excluyente=False)
    base.update(cambios)
    return Aviso(**base)


def perfil(**cambios):
    base = dict(cargos_buscados=["cajero"], habilidades=[],
                anios_experiencia=None, region=None, acepta_remoto=True,
                evitar=[])
    base.update(cambios)
    return Perfil(**base)


def test_aviso_sin_habilidades_igual_puntua_alto():
    # EL requisito central: los oficios no listan habilidades y aun así
    # deben rankear. Con el motor anterior esto daba puntaje nulo.
    resultado = puntuar(aviso(), perfil())
    assert resultado.total >= 90
    assert resultado.visible is True


def test_cargo_sin_relacion_queda_oculto():
    resultado = puntuar(aviso(titulo="Ingeniero de Procesos"), perfil())
    assert resultado.visible is False
    assert resultado.motivo_oculto == "afinidad_baja"


def test_habilidades_que_tengo_suben_el_puntaje():
    con = puntuar(aviso(habilidades=["Excel", "Manejo de caja"]),
                  perfil(habilidades=["Excel", "Manejo de caja"]))
    sin = puntuar(aviso(habilidades=["Excel", "Manejo de caja"]),
                  perfil(habilidades=[]))
    assert con.total > sin.total


def test_ingles_excluyente_penaliza_si_no_lo_tengo():
    resultado = puntuar(aviso(ingles_excluyente=True), perfil())
    assert resultado.ajustes["ingles_excluyente"] < 0


def test_ingles_excluyente_no_penaliza_si_lo_tengo():
    resultado = puntuar(aviso(ingles_excluyente=True),
                        perfil(habilidades=["Inglés"]))
    assert "ingles_excluyente" not in resultado.ajustes


def test_otra_region_penaliza():
    resultado = puntuar(aviso(region="Antofagasta"),
                        perfil(region="Metropolitana"))
    assert resultado.ajustes["otra_region"] < 0


def test_remoto_no_penaliza_por_region():
    resultado = puntuar(aviso(region="Antofagasta", modalidad="Remoto"),
                        perfil(region="Metropolitana", acepta_remoto=True))
    assert "otra_region" not in resultado.ajustes


def test_piden_mucha_mas_experiencia_penaliza():
    resultado = puntuar(aviso(anios_pedidos=8), perfil(anios_experiencia=1))
    assert resultado.ajustes["seniority_excesivo"] < 0


def test_experiencia_no_mencionada_nunca_penaliza():
    resultado = puntuar(aviso(anios_pedidos=None), perfil(anios_experiencia=1))
    assert "seniority_excesivo" not in resultado.ajustes


def test_lista_evitar_oculta_el_aviso():
    resultado = puntuar(aviso(texto="Fábrica de envases plásticos"),
                        perfil(evitar=["plástico"]))
    assert resultado.visible is False
    assert resultado.motivo_oculto == "evitado"


def test_evitar_de_una_persona_no_afecta_a_otra():
    con_filtro = puntuar(aviso(texto="Fábrica de envases plásticos"),
                         perfil(evitar=["plástico"]))
    sin_filtro = puntuar(aviso(texto="Fábrica de envases plásticos"), perfil())
    assert con_filtro.visible is False
    assert sin_filtro.visible is True


def test_el_puntaje_nunca_sale_del_rango():
    resultado = puntuar(
        aviso(ingles_excluyente=True, region="Antofagasta", anios_pedidos=15),
        perfil(region="Metropolitana", anios_experiencia=0, acepta_remoto=False))
    assert 0 <= resultado.total <= 100


@pytest.mark.parametrize("titulo", ["Cajero", "CAJERA", "Cajero/a part time"])
def test_variantes_del_mismo_cargo_son_visibles(titulo):
    assert puntuar(aviso(titulo=titulo), perfil()).visible is True
```

- [ ] **Step 2: Correr la prueba y verificar que falla**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_puntaje.py -v
```

Esperado: FAIL con `ModuleNotFoundError: No module named 'motor.puntaje'`

- [ ] **Step 3: Implementar**

Crear `motor/puntaje.py`:

```python
# -*- coding: utf-8 -*-
"""Combinación final: cargo primero, habilidades después, ajustes al final."""
from dataclasses import dataclass, field

from motor.cargo import UMBRAL_VISIBILIDAD, afinidad
from motor.texto import normalizar

# El cargo pesa más que las habilidades. Cuando el aviso no menciona ninguna
# habilidad, el cargo se lleva los 100 puntos: así un aviso de oficio no
# queda estructuralmente por debajo de uno corporativo que sí las lista.
_PESO_CARGO = 70
_PESO_HABILIDADES = 30

_AJUSTE_INGLES = -20
_AJUSTE_REGION = -25
_AJUSTE_SENIORITY = -15

# Cuántos años por encima de la experiencia declarada se toleran antes de
# considerar que el cargo queda grande.
_HOLGURA_ANIOS = 2


@dataclass(frozen=True)
class Perfil:
    cargos_buscados: list[str]
    habilidades: list[str] = field(default_factory=list)
    anios_experiencia: int | None = None
    region: str | None = None
    acepta_remoto: bool = True
    evitar: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Aviso:
    titulo: str
    texto: str
    habilidades: list[str] = field(default_factory=list)
    region: str = "Sin especificar"
    modalidad: str = "Sin especificar"
    anios_pedidos: int | None = None
    ingles_excluyente: bool = False


@dataclass(frozen=True)
class Puntaje:
    total: int
    afinidad_cargo: float
    ajustes: dict[str, int]
    visible: bool
    motivo_oculto: str | None = None


def puntuar(aviso: Aviso, perfil: Perfil) -> Puntaje:
    afin = afinidad(perfil.cargos_buscados, aviso.titulo)

    if _esta_evitado(aviso, perfil):
        return Puntaje(0, afin, {}, visible=False, motivo_oculto="evitado")

    base = _base(afin, aviso, perfil)
    ajustes = _ajustes(aviso, perfil)
    total = max(0, min(100, round(base + sum(ajustes.values()))))
    visible = afin >= UMBRAL_VISIBILIDAD
    return Puntaje(
        total=total,
        afinidad_cargo=afin,
        ajustes=ajustes,
        visible=visible,
        motivo_oculto=None if visible else "afinidad_baja",
    )


def _base(afin: float, aviso: Aviso, perfil: Perfil) -> float:
    """Cargo solo si el aviso no lista habilidades; cargo + habilidades si sí."""
    if not aviso.habilidades:
        return afin * (_PESO_CARGO + _PESO_HABILIDADES)
    mias = set(perfil.habilidades) & set(aviso.habilidades)
    cubiertas = len(mias) / len(aviso.habilidades)
    return afin * _PESO_CARGO + cubiertas * _PESO_HABILIDADES


def _ajustes(aviso: Aviso, perfil: Perfil) -> dict[str, int]:
    ajustes = {}
    if aviso.ingles_excluyente and "Inglés" not in perfil.habilidades:
        ajustes["ingles_excluyente"] = _AJUSTE_INGLES
    if _region_incompatible(aviso, perfil):
        ajustes["otra_region"] = _AJUSTE_REGION
    if _queda_grande(aviso, perfil):
        ajustes["seniority_excesivo"] = _AJUSTE_SENIORITY
    return ajustes


def _region_incompatible(aviso: Aviso, perfil: Perfil) -> bool:
    if not perfil.region or aviso.region == "Sin especificar":
        return False
    if aviso.modalidad == "Remoto" and perfil.acepta_remoto:
        return False
    return aviso.region != perfil.region


def _queda_grande(aviso: Aviso, perfil: Perfil) -> bool:
    """Solo cuando el aviso dice explícitamente cuántos años pide."""
    if aviso.anios_pedidos is None or perfil.anios_experiencia is None:
        return False
    return aviso.anios_pedidos > perfil.anios_experiencia + _HOLGURA_ANIOS


def _esta_evitado(aviso: Aviso, perfil: Perfil) -> bool:
    if not perfil.evitar:
        return False
    texto = normalizar(f"{aviso.titulo} {aviso.texto}")
    return any(normalizar(t) in texto for t in perfil.evitar if str(t).strip())
```

Reemplazar `motor/__init__.py` con:

```python
# -*- coding: utf-8 -*-
"""Motor de match cargo-primero. Funciones puras, sin base de datos ni UI."""
from motor.puntaje import Aviso, Perfil, Puntaje, puntuar

__all__ = ["Aviso", "Perfil", "Puntaje", "puntuar"]
```

- [ ] **Step 4: Correr las pruebas y verificar que pasan**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_puntaje.py -v
```

Esperado: 15 passed (12 funciones, una de ellas parametrizada con 3 casos)

- [ ] **Step 5: Correr la suite completa**

```powershell
.venv\Scripts\python.exe -m pytest tests -v
```

Esperado: 50 passed (6 texto + 8 cargo + 6 habilidades + 15 atributos + 15 puntaje)

- [ ] **Step 6: Verificar que el motor no arrastra dependencias**

```powershell
.venv\Scripts\python.exe -c "import motor; print(motor.puntuar)"
```

Esperado: imprime la función sin errores de importación. El motor debe
funcionar en un intérprete sin SQLAlchemy ni Streamlit instalados.

- [ ] **Step 7: Commit**

```bash
git add motor/puntaje.py motor/__init__.py tests/test_puntaje.py
git commit -m "feat: puntaje combinado cargo-primero con ajustes y lista evitar"
```

---

## Al terminar

El motor queda funcionando y probado, sin base de datos ni interfaz. Se
puede usar desde un intérprete para verificar a mano cómo puntúa cualquier
combinación de perfil y aviso.

**Planes siguientes**, en orden:

1. **Capa de datos** — esquema propio en Supabase, motor de conexión cacheado
   por proceso, upserts atómicos, tabla `terminos_busqueda`.
2. **Recolección** — fuentes, pipeline con presupuesto de tiempo y orden de
   prioridad de términos.
3. **App Streamlit** — identificación por correo, formulario de perfil,
   pestañas, marcas por usuario.
4. **Búsqueda en vivo** — scraping al registrarse con tope de 30 segundos y
   resultados parciales.

## Pendiente de calibración

- `UMBRAL_VISIBILIDAD` en `motor/cargo.py` está en 0.5 por criterio, no por
  datos. Revisar con ofertas reales apenas exista la capa de recolección.
- El catálogo de habilidades cubre varios rubros pero es un punto de
  partida. Crece cuando se vea qué piden los avisos que efectivamente se
  recolectan.
