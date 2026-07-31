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
