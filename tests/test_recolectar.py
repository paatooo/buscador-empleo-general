# -*- coding: utf-8 -*-
from datetime import datetime, timezone
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
               return_value=([_fila_falsa("http://gb/1", "cajero")],
                             {"http://gb/1"}, None)), \
         patch("fuente_computrabajo.fetch_all", return_value=([], set(), None)), \
         patch("fuente_trabajando.fetch_all", return_value=([], set(), None)), \
         patch("fuente_laborum.fetch_all", return_value=([], set(), None)), \
         patch("analizar.run", return_value={"analizadas": 1, "duplicadas": 0}):
        recolectar.run(eng)

    fila = db.consultar(eng, "SELECT ultima_corrida, ofertas_ultimas"
                             " FROM terminos_busqueda WHERE termino = 'cajero'")[0]
    assert fila[0] is not None
    assert fila[1] == 1


def test_run_ofertas_ultimas_usa_vigentes_no_filas_en_termino_saturado(tmp_path):
    # Término "saturado": todo lo que se encuentra ya es conocido, así que
    # `filas` viene vacío en las fuentes que filtran por `excluir_urls`
    # (computrabajo/trabajando/laborum) aunque el término siga vigente.
    # `ofertas_ultimas` debe reflejar `vigentes` (lo que sigue encontrándose),
    # no `filas` (lo nuevo) — de lo contrario un término productivo pero
    # saturado se ve, incorrectamente, como estéril.
    eng = db.engine(tmp_path / "r3b.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "cajero", "usuario", "2026-08-01T00:00:00")

    with patch("fuente_getonbrd.fetch_all", return_value=([], set(), None)), \
         patch("fuente_computrabajo.fetch_all",
               return_value=([], {"http://ct/1", "http://ct/2"}, None)), \
         patch("fuente_trabajando.fetch_all",
               return_value=([], {"http://tb/1"}, None)), \
         patch("fuente_laborum.fetch_all", return_value=([], set(), None)), \
         patch("analizar.run", return_value={"analizadas": 0, "duplicadas": 0}):
        recolectar.run(eng)

    fila = db.consultar(eng, "SELECT ofertas_ultimas"
                             " FROM terminos_busqueda WHERE termino = 'cajero'")[0]
    assert fila[0] == 3


def test_run_tolera_fuente_que_devuelve_vigentes_none(tmp_path):
    # Una fuente mal implementada que devuelva `vigentes=None` no debe
    # abortar la corrida entera (regresión: `vigentes_totales |= vigentes`
    # estaba fuera del try/except que cubre errores de la fuente).
    eng = db.engine(tmp_path / "r3c.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "cajero", "usuario", "2026-08-01T00:00:00")

    with patch("fuente_getonbrd.fetch_all", return_value=([], None, None)), \
         patch("fuente_computrabajo.fetch_all", return_value=([], set(), None)), \
         patch("fuente_trabajando.fetch_all", return_value=([], set(), None)), \
         patch("fuente_laborum.fetch_all", return_value=([], set(), None)), \
         patch("analizar.run", return_value={"analizadas": 0, "duplicadas": 0}):
        resumen = recolectar.run(eng)

    assert resumen["terminos_corridos"] == 1


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


def test_run_actualiza_last_seen_de_ofertas_que_siguen_vigentes(tmp_path, monkeypatch):
    eng = db.engine(tmp_path / "r7.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "cajero", "usuario", "2026-08-01T00:00:00")

    # Aísla esta prueba de la lógica de exclusión por recencia de
    # terminos_pendientes (ya probada aparte, en otra parte de la suite):
    # acá solo importa si last_seen se refresca entre dos corridas.
    monkeypatch.setattr(db, "terminos_pendientes", lambda eng, **kw: ["cajero"])

    fila_dia1 = _fila_falsa("http://gb/1", "cajero")
    fila_dia1["date_posted"] = "2026-08-01"

    # Corrida 1: la oferta se inserta por primera vez.
    with patch("recolectar.datetime") as m_dt:
        m_dt.now.return_value = datetime(2026, 8, 1, tzinfo=timezone.utc)
        with patch("fuente_getonbrd.fetch_all",
                   return_value=([fila_dia1], {"http://gb/1"}, None)), \
             patch("fuente_computrabajo.fetch_all", return_value=([], set(), None)), \
             patch("fuente_trabajando.fetch_all", return_value=([], set(), None)), \
             patch("fuente_laborum.fetch_all", return_value=([], set(), None)):
            recolectar.run(eng)

    last_seen_1 = db.consultar(eng, "SELECT last_seen FROM ofertas"
                                    " WHERE job_url = 'http://gb/1'")[0][0]
    assert last_seen_1 == "2026-08-01"

    # Corrida 2, varios días después: la misma oferta sigue en el sitio
    # (viene en `vigentes`) pero no es nueva (no vuelve en `filas`).
    with patch("recolectar.datetime") as m_dt:
        m_dt.now.return_value = datetime(2026, 8, 5, tzinfo=timezone.utc)
        with patch("fuente_getonbrd.fetch_all",
                   return_value=([], {"http://gb/1"}, None)), \
             patch("fuente_computrabajo.fetch_all", return_value=([], set(), None)), \
             patch("fuente_trabajando.fetch_all", return_value=([], set(), None)), \
             patch("fuente_laborum.fetch_all", return_value=([], set(), None)):
            recolectar.run(eng)

    last_seen_2 = db.consultar(eng, "SELECT last_seen FROM ofertas"
                                    " WHERE job_url = 'http://gb/1'")[0][0]
    # last_seen debe haberse refrescado en la segunda corrida, no seguir
    # clavado en la fecha de la primera inserción.
    assert last_seen_2 == "2026-08-05"
    assert last_seen_2 != last_seen_1


def _falla(*a, **k):
    return ([], set(), "boom: la red se cayó")


def test_run_no_registra_la_corrida_de_un_termino_si_fallaron_todas_las_fuentes(tmp_path):
    """Una corrida donde ninguna fuente respondió no es información sobre
    el término: si se registrara, `terminos_pendientes` lo excluiría por
    24 horas y después lo trataría como estéril. Una caída de red dejaría
    la recolección muerta un día y degradaría el catálogo entero."""
    eng = db.engine(tmp_path / "rf1.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "cajero", "base", "2026-08-01T00:00:00")

    with patch("fuente_getonbrd.fetch_all", _falla), \
         patch("fuente_computrabajo.fetch_all", _falla), \
         patch("fuente_trabajando.fetch_all", _falla), \
         patch("fuente_laborum.fetch_all", _falla):
        resumen = recolectar.run(eng)

    fila = db.consultar(eng, "SELECT ultima_corrida, ofertas_ultimas"
                             " FROM terminos_busqueda WHERE termino = 'cajero'")[0]
    assert fila[0] is None, "no debe quedar marcado como corrido"
    assert resumen["terminos_fallidos"] == 1
    assert resumen["terminos_corridos"] == 0
    assert db.terminos_pendientes(eng) == ["cajero"], "debe poder reintentarse"


def test_run_si_registra_un_termino_esteril_cuando_las_fuentes_si_respondieron(tmp_path):
    """Cero ofertas SIN errores sí es información: el término es estéril y
    corresponde despriorizarlo. Es justo lo contrario del caso de arriba."""
    eng = db.engine(tmp_path / "rf2.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "cajero", "base", "2026-08-01T00:00:00")

    vacio = ([], set(), None)
    with patch("fuente_getonbrd.fetch_all", return_value=vacio), \
         patch("fuente_computrabajo.fetch_all", return_value=vacio), \
         patch("fuente_trabajando.fetch_all", return_value=vacio), \
         patch("fuente_laborum.fetch_all", return_value=vacio):
        resumen = recolectar.run(eng)

    fila = db.consultar(eng, "SELECT ultima_corrida, ofertas_ultimas"
                             " FROM terminos_busqueda WHERE termino = 'cajero'")[0]
    assert fila[0] is not None
    assert fila[1] == 0
    assert resumen["terminos_corridos"] == 1
    assert resumen["terminos_fallidos"] == 0


def test_run_registra_el_termino_si_al_menos_una_fuente_respondio(tmp_path):
    eng = db.engine(tmp_path / "rf3.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "cajero", "base", "2026-08-01T00:00:00")

    with patch("fuente_getonbrd.fetch_all",
               return_value=([_fila_falsa("http://gb/9", "cajero")],
                             {"http://gb/9"}, None)), \
         patch("fuente_computrabajo.fetch_all", _falla), \
         patch("fuente_trabajando.fetch_all", _falla), \
         patch("fuente_laborum.fetch_all", _falla):
        resumen = recolectar.run(eng)

    fila = db.consultar(eng, "SELECT ultima_corrida, ofertas_ultimas"
                             " FROM terminos_busqueda WHERE termino = 'cajero'")[0]
    assert fila[0] is not None
    assert resumen["terminos_corridos"] == 1
    assert resumen["terminos_fallidos"] == 0
