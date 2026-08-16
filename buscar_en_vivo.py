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
        else:
            en_cola.append(cargo)
        urls_nuevas_totales.extend(urls_nuevas_cargo)
        if on_progreso:
            on_progreso(i + 1, len(cargos), cargo)

    if urls_nuevas_totales:
        analizar.run_urls(eng, urls_nuevas_totales)

    return {"buscados": buscados, "reutilizados": reutilizados,
            "en_cola": en_cola, "ofertas_nuevas": ofertas_nuevas,
            "agotado": agotado}
