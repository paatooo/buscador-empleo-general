# Búsqueda en vivo forzada — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un botón en "Ofertas para ti" que fuerza una nueva búsqueda en
vivo bajo demanda, sin esperar a que el perfil quede completamente vacío
como exige el camino automático de hoy.

**Architecture:** `db.termino_reciente` y `buscar_en_vivo.buscar` ganan
cada uno un parámetro opcional retrocompatible — ningún llamador
existente cambia de comportamiento sin pasarlo explícitamente. El freno
anti-spam del botón reusa la misma columna `ultima_corrida` con un
umbral corto en vez de las 24 horas normales, sin tablas ni estado
nuevo.

**Tech Stack:** Nada nuevo — mismas dependencias que ya tiene el
proyecto.

## Global Constraints

- **`db.termino_reciente(eng, termino, ahora, horas=None)`** —
  `horas=None` preserva el comportamiento actual (`_HORAS_MIN_ENTRE_CORRIDAS`,
  24h). Los llamadores existentes no cambian.
- **`buscar_en_vivo.buscar(..., forzar=False)`** — con `forzar=True`, el
  umbral de reutilización baja a `COOLDOWN_FORZAR_SEGUNDOS = 30` segundos
  en vez de saltarse el chequeo por completo. El camino automático
  (`formulario_perfil`) sigue sin pasar `forzar` — comportamiento
  idéntico al de hoy.
- **`COOLDOWN_FORZAR_SEGUNDOS = 30` es un valor de prueba explícito del
  usuario**, no definitivo — documentado como pendiente de calibración,
  no se justifica ni se defiende como número final.
- **El botón vive en "Ofertas para ti"**, visible siempre que la
  pestaña muestre resultados (no solo cuando está vacía).
- **Mensaje distinto según la causa**: "se buscó de verdad y no hay
  nada nuevo" vs. "no se buscó nada porque todo estaba en enfriamiento".
- **Nombres en español**, consistentes con el resto del proyecto.
- Spec de referencia:
  [`docs/superpowers/specs/2026-08-16-busqueda-forzada-design.md`](../specs/2026-08-16-busqueda-forzada-design.md).

---

## Estructura de archivos

```
buscador-empleo-personalizado/
├── db.py                 termino_reciente gana horas=
├── buscar_en_vivo.py      buscar gana forzar=, nueva constante
├── app.py                 boton + mensaje distinto
└── tests/
    ├── test_db.py         + pruebas de horas=
    └── test_buscar_en_vivo.py   + pruebas de forzar=
```

Nada de esto crea archivos nuevos — son extensiones retrocompatibles de
tres archivos ya existentes.

---

### Task 1: `db.termino_reciente` gana `horas=`

**Files:**
- Modify: `db.py:277-290`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: nada nuevo
- Produces: `termino_reciente(eng: Engine, termino: str, ahora: str, horas: float | None = None) -> bool`

- [ ] **Step 1: Escribir las pruebas que fallan**

Agregar a `tests/test_db.py`, después de
`test_termino_reciente_da_false_si_el_termino_no_existe`:

```python
def test_termino_reciente_sin_horas_se_comporta_como_antes(tmp_path):
    # Prueba de regresión: sin pasar horas=, el comportamiento no cambia
    # respecto de antes de este parámetro.
    eng = db.engine(tmp_path / "tr5.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "cajero", "base", "2026-07-01T00:00:00")
    db.registrar_corrida_termino(eng, "cajero", 5, "2026-08-01T09:00:00")
    assert db.termino_reciente(eng, "cajero", "2026-08-01T11:00:00") is True
    assert db.termino_reciente(eng, "cajero", "2026-08-02T10:00:00") is False


def test_termino_reciente_respeta_horas_personalizadas(tmp_path):
    eng = db.engine(tmp_path / "tr6.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "cajero", "base", "2026-08-07T00:00:00")
    db.registrar_corrida_termino(eng, "cajero", 5, "2026-08-07T10:00:00")
    # 20 segundos después: dentro de un umbral de 30s (30/3600 horas)
    assert db.termino_reciente(eng, "cajero", "2026-08-07T10:00:20",
                               horas=30 / 3600) is True
    # 40 segundos después: fuera del umbral de 30s, muy dentro de 24h
    assert db.termino_reciente(eng, "cajero", "2026-08-07T10:00:40",
                               horas=30 / 3600) is False
```

