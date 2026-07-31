# -*- coding: utf-8 -*-
"""Fuente Computrabajo Chile (cl.computrabajo.com) — scraping HTML.

Los términos de búsqueda vienen de `terminos_busqueda`, no de una lista
fija: se convierten a slug (espacios → guiones) antes de armar la URL.
"""
import html as html_mod
import re
import time
from datetime import date, timedelta

import requests

import jobposting

BASE = "https://cl.computrabajo.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
           "Accept-Language": "es-CL,es;q=0.9"}

PAGINAS_POR_BUSQUEDA = 2
MAX_DETALLES_POR_CORRIDA = 100


def _slug(termino: str) -> str:
    """Convierte un término de búsqueda a slug de URL. Cualquier
    secuencia de caracteres que no sea letra/dígito/guion bajo se
    colapsa a un solo guion — así ningún carácter especial (/, .., #, ?)
    puede llegar intacto a la URL. "cajero/a" -> "cajero-a";
    "a..b" -> "a-b" (nunca sobrevive ".." literal)."""
    limpio = re.sub(r"[^\w]+", "-", (termino or "").strip().lower())
    return limpio.strip("-")


def _limpia(html: str) -> str:
    texto = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()
    return html_mod.unescape(texto)


def _fecha_relativa(texto: str, hoy: date) -> str | None:
    """'Hace 3 días', 'Hace 5 horas', 'Ayer', 'Hoy' → fecha ISO."""
    t = texto.lower()
    if "hoy" in t or "hora" in t or "minuto" in t:
        return hoy.isoformat()
    if "ayer" in t:
        return (hoy - timedelta(days=1)).isoformat()
    m = re.search(r"hace\s+(\d+)\s+d[ií]as?", t)
    if m:
        return (hoy - timedelta(days=int(m.group(1)))).isoformat()
    m = re.search(r"hace\s+m[aá]s de\s+(\d+)\s+d[ií]as?", t)
    if m:
        return (hoy - timedelta(days=int(m.group(1)))).isoformat()
    return None


_MAX_BLOQUE = 20_000  # cota dura: ningún listado real de Computrabajo se
                        # acerca a este tamaño por oferta; evita que un
                        # regex tenga que escanear HTML mal formado o
                        # truncado sin límite (backtracking catastrófico
                        # verificado: una página de ~80KB sin </article>
                        # tardaba ~14s; con esta cota, tiempo acotado).


def _parse_listado(html: str, hoy: date) -> list[dict]:
    ofertas = []
    posiciones = [m.start() for m in re.finditer(r"<article\b", html)]
    posiciones.append(len(html))
    for i in range(len(posiciones) - 1):
        fin = min(posiciones[i + 1], posiciones[i] + _MAX_BLOQUE)
        bloque = html[posiciones[i]:fin]
        if "box_offer" not in bloque:
            continue
        link = re.search(r'href="(/ofertas-de-trabajo/[^"#]+)', bloque)
        titulo = re.search(r'js-o-link[^>]*>\s*([^<]{3,120})', bloque)
        if not (link and titulo):
            continue
        empresa = re.search(r'<p class="dFlex[^"]*"[^>]*>(.*?)</p>', bloque, re.S)
        lugar = re.search(r'<span class="mr10">\s*([^<]{3,80})', bloque)
        fecha = re.search(r'<p class="fs13[^"]*"[^>]*>\s*([^<]{3,40})<', bloque)
        ofertas.append({
            "job_url": BASE + link.group(1).strip(),
            "title": _limpia(titulo.group(1)),
            "company": _limpia(empresa.group(1)) if empresa else "No informada",
            "location": _limpia(lugar.group(1)) if lugar else "Chile",
            "date_posted": _fecha_relativa(fecha.group(1), hoy) if fecha else None,
        })
    return ofertas


def _descripcion_detalle(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=25)
    parrafos = re.findall(r'<p class="mbB[^"]*"[^>]*>(.*?)</p>', r.text, re.S)
    listas = re.findall(r'<ul class="disc[^"]*"[^>]*>(.*?)</ul>', r.text, re.S)
    partes = [jobposting.texto(p) for p in parrafos]
    partes += [jobposting.texto(f"<ul>{u}</ul>") for u in listas]
    return "\n\n".join(x for x in partes if x)[:8000]


def fetch_all(terminos: list[str], excluir_urls=None,
              max_detalles: int = MAX_DETALLES_POR_CORRIDA
              ) -> tuple[list[dict], set, str | None]:
    excluir_urls = excluir_urls or set()
    hoy = date.today()
    vistas, filas, error = set(), [], None
    for q in terminos:
        slug = _slug(q)
        for pagina in range(1, PAGINAS_POR_BUSQUEDA + 1):
            url = f"{BASE}/trabajo-de-{slug}" + (f"?p={pagina}" if pagina > 1 else "")
            try:
                r = requests.get(url, headers=HEADERS, timeout=30)
                r.raise_for_status()
                for o in _parse_listado(r.text, hoy):
                    if o["job_url"] not in vistas:
                        o["search_term"] = q
                        vistas.add(o["job_url"])
                        filas.append(o)
            except Exception as e:
                error = str(e)[:200]
                print(f"[ERROR] computrabajo '{q}' p{pagina}: {e}")
            time.sleep(1)

    nuevas = [f for f in filas if f["job_url"] not in excluir_urls][:max_detalles]
    for f in nuevas:
        try:
            f["description"] = _descripcion_detalle(f["job_url"])
        except Exception as e:
            f["description"] = ""
            error = str(e)[:200]
        time.sleep(0.8)

    for f in nuevas:
        f["site"] = "computrabajo"
        for col, val in (("job_type", None), ("is_remote", "False"),
                         ("min_amount", None), ("max_amount", None),
                         ("currency", None), ("interval", None)):
            f[col] = val

    print(f"[OK] computrabajo: {len(nuevas)} ofertas nuevas "
          f"({len(filas)} vistas en listados)")
    return nuevas, vistas, error
