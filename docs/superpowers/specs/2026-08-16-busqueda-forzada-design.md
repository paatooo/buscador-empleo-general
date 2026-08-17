# Búsqueda en vivo forzada — diseño

## Objetivo

Hoy `buscar_en_vivo.buscar` solo se dispara automáticamente cuando un
perfil recién guardado queda completamente vacío (ver
[`2026-08-07-busqueda-en-vivo-design.md`](2026-08-07-busqueda-en-vivo-design.md)).
No hay forma de pedir una búsqueda en vivo a demanda cuando el perfil ya
tiene algunos resultados pero la persona quiere ver si apareció algo
nuevo. Este documento agrega un botón en "Ofertas para ti" que fuerza una
nueva búsqueda en vivo bajo demanda, sin esperar a que el perfil quede
vacío.

## Relación con lo ya construido

Reusa `buscar_en_vivo.buscar` y `db.termino_reciente` tal cual —
ninguno de los dos se reescribe, solo se les agrega un parámetro
opcional que no cambia el comportamiento por defecto de nadie que ya los
llame. No hay tablas ni columnas nuevas: el freno de esta función usa la
misma columna `ultima_corrida` que ya existe, con un umbral distinto.

## Decisiones

### 1. `db.termino_reciente` gana un umbral configurable

```python
def termino_reciente(eng: Engine, termino: str, ahora: str,
                     horas: float | None = None) -> bool:
```

`horas=None` (el default) preserva el comportamiento actual —
`_HORAS_MIN_ENTRE_CORRIDAS` (24). Cualquier llamador puede pasar un
umbral distinto sin tocar la constante privada del módulo. Los llamadores
existentes (`buscar_en_vivo.buscar` en su camino normal,
`db.terminos_pendientes` si alguna vez lo adoptara) no cambian: sin pasar
`horas`, el comportamiento es idéntico al de hoy.

### 2. `buscar_en_vivo.buscar` gana `forzar`

```python
def buscar(eng, cargos: list[str],
          presupuesto_segundos: int = PRESUPUESTO_SEGUNDOS_DEFECTO,
          ahora: str | None = None, on_progreso=None,
          forzar: bool = False) -> dict:
```

Con `forzar=True`, el chequeo de reutilización interno usa un umbral
corto (`COOLDOWN_FORZAR_SEGUNDOS = 30`, en vez de las 24 horas) en lugar
de saltarse el chequeo por completo. Esto es deliberado: sin ningún
freno, alguien podría apretar el botón repetidas veces y disparar
búsquedas reales una tras otra contra los cuatro sitios externos. Con el
freno corto, un cargo recién buscado —por el botón o automáticamente— se
reporta como reutilizado si se vuelve a pedir dentro de esos 30 segundos,
pero cualquier cargo fuera de esa ventana se busca de verdad. El
guardarraíl de concurrencia (máximo 3 simultáneas) sigue aplicando igual
que siempre, sin cambios.

**30 segundos es un número de prueba, no definitivo** — el usuario lo
eligió así explícitamente para validar el comportamiento primero y
subirlo después con datos reales de uso. Queda documentado en "Pendiente
de calibración".

El camino automático (`formulario_perfil` llamando a
`_buscar_en_vivo_con_progreso` cuando el perfil recién guardado queda
vacío) sigue sin pasar `forzar` — su comportamiento no cambia.

### 3. El botón en `app.py`

`_buscar_en_vivo_con_progreso(cargos, forzar=False)` gana el mismo
parámetro, que pasa tal cual a `buscar_en_vivo.buscar`. En `tab_ofertas`,
justo debajo de la línea `"{len(puntuadas)} ofertas para ti, ordenadas
por match."`, un botón (`key="of_buscar_de_nuevo"`) que llama
`_buscar_en_vivo_con_progreso(perfil.cargos_buscados, forzar=True)`.
Visible siempre que la pestaña muestre resultados — no solo cuando está
vacía, que es el único caso que dispara la búsqueda automática hoy.

### 4. Mensaje distinto según qué pasó

Hoy `_buscar_en_vivo_con_progreso` termina con un único mensaje genérico
de "no encontramos nada" cuando `ofertas_nuevas` no trae valores
positivos. Con el freno de 30 segundos en juego, hay dos causas
distintas para "no nuevas ofertas" y conviene decírselo a la persona:

- **Se buscó de verdad y no apareció nada nuevo** (`resumen["buscados"]`
  no está vacío, pero `ofertas_nuevas` da todo en cero): mensaje actual,
  sin cambios ("todavía no encontramos ofertas publicadas...").
- **Nada se buscó de verdad porque todo estaba en enfriamiento**
  (`resumen["buscados"]` vacío, `resumen["reutilizados"]` no vacío):
  mensaje distinto, explicando que se buscó hace muy poco y que espere un
  momento antes de volver a intentar.

## Fuera de alcance

- Un contador o cuenta regresiva visible del tiempo de enfriamiento
  restante — el botón simplemente puede volver a apretarse, y si todavía
  está en la ventana corta, el mensaje de la sección 4 lo explica después
  del hecho, no antes.
- Cambiar el umbral de 24 horas de la corrida programada — sigue igual,
  esto solo agrega un umbral corto adicional para el camino forzado.

## Pruebas

Mismo patrón que el resto de `tests/test_buscar_en_vivo.py` y
`tests/test_db.py` — mockear `fetch_all`, sin red real. Casos que
importan:

- `db.termino_reciente(eng, termino, ahora, horas=X)` respeta el umbral
  pasado, distinto del default de 24h
- `db.termino_reciente(eng, termino, ahora)` sin pasar `horas` se
  comporta idéntico a como se comportaba antes de este cambio (prueba de
  regresión, no solo de la función nueva)
- `buscar(..., forzar=True)` vuelve a scrapear un cargo corrido hace más
  de 30 segundos pero menos de 24 horas (el caso que el camino normal
  hoy reutilizaría sin buscar)
- `buscar(..., forzar=True)` sigue reutilizando (no vuelve a scrapear)
  un cargo corrido hace menos de 30 segundos
- `buscar(...)` sin `forzar` (el camino automático de siempre) no cambia
  de comportamiento con este cambio — prueba de regresión

## Pendiente de calibración

- `COOLDOWN_FORZAR_SEGUNDOS = 30` es un valor de prueba explícito del
  usuario, para validar el comportamiento antes de decidir un número
  definitivo — subirlo (probablemente a varios minutos) una vez que haya
  uso real del botón.
