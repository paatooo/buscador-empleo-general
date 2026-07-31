# -*- coding: utf-8 -*-
from unittest.mock import MagicMock, patch

import fuente_laborum

SITEMAP_XML = """<?xml version="1.0"?>
<urlset>
  <url><loc>https://www.laborum.cl/empleos/cajero-supermercado-1</loc></url>
  <url><loc>https://www.laborum.cl/empleos/desarrollador-web-2</loc></url>
</urlset>
"""

HTML_DETALLE = """
<script type="application/ld+json">
{"@type": "JobPosting", "title": "Cajero/a", "description": "<p>Texto</p>",
 "hiringOrganization": {"name": "Empresa X"}}
</script>
"""


def _resp(text, status=200):
    r = MagicMock()
    r.status_code = status
    r.text = text
    r.raise_for_status = MagicMock()
    return r


def test_fetch_all_filtra_por_los_terminos_recibidos():
    def side_effect(url, **kwargs):
        return _resp(SITEMAP_XML) if "sitemap" in url else _resp(HTML_DETALLE)

    with patch("requests.get", side_effect=side_effect):
        filas, vigentes, error = fuente_laborum.fetch_all(["cajero"])
    assert vigentes == {"https://www.laborum.cl/empleos/cajero-supermercado-1"}
    assert len(filas) == 1


def test_fetch_all_excluye_urls_ya_conocidas():
    llamadas_detalle = []

    def side_effect(url, **kwargs):
        if "sitemap" in url:
            return _resp(SITEMAP_XML)
        llamadas_detalle.append(url)
        return _resp(HTML_DETALLE)

    conocida = "https://www.laborum.cl/empleos/cajero-supermercado-1"
    with patch("requests.get", side_effect=side_effect):
        fuente_laborum.fetch_all(["cajero"], excluir_urls={conocida})
    assert llamadas_detalle == []


def test_fetch_all_error_de_sitemap_no_interrumpe():
    with patch("requests.get", side_effect=ConnectionError("timeout")):
        filas, vigentes, error = fuente_laborum.fetch_all(["cajero"])
    assert filas == []
    assert error is not None
