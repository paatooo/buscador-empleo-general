# -*- coding: utf-8 -*-
from unittest.mock import MagicMock, patch

import fuente_getonbrd

RESPUESTA_API = {
    "data": [
        {
            "links": {"public_url": "https://www.getonbrd.com/jobs/cajero-1"},
            "attributes": {
                "title": "Cajero/a",
                "countries": ["Chile"],
                "remote": False,
                "remote_modality": "no_remote",
                "published_at": 1751328000,  # 2025-07-01
                "min_salary": None, "max_salary": None,
                "description": "<p>Se busca cajero</p>",
                "company": {"data": {"attributes": {"name": "Empresa X"}}},
            },
        },
        {
            "links": {"public_url": "https://www.getonbrd.com/jobs/dev-2"},
            "attributes": {
                "title": "Developer", "countries": ["Argentina"],
                "remote": False, "remote_modality": "no_remote",
                "published_at": None, "description": "",
                "company": {"data": {"attributes": {"name": "Otra"}}},
            },
        },
    ]
}


def _respuesta_mock(json_data, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


def test_fetch_devuelve_filas_de_chile():
    with patch("requests.get", return_value=_respuesta_mock(RESPUESTA_API)):
        filas = fuente_getonbrd.fetch("cajero")
    assert len(filas) == 1
    assert filas[0]["title"] == "Cajero/a"
    assert filas[0]["site"] == "getonbrd"
    assert filas[0]["job_url"] == "https://www.getonbrd.com/jobs/cajero-1"


def test_fetch_descarta_ofertas_fuera_de_chile_y_no_remotas():
    with patch("requests.get", return_value=_respuesta_mock(RESPUESTA_API)):
        filas = fuente_getonbrd.fetch("cajero")
    urls = {f["job_url"] for f in filas}
    assert "https://www.getonbrd.com/jobs/dev-2" not in urls


def test_fetch_sin_resultados_da_lista_vacia():
    with patch("requests.get", return_value=_respuesta_mock({"data": []})):
        assert fuente_getonbrd.fetch("cargo-inexistente") == []


def test_fetch_all_usa_los_terminos_recibidos_no_una_lista_fija():
    # Requisito central del proyecto: los términos vienen de la base, no
    # de una constante en el código.
    with patch("requests.get", return_value=_respuesta_mock(RESPUESTA_API)) as m:
        fuente_getonbrd.fetch_all(["soldador", "garzon"])
    llamadas = [c.kwargs["params"]["query"] for c in m.call_args_list]
    assert llamadas == ["soldador", "garzon"]


def test_fetch_all_devuelve_urls_vigentes_y_sin_error():
    with patch("requests.get", return_value=_respuesta_mock(RESPUESTA_API)):
        filas, vigentes, error = fuente_getonbrd.fetch_all(["cajero"])
    assert len(filas) == 1
    assert vigentes == {"https://www.getonbrd.com/jobs/cajero-1"}
    assert error is None


def test_fetch_all_captura_error_sin_interrumpir_los_demas_terminos():
    def side_effect(*args, **kwargs):
        if kwargs["params"]["query"] == "falla":
            raise ConnectionError("timeout")
        return _respuesta_mock(RESPUESTA_API)

    with patch("requests.get", side_effect=side_effect):
        filas, vigentes, error = fuente_getonbrd.fetch_all(["falla", "cajero"])
    assert error is not None
    assert len(filas) == 1  # el segundo término sí funcionó