- [ ] **Step 2: Correr las pruebas y verificar que fallan**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_db.py -k "sin_horas or horas_personalizadas" -v
```

Esperado: FAIL con `TypeError: termino_reciente() got an unexpected keyword argument 'horas'`

- [ ] **Step 3: Implementar**

Reemplazar en `db.py` (líneas 277-290):

```python
def termino_reciente(eng: Engine, termino: str, ahora: str,
                     horas: float | None = None) -> bool:
    """True si `termino` se corrió (en vivo o programada) hace menos de
    `horas` (default: `_HORAS_MIN_ENTRE_CORRIDAS`, el mismo umbral de
    24h que usa `terminos_pendientes`). Mismo umbral por defecto y misma
    comparación lexicográfica de cadenas ISO — un término nunca corrido
    da False."""
    from datetime import datetime, timedelta

    if horas is None:
        horas = _HORAS_MIN_ENTRE_CORRIDAS

    fila = consultar(eng, "SELECT ultima_corrida FROM terminos_busqueda"
                          " WHERE termino = :t", {"t": termino})
    if not fila or fila[0][0] is None:
        return False
    corte = (datetime.fromisoformat(ahora)
             - timedelta(hours=horas)).isoformat()
    return fila[0][0] >= corte
```

- [ ] **Step 4: Correr las pruebas y verificar que pasan**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_db.py -v
```

Esperado: todas pasan (las de antes + las 2 nuevas)

- [ ] **Step 5: Commit**

```bash
git add db.py tests/test_db.py
git commit -m "feat: db.termino_reciente acepta un umbral de horas configurable"
```

---

### Task 2: `buscar_en_vivo.buscar` gana `forzar=`

**Files:**
- Modify: `buscar_en_vivo.py`
- Test: `tests/test_buscar_en_vivo.py`

**Interfaces:**
- Consumes: `db.termino_reciente(eng, termino, ahora, horas=...)` (Task 1)
- Produces:
  - `COOLDOWN_FORZAR_SEGUNDOS = 30`
  - `buscar(eng, cargos, presupuesto_segundos=PRESUPUESTO_SEGUNDOS_DEFECTO, ahora=None, on_progreso=None, forzar=False) -> dict`
    (misma forma de retorno que antes — sin cambios en las claves)

- [ ] **Step 1: Escribir las pruebas que fallan**

Agregar a `tests/test_buscar_en_vivo.py` (usa el helper `_fila_falsa` que
ya existe en el archivo):

```python
def test_buscar_forzar_vuelve_a_scrapear_un_cargo_de_hace_mas_de_30s(tmp_path):
    eng = db.engine(tmp_path / "bf1.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "cajero", "usuario", "2026-08-16T10:00:00")
    db.registrar_corrida_termino(eng, "cajero", 5, "2026-08-16T10:00:00")

    with patch("fuente_getonbrd.fetch_all",
               return_value=([], set(), None)) as m_gb, \
         patch("fuente_trabajando.fetch_all", return_value=([], set(), None)), \
         patch("fuente_laborum.fetch_all", return_value=([], set(), None)), \
         patch("fuente_computrabajo.fetch_all", return_value=([], set(), None)):
        # 1 minuto después de la corrida anterior: fuera del enfriamiento
        # de 30s del forzado, muy dentro de las 24h normales (que sin
        # forzar habrían reutilizado el cargo sin buscar de nuevo).
        resumen = buscar_en_vivo.buscar(eng, ["cajero"],
                                        ahora="2026-08-16T10:01:00",
                                        forzar=True)

    m_gb.assert_called_once()
    assert resumen["buscados"] == ["cajero"]
    assert resumen["reutilizados"] == []


def test_buscar_forzar_sigue_reutilizando_dentro_de_los_30s(tmp_path):
    eng = db.engine(tmp_path / "bf2.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "cajero", "usuario", "2026-08-16T10:00:00")
    db.registrar_corrida_termino(eng, "cajero", 5, "2026-08-16T10:00:00")

    with patch("fuente_getonbrd.fetch_all") as m_gb, \
         patch("fuente_trabajando.fetch_all") as m_tb, \
         patch("fuente_laborum.fetch_all") as m_lb, \
         patch("fuente_computrabajo.fetch_all") as m_ct:
        # 10 segundos después: dentro del enfriamiento de 30s.
        resumen = buscar_en_vivo.buscar(eng, ["cajero"],
                                        ahora="2026-08-16T10:00:10",
                                        forzar=True)

    m_gb.assert_not_called()
    m_tb.assert_not_called()
    m_lb.assert_not_called()
    m_ct.assert_not_called()
    assert resumen["reutilizados"] == ["cajero"]
    assert resumen["buscados"] == []


def test_buscar_sin_forzar_no_cambia_de_comportamiento(tmp_path):
    # Prueba de regresión: el camino automático (sin forzar) sigue
    # reutilizando un cargo corrido hace 1 minuto, porque su umbral
    # sigue siendo 24h, no 30s.
    eng = db.engine(tmp_path / "bf3.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "cajero", "usuario", "2026-08-16T10:00:00")
    db.registrar_corrida_termino(eng, "cajero", 5, "2026-08-16T10:00:00")

    with patch("fuente_getonbrd.fetch_all") as m_gb, \
         patch("fuente_trabajando.fetch_all") as m_tb, \
         patch("fuente_laborum.fetch_all") as m_lb, \
         patch("fuente_computrabajo.fetch_all") as m_ct:
        resumen = buscar_en_vivo.buscar(eng, ["cajero"],
                                        ahora="2026-08-16T10:01:00")

    m_gb.assert_not_called()
    assert resumen["reutilizados"] == ["cajero"]
```

