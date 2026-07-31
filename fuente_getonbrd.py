# -*- coding: utf-8 -*-
"""Fuente Get on Board (getonbrd.com) — API pública.

A diferencia del proyecto de referencia, los términos de búsqueda no están
fijos en el código: los pasa quien llama (`recolectar.py`), leídos de
`terminos_busqueda`. Devuelve `list[dict]`, no `DataFrame` — compatible
directo con `db.upsert_ofertas`.
"""
import time
from datetime import datetime, timezone

import requests

import jobposting

API = "https://www.getonbrd.com/api/v0/search/jobs"
HEADERS = {"User-Agent": "Mozilla/5.0 (buscador-empleo-personalizado; uso personal)"}

# Textos en español para que el motor detecte la modalidad desde la descripción
_MODALIDAD = {
    "hybrid": "Modalidad de trabajo híbrida.",
    "remote": "Trabajo remoto.",
    "fully_remote": "Trabajo 100% remoto.",
    "remote_local": "Trabajo remoto local.",
    "no_remote": "Trabajo presencial.",
}


def fetch(query: str, per_page: int = 50) -> list[dict]:
    resp = requests.get(
        API, headers=HEADERS, timeout=30,
        params={"query": query, "per_page": per_page, "expand": '["company"]'},
    )
    resp.raise_for_status()
    filas = []
    for item in resp.json().get("data", []):
        a = item.get("attributes", {})
        countries = a.get("countries") or ""
        if isinstance(countries, (list, tuple)):
            countries = ", ".join(str(c) for c in countries)
        remoto = bool(a.get("remote"))
        if "Chile" not in countries and not remoto:
            continue  # solo Chile o remoto postulable desde Chile
        try:
            company = a["company"]["data"]["attributes"]["name"]
        except (KeyError, TypeError):
            company = ""
        publicada = None
        if a.get("published_at"):
            publicada = datetime.fromtimestamp(
                a["published_at"], tz=timezone.utc).date().isoformat()
        descripcion = "\n\n".join(
            jobposting.texto(a.get(campo)) for campo in
            ("description", "functions", "desirable", "projects") if a.get(campo)
        )

        def _num(v):
            return v if isinstance(v, (int, float)) else None

        job_url = str(item.get("links", {}).get("public_url") or "")
        if not job_url:
            continue
        filas.append({
            "site": "getonbrd",
            "job_url": job_url,
            "title": str(a.get("title") or ""),
            "company": str(company or ""),
            "location": str(countries or "Chile"),
            "date_posted": publicada,
            "job_type": None,
            "is_remote": str(remoto),
            "min_amount": _num(a.get("min_salary")),
            "max_amount": _num(a.get("max_salary")),
            "currency": "USD" if _num(a.get("min_salary")) else None,
            "interval": "monthly" if _num(a.get("min_salary")) else None,
            "description": _MODALIDAD.get(str(a.get("remote_modality")), "")
                           + " " + descripcion,
        })
    return filas


def fetch_all(terminos: list[str], excluir_urls=None,
              per_page: int = 50) -> tuple[list[dict], set, str | None]:
    """Itera los términos recibidos; retorna (filas, urls_vigentes,
    error_o_None). Trae siempre el resultado completo (la API es liviana),
    por lo que las urls vigentes son las del propio resultado."""
    filas, error = [], None
    for q in terminos:
        try:
            encontradas = fetch(q, per_page)
            for f in encontradas:
                f["search_term"] = q
            filas.extend(encontradas)
            print(f"[OK] getonbrd   '{q}': {len(encontradas)} ofertas")
        except Exception as e:
            error = str(e)[:300]
            print(f"[ERROR] getonbrd '{q}': {e}")
        time.sleep(1)
    vigentes = {f["job_url"] for f in filas}
    return filas, vigentes, error
