# -*- coding: utf-8 -*-
from unittest.mock import MagicMock, patch

import fuente_computrabajo

HTML_LISTADO = """
<article class="box_offer">
  <a href="/ofertas-de-trabajo/oferta-cajero-1234.html" class="js-o-link">
    Cajero/a supermercado
  </a>
  <p class="dFlex">Supermercado Los Andes</p>
  <span class="mr10">Santiago</span>
  <p class="fs13">Hace 2 días</p>
</article>
"""

HTML_DETALLE = """
<p class="mbB">Se busca cajero con experiencia en atención a público.</p>
<ul class="disc"><li>Turno tarde</li><li>Disponibilidad inmediata</li></ul>
"""


def _resp(text, status=200):
    r = MagicMock()
    r.status_code = status
    r.text = text
    r.raise_for_status = MagicMock()
    return r


def test_fetch_all_parsea_el_listado():
    with patch("requests.get", return_value=_resp(HTML_LISTADO)):
        filas, vigentes, error = fuente_computrabajo.fetch_all(["cajero"])
    assert len(filas) >= 1
    fila = filas[0]
    assert fila["title"] == "Cajero/a supermercado"
    assert fila["company"] == "Supermercado Los Andes"
    assert fila["job_url"].endswith("oferta-cajero-1234.html")


def test_fetch_all_usa_los_terminos_recibidos():
    urls_pedidas = []

    def side_effect(url, **kwargs):
        urls_pedidas.append(url)
        return _resp(HTML_LISTADO if "trabajo-de-" in url else HTML_DETALLE)

    with patch("requests.get", side_effect=side_effect):
        fuente_computrabajo.fetch_all(["soldador", "garzon"])
    listados = [u for u in urls_pedidas if "trabajo-de-" in u]
    assert any("trabajo-de-soldador" in u for u in listados)
    assert any("trabajo-de-garzon" in u for u in listados)


def test_fetch_all_trae_la_descripcion_del_detalle():
    def side_effect(url, **kwargs):
        return _resp(HTML_LISTADO if "trabajo-de-" in url else HTML_DETALLE)

    with patch("requests.get", side_effect=side_effect):
        filas, _, _ = fuente_computrabajo.fetch_all(["cajero"])
    assert "atención a público" in filas[0]["description"].lower()


def test_fetch_all_excluye_urls_ya_conocidas_del_detalle():
    llamadas_detalle = []

    def side_effect(url, **kwargs):
        if "trabajo-de-" in url:
            return _resp(HTML_LISTADO)
        llamadas_detalle.append(url)
        return _resp(HTML_DETALLE)

    conocida = "https://cl.computrabajo.com/ofertas-de-trabajo/oferta-cajero-1234.html"
    with patch("requests.get", side_effect=side_effect):
        fuente_computrabajo.fetch_all(["cajero"], excluir_urls={conocida})
    assert llamadas_detalle == []  # no se pidió el detalle de una oferta ya conocida


def test_fetch_all_captura_error_de_listado_sin_interrumpir():
    def side_effect(url, **kwargs):
        if "trabajo-de-falla" in url:
            raise ConnectionError("timeout")
        return _resp(HTML_LISTADO if "trabajo-de-" in url else HTML_DETALLE)

    with patch("requests.get", side_effect=side_effect):
        filas, _, error = fuente_computrabajo.fetch_all(["falla", "cajero"])
    assert error is not None
    assert len(filas) >= 1  # el segundo término sí funcionó