- [ ] **Step 2: Correr las pruebas y verificar que fallan**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_buscar_en_vivo.py -k forzar -v
```

Esperado: FAIL con `TypeError: buscar() got an unexpected keyword argument 'forzar'`

- [ ] **Step 3: Implementar**

Agregar la constante nueva en `buscar_en_vivo.py`, justo después de
`MAX_SIMULTANEAS = 3`:

```python
# Freno propio de la búsqueda forzada (botón "buscar de nuevo" en
# app.py), separado del umbral de 24h de la reutilización normal — sin
# él, alguien podría apretar el botón varias veces seguidas y disparar
# búsquedas reales una tras otra contra los cuatro sitios externos. 30s
# es un valor de prueba explícito del usuario, no definitivo — subir
# una vez que haya uso real (ver "Pendiente de calibración" del spec).
COOLDOWN_FORZAR_SEGUNDOS = 30
```

Reemplazar la firma y el cuerpo de `buscar`:

```python
def buscar(eng, cargos: list[str],
          presupuesto_segundos: int = PRESUPUESTO_SEGUNDOS_DEFECTO,
          ahora: str | None = None, on_progreso=None,
          forzar: bool = False) -> dict:
    """Busca en vivo los `cargos` que lo necesiten contra las cuatro
    fuentes, con un presupuesto de tiempo total. `on_progreso`, si se
    pasa, se llama como `on_progreso(indice, total, cargo)` después de
    procesar cada cargo (buscado o reutilizado) — para que `app.py`
    pueda mostrar una barra de progreso sin que este módulo dependa de
    streamlit. `forzar=True` reduce el umbral de reutilización de 24h a
    `COOLDOWN_FORZAR_SEGUNDOS` — pensado para un botón de "buscar de
    nuevo" a demanda: un cargo recién buscado sigue reutilizándose
    dentro de esa ventana corta, pero cualquier cargo fuera de ella se
    busca de verdad, sin esperar 24h."""
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
                                on_progreso, forzar)
    finally:
        _semaforo.release()


