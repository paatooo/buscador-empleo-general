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

# 30s era una meta, no una medida: las cuatro fuentes tienen sus propios
# pisos de paginación/espera (heredados del diseño de lote de 45 minutos
# de recolectar.py), que en la práctica hacen que una corrida real tome
# entre 60 y 200+ segundos por cargo — confirmado con una corrida de
# producción de esta misma recolección (~240s para un solo término contra
# las cuatro fuentes). 240s refleja ese comportamiento medido, no un
# número redondo elegido a ojo.
PRESUPUESTO_SEGUNDOS_DEFECTO = 240

MAX_SIMULTANEAS = 3

# Freno propio de la búsqueda forzada (botón "buscar de nuevo" en
# app.py), separado del umbral de 24h de la reutilización normal — sin
# él, alguien podría apretar el botón varias veces seguidas y disparar
# búsquedas reales una tras otra contra los cuatro sitios externos. 30s
# es un valor de prueba explícito del usuario, no definitivo — subir
# una vez que haya uso real (ver "Pendiente de calibración" del spec).
COOLDOWN_FORZAR_SEGUNDOS = 30

# Orden de velocidad esperada, NO el orden de recolectar.py: acá interesa
# maximizar lo que llega antes del corte de tiempo, así que la fuente más
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

    if forzar:
        # Sin esto, un perfil con varios cargos siempre repetiría el
        # primero en cada clic del botón "buscar de nuevo": una búsqueda
        # real tarda minutos (ver PRESUPUESTO_SEGUNDOS_DEFECTO más
        # arriba), así que para cuando la persona vuelve a apretar, el
        # cargo #1 ya "parece" fuera de cualquier enfriamiento razonable
        # y se vuelve a buscar antes que los demás — encontrado en la
        # revisión final de rama. Se ordena por el mismo criterio que ya
        # usa `db.terminos_pendientes` para la corrida programada: nunca
        # buscado primero, después el más antiguo.
        ultima_por_cargo = {
            cargo: db.consultar(
                eng, "SELECT ultima_corrida FROM terminos_busqueda"
                    " WHERE termino = :t", {"t": cargo})[0][0]
            for cargo in cargos
        }
        cargos = sorted(cargos, key=lambda c: ultima_por_cargo[c] or "")

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

        # Mismo criterio que recolectar.py (commit 8203005): una corrida
        # donde ninguna fuente respondió no es información sobre el
        # cargo, es información sobre la red — no se registra, para que
        # pueda reintentarse. Además, si el presupuesto cortó el bucle de
        # fuentes a mitad de camino, tampoco se registra como corrida: el
        # cargo solo se probó parcialmente (p. ej. 2 de 4 fuentes), así
        # que marcarlo como "corrido" lo sacaría de rotación 24h y podría
        # despriorizarlo como estéril si lo poco que se probó no encontró
        # nada — mismo bug que ya se corrigió una vez para el chequeo
        # entre cargos, reintroducido acá por el chequeo dentro de un
        # mismo cargo.
        if alguna_respondio and not cortado_por_presupuesto:
            db.registrar_corrida_termino(eng, cargo, total_cargo, ahora)
            buscados.append(cargo)
        else:
            en_cola.append(cargo)
        # Fuera del if/else: un cargo cortado a mitad de camino puede
        # haber insertado ofertas reales antes del corte (p. ej. getonbrd
        # alcanzó a responder, laborum no) — sin esto quedaba sin clave en
        # ofertas_nuevas, y la app mostraba "no encontramos nada" mientras
        # esas ofertas ya estaban visibles (la caché se limpia siempre).
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
