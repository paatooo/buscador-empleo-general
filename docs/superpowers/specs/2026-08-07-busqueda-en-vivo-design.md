# Búsqueda en vivo al registrarse — diseño

## Objetivo

Cuando alguien guarda un perfil cuyos cargos no calzan con nada de lo ya
recolectado, la app no lo deja mirando una pantalla vacía hasta la próxima
corrida programada: scrapea esos cargos en el momento (tope 30 segundos,
resultados parciales) y muestra lo que encuentre, dejando claro que es una
primera pasada y que mañana habrá más. Ya descrito en la sección 4 del
[spec principal](2026-07-29-buscador-empleo-personalizado-design.md); este
documento fija las decisiones de diseño que ese spec dejaba abiertas.

## Relación con lo ya construido

Reusa todo lo que ya existe: `fetch_all(terminos, excluir_urls)` (idéntico
en las cuatro fuentes), `db.upsert_ofertas`, `db.agregar_termino`,
`db.registrar_corrida_termino`, `db.terminos_pendientes` (mismo umbral de
`_HORAS_MIN_ENTRE_CORRIDAS`), y `app_data.puntuar_ofertas` para decidir si
un perfil "queda vacío". No inventa tablas nuevas ni un segundo mecanismo
de reutilización — la búsqueda en vivo y la corrida programada comparten
el mismo estado en `terminos_busqueda`.

## Decisiones

### 1. Disparador: perfil completo vacío, no cargo por cargo

Se dispara al guardar un perfil (primera vez o edición) cuando
`app_data.puntuar_ofertas(ofertas_actuales, perfil)` da lista vacía —
ningún cargo de la lista trae ninguna oferta visible. Si al menos un cargo
ya calza con algo, no se scrapea nada al momento aunque otro cargo de la
lista esté completamente descubierto; ese otro cargo queda igual en
`terminos_busqueda` para la corrida programada, por el camino normal de
`agregar_termino`.

Se busca por **todos** los cargos del perfil a la vez (no solo el primero),
repartiendo el presupuesto de 30 segundos entre ellos — ver sección 3.

### 2. Nuevo módulo `buscar_en_vivo.py`

Misma separación que el resto del proyecto: funciones puras sobre
`Engine` + listas de términos, testeables con pytest mockeando
`fetch_all` de las cuatro fuentes (igual que `tests/test_recolectar.py`).
`app.py` solo lo invoca y dibuja la barra de progreso — nada de
`streamlit` dentro de `buscar_en_vivo.py`.

**Produce:**

- `buscar(eng, cargos: list[str], presupuesto_segundos: int = 30) -> dict`
  — orquesta todo: reutilización, scraping con presupuesto, persistencia,
  análisis acotado, registro de la corrida. Devuelve un resumen (cargos
  buscados, cargos reutilizados de una corrida reciente, ofertas nuevas
  por cargo, si el presupuesto se agotó antes de terminar todos los
  cargos).

**`db.py` suma `termino_reciente(eng, termino: str, ahora: str) -> bool`**
— encapsula el mismo chequeo que ya hace `terminos_pendientes` contra
`_HORAS_MIN_ENTRE_CORRIDAS` (una constante privada de `db.py`), para que
`buscar_en_vivo.py` no tenga que alcanzar esa constante desde afuera.
`terminos_pendientes` puede quedar tal cual (no es necesario reescribirlo
en términos de esta función nueva) o adoptarla internamente si al
implementar resulta más simple — decisión libre para el plan, mientras la
constante siga viviendo en un solo lugar.

**Concurrencia:** un contador módulo-nivel (`threading.Lock`, mismo patrón
que `db._ENGINES_LOCK`) limita a **3** llamadas a `buscar()` corriendo a la
vez en el proceso. Como Streamlit Cloud corre una sola instancia, no hace
falta coordinación entre procesos ni tabla en la base. Si ya hay 3
corriendo, `buscar()` no scrapea nada: registra los cargos en
`terminos_busqueda` (vía `agregar_termino`, origen `"usuario"`) igual que
si fueran a esperar la corrida programada, y devuelve un resumen que dice
"agregado a la cola" en vez de "buscado ahora". El perfil se guarda de
todas formas — este guardarraíl nunca bloquea el guardado.

### 3. Orden de fuentes y presupuesto de 30 segundos

Se corren en orden de velocidad esperada: Get on Board (API, responde en
segundos) → Trabajando → Laborum (ambas por sitemap) → Computrabajo (HTML
paginado, la más lenta — la primera que se corta si no alcanza el
tiempo). Antes de empezar cada fuente se chequea el tiempo restante contra
`time.monotonic()`; si no alcanza, se salta esa fuente (y las que
quedan) en vez de arrancarla a medias. El presupuesto es sobre el total de
la llamada a `buscar()`, no por cargo ni por fuente — con varios cargos
sin cubrir, cada uno recibe menos tiempo, nunca se extiende el total.

Resultados parciales: lo que haya llegado cuando se acaba el presupuesto
es lo que se persiste y se muestra. No es un error, es el comportamiento
esperado documentado en el spec principal.

### 4. Persistencia y análisis acotado a lo nuevo