def _buscar_con_cupo(eng, cargos, presupuesto_segundos, ahora, on_progreso,
                     forzar=False) -> dict:
    hoy = ahora[:10]
    horas_reutilizacion = COOLDOWN_FORZAR_SEGUNDOS / 3600 if forzar else None
    for cargo in cargos:
        db.agregar_termino(eng, cargo, "usuario", ahora)

    inicio = time.monotonic()
    buscados, reutilizados, en_cola = [], [], []
    ofertas_nuevas = {}
    urls_nuevas_totales = []
    conocidas = {f["job_url"] for f in db.cargar_ofertas(eng)}
    vigentes_totales = set()
    agotado = False

    for i, cargo in enumerate(cargos):
        if db.termino_reciente(eng, cargo, ahora, horas=horas_reutilizacion):
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
        cortado_por_presupuesto = False
        urls_nuevas_cargo = []
        ofertas_insertadas_cargo = 0
        for nombre_fuente, modulo in FUENTES:
            if time.monotonic() - inicio > presupuesto_segundos:
                agotado = True
                cortado_por_presupuesto = True
                break
            try:
                filas, vigentes, error = modulo.fetch_all(
                    [cargo], excluir_urls=conocidas)
            except Exception as e:
                filas, vigentes, error = [], set(), str(e)[:300]
            vigentes = vigentes or set()
            vigentes_totales |= vigentes
            total_cargo += len(vigentes)
            if filas:
                for f in filas:
                    f.setdefault("scrape_date", hoy)
                    f.setdefault("last_seen", hoy)
                    f.setdefault("search_term", cargo)
                columnas = [c for c in COLUMNAS_OFERTA if c in filas[0]]
                try:
                    ofertas_insertadas_cargo += db.upsert_ofertas(
                        eng, filas, columnas)
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

        if alguna_respondio and not cortado_por_presupuesto:
            db.registrar_corrida_termino(eng, cargo, total_cargo, ahora)
            buscados.append(cargo)
        else:
            en_cola.append(cargo)
        ofertas_nuevas[cargo] = ofertas_insertadas_cargo
        urls_nuevas_totales.extend(urls_nuevas_cargo)
        if on_progreso:
            on_progreso(i + 1, len(cargos), cargo)

    db.actualizar_last_seen(eng, vigentes_totales, hoy)
    if urls_nuevas_totales:
        analizar.run_urls(eng, urls_nuevas_totales)

    return {"buscados": buscados, "reutilizados": reutilizados,
            "en_cola": en_cola, "ofertas_nuevas": ofertas_nuevas,
            "agotado": agotado}
```

(Único cambio real en `_buscar_con_cupo` respecto de la versión actual:
el nuevo parámetro `forzar`, la línea `horas_reutilizacion = ...`, y
pasar `horas=horas_reutilizacion` al `db.termino_reciente` de la línea
del chequeo de reutilización. El resto del cuerpo es idéntico al de hoy
— cópialo tal cual si tu editor no hace merge automático.)

- [ ] **Step 4: Correr las pruebas y verificar que pasan**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_buscar_en_vivo.py -v
```

Esperado: todas pasan (las de antes + las 3 nuevas)

- [ ] **Step 5: Correr la suite completa**

```powershell
.venv\Scripts\python.exe -m pytest tests -v
```

Esperado: sin regresiones

- [ ] **Step 6: Commit**

```bash
git add buscar_en_vivo.py tests/test_buscar_en_vivo.py
git commit -m "feat: buscar_en_vivo.buscar acepta forzar= con enfriamiento corto"
```

---

### Task 3: Botón en `app.py`

**Files:**
- Modify: `app.py`

**Interfaces:**
- Consumes: `buscar_en_vivo.buscar(..., forzar=...)` (Task 2)

- [ ] **Step 1: Modificar `_buscar_en_vivo_con_progreso` para aceptar `forzar`**

Reemplazar la función completa en `app.py`:

