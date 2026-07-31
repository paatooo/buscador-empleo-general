# -*- coding: utf-8 -*-
from unittest.mock import patch

import db
import recolectar

COLUMNAS_OFERTA = ("job_url", "site", "search_term", "title", "company",
                   "location", "date_posted", "job_type", "is_remote",
                   "min_amount", "max_amount", "currency", "interval",
                   "description", "scrape_date")


def _fila_falsa(url, termino):
    return {"job_url": url, "site": "getonbrd", "search_term": termino,
            "title": "Cajero", "company": "X", "location": "Chile",
            "date_posted": "2026-08-01", "job_type": None,
            "is_remote": "False", "min_amount": None, "max_amount": None,
            "currency": None, "interval": None, "description": "texto",
            "scrape_date": "2026-08-01"}


def test_run_consulta_terminos_pendientes_y_corre_las_cuatro_fuentes(tmp_path):
    eng = db.engine(tmp_path / "r.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "cajero", "usuario", "2026-08-01T00:00:00")

    with patch("fuente_getonbrd.fetch_all",
               return_value=([_fila_falsa("http://gb/1", "cajero")], set(), None)) as m_gb, \
         patch("fuente_computrabajo.fetch_all",
               return_value=([], set(), None)) as m_ct, \
         patch("fuente_trabajando.fetch_all",
               return_value=([], set(), None)) as m_tb, \
         patch("fuente_laborum.fetch_all",
               return_value=([], set(), None)) as m_lb, \
         patch("analizar.run", return_value={"analizadas": 0, "duplicadas": 0}):
        resumen = recolectar.run(eng)

    m_gb.assert_called_once()
    m_ct.assert_called_once()
    m_tb.assert_called_once()
    m_lb.assert_called_once()
    assert resumen["terminos_corridos"] == 1
    assert resumen["ofertas_nuevas"] == 1


def test_run_guarda_las_ofertas_encontradas(tmp_path):
    eng = db.engine(tmp_path / "r2.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "cajero", "usuario", "2026-08-01T00:00:00")

    with patch("fuente_getonbrd.fetch_all",
               return_value=([_fila_falsa("http://gb/1", "cajero")], set(), None)), \
         patch("fuente_computrabajo.fetch_all", return_value=([], set(), None)), \
         patch("fuente_trabajando.fetch_all", return_value=([], set(), None)), \
         patch("fuente_laborum.fetch_all", return_value=([], set(), None)), \
         patch("analizar.run", return_value={"analizadas": 1, "duplicadas": 0}):
        recolectar.run(eng)

    assert db.escalar(eng, "SELECT COUNT(*) FROM ofertas") == 1


def test_run_registra_la_corrida_de_cada_termino(tmp_path):
    eng = db.engine(tmp_path / "r3.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "cajero", "usuario", "2026-08-01T00:00:00")

    with patch("fuente_getonbrd.fetch_all",
               return_value=([_fila_falsa("http://gb/1", "cajero")], set(), None)), \
         patch("fuente_computrabajo.fetch_all", return_value=([], set(), None)), \
         patch("fuente_trabajando.fetch_all", return_value=([], set(), None)), \
         patch("fuente_laborum.fetch_all", return_value=([], set(), None)), \
         patch("analizar.run", return_value={"analizadas": 1, "duplicadas": 0}):
        recolectar.run(eng)

    fila = db.consultar(eng, "SELECT ultima_corrida, ofertas_ultimas"
                             " FROM terminos_busqueda WHERE termino = 'cajero'")[0]
    assert fila[0] is not None
    assert fila[1] == 1


def test_run_corta_por_presupuesto_de_tiempo(tmp_path):
    eng = db.engine(tmp_path / "r4.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "termino1", "usuario", "2026-08-01T00:00:00")
    db.agregar_termino(eng, "termino2", "usuario", "2026-08-01T00:00:00")

    llamados = []

    def fake_getonbrd(terminos, **kwargs):
        llamados.append(terminos[0] if terminos else None)
        return [], set(), None

    with patch("fuente_getonbrd.fetch_all", side_effect=fake_getonbrd), \
         patch("fuente_computrabajo.fetch_all", return_value=([], set(), None)), \
         patch("fuente_trabajando.fetch_all", return_value=([], set(), None)), \
         patch("fuente_laborum.fetch_all", return_value=([], set(), None)), \
         patch("analizar.run", return_value={"analizadas": 0, "duplicadas": 0}), \
         patch("time.monotonic", side_effect=[0, 0, 100, 100, 9999]):
        # El segundo chequeo de tiempo (100s) ya no debe alcanzar para un
        # presupuesto de 50s: solo se corre el primer término.
        resumen = recolectar.run(eng, presupuesto_segundos=50)

    assert resumen["terminos_corridos"] == 1


def test_run_sin_terminos_pendientes_no_falla(tmp_path):
    eng = db.engine(tmp_path / "r5.db")
    db.ensure_schema(eng)
    with patch("analizar.run", return_value={"analizadas": 0, "duplicadas": 0}):
        resumen = recolectar.run(eng)
    assert resumen["terminos_corridos"] == 0


def test_run_llama_al_analizador_al_final(tmp_path):
    eng = db.engine(tmp_path / "r6.db")
    db.ensure_schema(eng)
    with patch("analizar.run", return_value={"analizadas": 3, "duplicadas": 1}) as m:
        resumen = recolectar.run(eng)
    m.assert_called_once()
    assert resumen["analizadas"] == 3


def test_run_actualiza_last_seen_de_ofertas_que_siguen_vigentes(tmp_path):
    eng = db.engine(tmp_path / "r7.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "cajero", "usuario", "2026-08-01T00:00:00")

    fila_dia1 = _fila_falsa("http://gb/1", "cajero")
    fila_dia1["date_posted"] = "2026-08-01"

    # Corrida 1: la oferta se inserta por primera vez.
    with patch("fuente_getonbrd.fetch_all",
               return_value=([fila_dia1], {"http://gb/1"}, None)), \
         patch("fuente_computrabajo.fetch_all", return_value=([], set(), None)), \
         patch("fuente_trabajando.fetch_all", return_value=([], set(), None)), \
         patch("fuente_laborum.fetch_all", return_value=([], set(), None)):
        recolectar.run(eng)

    # Corrida 2, varios días después: la misma oferta sigue en el sitio
    # (viene en `vigentes`) pero no es nueva (no vuelve en `filas`).
    with patch("fuente_getonbrd.fetch_all",
               return_value=([], {"http://gb/1"}, None)), \
         patch("fuente_computrabajo.fetch_all", return_value=([], set(), None)), \
         patch("fuente_trabajando.fetch_all", return_value=([], set(), None)), \
         patch("fuente_laborum.fetch_all", return_value=([], set(), None)):
        recolectar.run(eng)

    last_seen = db.consultar(eng, "SELECT last_seen FROM ofertas"
                                  " WHERE job_url = 'http://gb/1'")[0][0]
    # last_seen debe haberse refrescado en la segunda corrida, no seguir
    # clavado en la fecha de la primera inserción.
    hoy = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc).date().isoformat()
    assert last_seen == hoy