Cada cargo buscado en vivo sigue el mismo camino que usa
`recolectar.py`: `db.upsert_ofertas` con las filas encontradas,
`db.agregar_termino(eng, cargo, "usuario", ahora)` si el término no
existía, `db.registrar_corrida_termino(eng, cargo, total_encontrado,
ahora)` al terminar (mismo criterio que el fix de
`recolectar.py`/commit `8203005`: solo se registra la corrida de un cargo
si al menos una fuente respondió sin error — si las cuatro fallan, el
cargo queda pendiente para reintentar, no se descarta).

**`analizar.py` suma `run_urls(eng, urls: list[str]) -> dict`** — mismo
cálculo genérico que `run()` (habilidades, áreas, región, modalidad, tipo
de contrato, años pedidos, inglés excluyente, vigencia) pero acotado a las
URLs que la búsqueda en vivo acaba de insertar, no la tabla completa.
La deduplicación (`analizar.py` línea ~34-43) sigue necesitando ver la
base completa para no perderse un duplicado contra una oferta vieja, pero
la clave de comparación (`título|empresa|región`) ya se construye
ordenando `filas_ofertas` — para `run_urls` esa consulta trae todas las
filas (para construir el set de claves vistas) pero el cálculo pesado por
oferta (habilidades, áreas, texto) solo corre para las URLs pedidas.
`run()` no cambia — sigue siendo lo que usa `recolectar.py`.

### 5. Reutilización: mismo umbral de 24 horas

Antes de scrapear un cargo, `buscar()` llama `db.termino_reciente(eng,
cargo, ahora)` (sección 2) — mismo umbral de 24 horas que ya usa
`db.terminos_pendientes` para la corrida programada. Si el cargo se
corrió hace menos de 24 horas —en vivo o programada, da igual el
origen—, no se repite: se muestra lo que ya haya en la base para ese
cargo (posiblemente vacío, si la corrida anterior tampoco encontró
nada), con el mensaje honesto.

Una vez que un cargo pasa por búsqueda en vivo, deja de ser "nunca
corrido" — entra a la rotación normal de `terminos_pendientes` junto con
todo lo demás, sin trato especial. Es la extensión natural del mecanismo
que ya existe, no un mecanismo nuevo.

### 6. Caso vacío

Si después del presupuesto de 30 segundos (o de reutilizar una corrida
reciente que tampoco encontró nada) `puntuar_ofertas` sigue vacío para
algún cargo, se muestra el mensaje honesto del spec principal ("todavía no
tenemos ofertas de X, las seguimos buscando") — nunca una lista con match
bajo para simular resultados.

### 7. Invalidar la caché de `app.py`

`_ofertas_crudas()` está cacheada con `@st.cache_data(ttl=300)`. Si
`buscar_en_vivo.buscar` encuentra algo y no se invalida esa caché, la
persona vería "no encontramos nada" hasta que expire (hasta 5 minutos)
pese a que ya se guardó lo que buscaba. Después de una llamada a
`buscar()` con resultados nuevos, `app.py` llama
`_ofertas_crudas.clear()` antes de renderizar las pestañas.

### 8. Dónde se engancha en `app.py`

Dentro de `formulario_perfil`, después de `guardar_perfil` y antes de
devolver el perfil nuevo: si `app_data.puntuar_ofertas` da vacío para el
perfil recién guardado, se llama `buscar_en_vivo.buscar` con una barra de
progreso (`st.progress`, actualizada a medida que cada fuente termina) y
un texto explicando que es una primera pasada. Al terminar, si hubo
resultados nuevos, se limpia la caché (sección 7) y se sigue el flujo
normal hacia las pestañas.

## Pruebas

Mismo patrón que `tests/test_recolectar.py`: mockear `fetch_all` de las
cuatro fuentes con `unittest.mock.patch`, sin red real. Casos que importan:

- un cargo sin nada en la base dispara la búsqueda y persiste lo
  encontrado, visible después vía `puntuar_ofertas`
- un perfil con al menos un cargo cubierto no dispara nada
- el presupuesto de tiempo corta antes de terminar todas las fuentes o
  todos los cargos, sin dejar la base inconsistente (mismo caso de prueba
  que ya pide la sección "Pruebas" del spec principal)
- `db.termino_reciente` da `True` para un cargo corrido hace menos de 24h
  (en vivo o programada) y `False` para uno más viejo o nunca corrido —
  y `buscar()` no vuelve a scrapear un cargo reciente
- 4 llamadas simultáneas: la 4ta no scrapea, pero el cargo queda
  registrado para la corrida programada
- ninguna fuente responde: el cargo no se registra como corrido (mismo
  criterio que `recolectar.py`)
- `analizar.run_urls` con URLs mezcladas (algunas duplicadas contra
  ofertas viejas, alguna nueva) da el mismo resultado que `run()` sobre
  esas URLs, sin reprocesar las que no se pidieron

## Fuera de alcance

- Cola persistente entre reinicios del proceso — si Streamlit Cloud
  reinicia la instancia, el contador de concurrencia vuelve a cero (no es
  un problema: no hay corridas "en curso" que perder, cada `buscar()` es
  una llamada síncrona dentro de un request).
- Notificar a la persona cuando la corrida programada del día siguiente
  finalmente cubra un cargo que quedó en cola — no hay mecanismo de
  notificación en la app todavía.