```python
def _buscar_en_vivo_con_progreso(cargos: list[str], forzar: bool = False) -> None:
    """Busca en vivo los `cargos` dados. Sin `forzar` (el camino
    automático, cuando el perfil recién guardado queda vacío) o con
    `forzar=True` (el botón "Buscar de nuevo" a demanda, con un
    enfriamiento corto en vez del umbral de 24h normal — ver
    `buscar_en_vivo.COOLDOWN_FORZAR_SEGUNDOS`)."""
    import buscar_en_vivo
    import db

    # st.progress no es un widget con estado (no acepta key=) — es un
    # elemento de despliegue puro, así que no le aplica el problema de
    # DuplicateElementId que sí afecta a los widgets interactivos.
    texto_inicial = (
        "Buscando de nuevo en vivo (puede tomar unos minutos)..." if forzar
        else "Todavía no tenemos ofertas para tu perfil — buscando en "
             "vivo (esta es una primera pasada; mañana habrá más).")
    barra = st.progress(0.0, text=texto_inicial)

    def avance(indice, total, cargo):
        barra.progress(indice / total, text=f"Buscando «{cargo}»"
                       f" ({indice}/{total})...")

    try:
        eng = db.engine()
        resumen = buscar_en_vivo.buscar(eng, cargos, on_progreso=avance,
                                        forzar=forzar)
    except Exception as e:
        # El perfil ya se guardó (ver `st.success` más arriba) antes de
        # llegar aquí — una falla transitoria a mitad de una búsqueda que
        # ahora puede tomar varios minutos (ver PRESUPUESTO_SEGUNDOS_DEFECTO
        # en buscar_en_vivo.py) no debe dejar a la persona con un
        # traceback crudo por algo que de todos modos ya funcionó.
        barra.empty()
        print(f"[ERROR] busqueda en vivo: {e}")
        st.warning("No pudimos completar la búsqueda en vivo — prueba de "
                  "nuevo más tarde, o espera a la próxima corrida "
                  "programada.")
        _ofertas_crudas.clear()
        return
    barra.empty()

    # Limpiar siempre, no solo cuando ofertas_nuevas trae algo: en un caso
    # extremo (una fuente devuelve filas junto con un error, así que
    # alguna_respondio queda en False) una oferta puede haberse insertado
    # sin que el cargo tenga clave en ofertas_nuevas — más barato limpiar
    # de más (una lectura extra a la base) que arriesgar una caché
    # desactualizada.
    _ofertas_crudas.clear()
    if not any(resumen["ofertas_nuevas"].values()):
        if resumen["buscados"]:
            # Se buscó de verdad y no apareció nada nuevo.
            st.info("Todavía no encontramos ofertas publicadas para lo que "
                    "buscas — seguimos intentando en las próximas corridas.")
        elif resumen["reutilizados"]:
            # No se buscó nada de verdad porque todo estaba en
            # enfriamiento (ver COOLDOWN_FORZAR_SEGUNDOS) — mensaje
            # distinto: no es que no haya nada, es que se buscó hace
            # instantes.
            st.info("Ya buscaste esto hace muy poco — espera un momento "
                    "antes de volver a intentar.")
```

- [ ] **Step 2: Agregar el botón en `tab_ofertas`**

Reemplazar la línea `st.write(f"{len(puntuadas)} ofertas para ti, ordenadas por match.")`
y lo que sigue inmediatamente, dentro de `tab_ofertas`:

```python
    st.write(f"{len(puntuadas)} ofertas para ti, ordenadas por match.")
    if st.button("🔄 Buscar de nuevo en vivo", key="of_buscar_de_nuevo"):
        _buscar_en_vivo_con_progreso(perfil.cargos_buscados, forzar=True)
    marcas = app_data.marcas_de(usuario_id)
```

