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


def run(eng, db_path=None) -> dict:
    db.ensure_schema(eng)
    filas_ofertas = db.consultar(eng, "SELECT job_url, site, title, company,"
                                      " location, date_posted, is_remote,"
                                      " description, scrape_date, last_seen"
                                      " FROM ofertas")
    if not filas_ofertas:
        return {"analizadas": 0, "duplicadas": 0}

    hoy = datetime.now(timezone.utc).date()
    ultima_corrida = max(
        (f[9] for f in filas_ofertas if f[9]), default=hoy.isoformat())

    # Deduplicación por contenido: misma oferta publicada varias veces
    # (distinto link o distinta fuente). Se conserva la primera capturada.
    ordenadas = sorted(filas_ofertas, key=lambda f: (f[8] or "", f[0]))
    vistas_clave = set()
    duplicada_por_url = {}
    for f in ordenadas:
        job_url, _, title, company, location = f[0], f[1], f[2], f[3], f[4]
        clave = f"{normalizar(title)}|{normalizar(company)}|{region(location)}"
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
