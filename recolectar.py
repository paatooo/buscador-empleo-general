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

# Se guardan los módulos, no `modulo.fetch_all` ya resuelto: si se captura
# la función en este momento, un `patch("fuente_x.fetch_all", ...)` en los
# tests (o cualquier reemplazo en caliente del atributo del módulo) no
# tendría efecto, porque la referencia ya capturada apunta a la función
# original. Resolver el atributo recién al llamar (`modulo.fetch_all(...)`
# dentro del bucle) respeta cualquier reemplazo hecho sobre el módulo.
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
            try:
                filas, _vigentes, _error = modulo.fetch_all(
                    [termino], excluir_urls=conocidas)
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