(La línea `marcas = app_data.marcas_de(usuario_id)` ya existía — solo se
agrega el `if st.button(...)` entre el `st.write` y esa línea. El bucle
`for oferta in puntuadas[:50]: ...` que sigue no cambia.)

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: boton para forzar una nueva busqueda en vivo a demanda"
```

- [ ] **Step 4: Correr la suite completa**

```powershell
.venv\Scripts\python.exe -m pytest tests -v
```

Esperado: sin regresiones (este archivo no tiene pruebas automáticas
propias — se verifica corriendo la app de verdad).

- [ ] **Step 5: Verificar a mano con streamlit run**

```powershell
.venv\Scripts\python.exe -m streamlit run app.py
```

Comprobar, con un perfil que ya tenga resultados en "Ofertas para ti":
- El botón "🔄 Buscar de nuevo en vivo" aparece debajo del conteo de
  ofertas, sin importar cuántos resultados haya.
- Apretarlo muestra la barra de progreso con el texto de "Buscando de
  nuevo en vivo..." (no el texto de "primera pasada", que es solo para
  el camino automático).
- Apretarlo dos veces seguidas (dentro de 30 segundos): la segunda vez
  no dispara scraping real — mensaje de "ya buscaste esto hace muy
  poco".
- Esperar más de 30 segundos y apretarlo de nuevo: sí dispara una
  búsqueda real otra vez para los mismos cargos.
- Ningún error de `DuplicateElementId` ni excepción visible en la
  consola del navegador ni en la terminal.

---

## Al terminar

El botón completa el ciclo de búsqueda en vivo: ya no depende
exclusivamente de que el perfil quede vacío — cualquiera puede pedir una
pasada nueva cuando quiera, con un freno corto que evita machacar los
sitios externos.

## Pendiente de calibración

- `COOLDOWN_FORZAR_SEGUNDOS = 30` es un valor de prueba explícito del
  usuario — subirlo (probablemente a varios minutos) una vez que haya
  uso real del botón.

Encontrado en la revisión final de rama (después de que las tareas
individuales ya estaban aprobadas), revisado por la persona usuaria y
explícitamente diferido — no son descuidos, son decisiones tomadas:

- El enfriamiento de 30s se mide desde que la búsqueda *empieza*, no
  desde que termina — como una búsqueda real tarda bastante más que
  30s, en la práctica el enfriamiento casi siempre ya expiró para
  cuando el control vuelve a la persona usuaria. Queda como pendiente
  de calibración junto con el valor mismo de `COOLDOWN_FORZAR_SEGUNDOS`.
- Dos sesiones distintas pueden terminar scrapeando el mismo cargo al
  mismo tiempo — el semáforo (`MAX_SIMULTANEAS`) limita la concurrencia
  total, pero no evita que dos personas dispares una búsqueda del mismo
  cargo en paralelo. Queda pendiente, sin arreglo por ahora.
- En el peor caso la página puede bloquearse hasta ~440s (cerca de 7
  minutos): el chequeo de presupuesto ocurre *antes* de arrancar cada
  fuente, no como un corte duro a mitad de una fuente. Es más que los
  "unos minutos" que sugiere el texto del botón, pero ese texto no es
  técnicamente incorrecto — queda como informativo, sin cambios.
- El mensaje "no pudimos empezar la búsqueda ahora mismo" puede
  aparecer también en el camino automático (perfil recién guardado sin
  ofertas), donde no hay un botón para reintentar. Se deja tal cual.

Encontrado en la **segunda** revisión final de rama, tras el primer
round de arreglos (rerun + rotación) — igual de deliberado, no un
descuido:

- **La rotación por `ultima_corrida` no cubre un cargo que nunca llega a
  completar sus 4 fuentes** (se corta por presupuesto en cada clic, o
  sus 4 fuentes fallan siempre) — su `ultima_corrida` queda `NULL` para
  siempre, así que sigue ordenando primero y los demás cargos del
  perfil no tienen turno. Medido como alcanzable con tiempos reales de
  las fuentes (`fuente_trabajando`/`fuente_laborum` con el cupo lleno
  rondan 110-130s cada una), sobre todo en las primeras búsquedas de un
  perfil nuevo. El arreglo completo requiere una columna nueva
  (`ultimo_intento`, escrita para todo cargo intentado, se complete o
  no) — una migración de esquema real sobre Supabase de producción, que
  se decidió no hacer todavía. La rama sigue siendo estrictamente mejor
  que `main` de todas formas: el botón no existía antes.
- Las pruebas nuevas de rotación verifican el orden dentro de una sola
  llamada a `buscar()`, no el escenario real (varios clics = varias
  llamadas separadas, con el tiempo real avanzando entre una y otra).
  El controller sí verificó esto último con una simulación aislada
  antes de aceptar el fix, pero no quedó como prueba permanente.
- El `if ...: st.rerun()` del botón (el arreglo del Crítico 1 original)
  no tiene ninguna prueba automatizada — `app.py` no tiene suite propia
  por convención del proyecto, así que solo queda verificado a mano
  (`AppTest`, no permanente).
- Si una búsqueda forzada consume el presupuesto completo sin registrar
  nada, el mensaje sigue siendo "no pudimos empezar la búsqueda" — que
  es engañoso después de que la persona esperó varios minutos. Distinto
  del punto ya documentado sobre el mismo mensaje en el camino
  automático.
- Ordenar por `ultima_corrida` hace una consulta por cargo en vez de una
  sola con `IN (...)` — irrelevante frente a los 240s de una búsqueda,
  mencionado solo por prolijidad.
