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
