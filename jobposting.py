# -*- coding: utf-8 -*-
"""Parser de datos estructurados schema.org/JobPosting (JSON-LD),
compartido por las fuentes que scrapean páginas de detalle. Genérico —no
depende de ningún perfil."""
import html as html_mod
import json
import re


def extraer(html: str) -> dict | None:
    for bloque in re.findall(
            r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
        try:
            d = json.loads(bloque)
        except json.JSONDecodeError:
            continue
        if isinstance(d, list):
            d = next((x for x in d if isinstance(x, dict)
                      and x.get("@type") == "JobPosting"), None)
        if isinstance(d, dict) and d.get("@type") == "JobPosting":
            return d
    return None


def texto(html_desc: str) -> str:
    """HTML → texto plano preservando estructura: párrafos, títulos y viñetas."""
    t = html_desc or ""
    t = re.sub(r"<\s*(br|/p|/div|/h[1-6]|/ul|/ol|/tr)\s*/?>", "\n", t, flags=re.I)
    t = re.sub(r"<\s*li[^>]*>", "\n- ", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html_mod.unescape(t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r" ?\n ?", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def ubicacion(d: dict) -> str:
    loc = d.get("jobLocation") or {}
    if isinstance(loc, list):
        loc = loc[0] if loc else {}
    if not isinstance(loc, dict):
        return str(loc) or "Chile"
    dir_ = loc.get("address") or {}
    if not isinstance(dir_, dict):
        return str(dir_) or "Chile"
    partes = [dir_.get(k) for k in
              ("streetAddress", "addressLocality", "addressRegion")]
    return ", ".join(str(p) for p in partes if p) or "Chile"


def a_fila(d: dict, url: str, site: str) -> dict:
    """JobPosting → fila con el esquema de columnas de `ofertas`."""
    vence = str(d.get("validThrough") or "")[:10]
    desc = texto(d.get("description", ""))
    if vence:
        desc = f"Postulación vigente hasta {vence}. " + desc
    org = d.get("hiringOrganization") or {}
    return {
        "site": site,
        "job_url": url,
        "title": d.get("title"),
        "company": (org.get("name") if isinstance(org, dict) else str(org))
                   or "No informada",
        "location": ubicacion(d),
        "date_posted": str(d.get("datePosted") or "")[:10] or None,
        "job_type": d.get("employmentType"),
        "is_remote": str("TELECOMMUTE" in str(d.get("jobLocationType", ""))),
        "min_amount": None, "max_amount": None,
        "currency": None, "interval": None,
        "description": desc,
    }
