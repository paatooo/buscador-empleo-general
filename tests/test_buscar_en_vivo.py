# -*- coding: utf-8 -*-
from unittest.mock import patch

import buscar_en_vivo
import db


def _fila_falsa(url, cargo, site="getonbrd"):
    return {"job_url": url, "site": site, "search_term": cargo,
            "title": "Cajero", "company": "X", "location": "Chile",
            "date_posted": "2026-08-01", "job_type": None,
            "is_remote": "False", "min_amount": None, "max_amount": None,
            "currency": None, "interval": None, "description": "texto de cajero",
            "scrape_date": "2026-08-07"}


def test_buscar_persiste_lo_encontrado_y_lo_deja_analizado(tmp_path):
    eng = db.engine(tmp_path / "b1.db")
    db.ensure_schema(eng)
    with patch("fuente_getonbrd.fetch_all",
               return_value=([_fila_falsa("http://gb/1", "cajero")],
                             {"http://gb/1"}, None)), \
         patch("fuente_trabajando.fetch_all", return_value=([], set(), None)), \
         patch("fuente_laborum.fetch_all", return_value=([], set(), None)), \
         patch("fuente_computrabajo.fetch_all", return_value=([], set(), None)):
        resumen = buscar_en_vivo.buscar(eng, ["cajero"],
                                        ahora="2026-08-07T10:00:00")

    assert resumen["buscados"] == ["cajero"]
    assert resumen["ofertas_nuevas"] == {"cajero": 1}
    assert resumen["reutilizados"] == []
    assert resumen["en_cola"] == []
    assert db.escalar(eng, "SELECT COUNT(*) FROM ofertas") == 1
    fila = db.consultar(eng, "SELECT habilidades FROM oferta_analisis"
                             " WHERE job_url = 'http://gb/1'")
    assert fila, "la oferta nueva debe quedar analizada, no solo insertada"


def test_buscar_registra_la_corrida_del_cargo(tmp_path):
    eng = db.engine(tmp_path / "b2.db")
    db.ensure_schema(eng)
    with patch("fuente_getonbrd.fetch_all",
               return_value=([_fila_falsa("http://gb/1", "cajero")],
                             {"http://gb/1"}, None)), \
         patch("fuente_trabajando.fetch_all", return_value=([], set(), None)), \
         patch("fuente_laborum.fetch_all", return_value=([], set(), None)), \
         patch("fuente_computrabajo.fetch_all", return_value=([], set(), None)):
        buscar_en_vivo.buscar(eng, ["cajero"], ahora="2026-08-07T10:00:00")

    fila = db.consultar(eng, "SELECT origen, ultima_corrida, ofertas_ultimas"
                             " FROM terminos_busqueda WHERE termino = 'cajero'")[0]
    assert fila[0] == "usuario"
    assert fila[1] == "2026-08-07T10:00:00"
    assert fila[2] == 1


def test_buscar_cargo_reciente_no_vuelve_a_scrapear(tmp_path):
    eng = db.engine(tmp_path / "b3.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "cajero", "base", "2026-08-06T00:00:00")
    db.registrar_corrida_termino(eng, "cajero", 5, "2026-08-06T10:00:00")

    with patch("fuente_getonbrd.fetch_all") as m_gb, \
         patch("fuente_trabajando.fetch_all") as m_tb, \
         patch("fuente_laborum.fetch_all") as m_lb, \
         patch("fuente_computrabajo.fetch_all") as m_ct:
        # "ahora" es 12 horas después de la corrida: sigue dentro de 24h
        resumen = buscar_en_vivo.buscar(eng, ["cajero"],
                                        ahora="2026-08-06T22:00:00")

    m_gb.assert_not_called()
    m_tb.assert_not_called()
    m_lb.assert_not_called()
    m_ct.assert_not_called()
    assert resumen["reutilizados"] == ["cajero"]
    assert resumen["buscados"] == []


def test_buscar_cargo_corrido_hace_mas_de_24h_si_vuelve_a_scrapear(tmp_path):
    eng = db.engine(tmp_path / "b4.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "cajero", "base", "2026-08-04T00:00:00")
    db.registrar_corrida_termino(eng, "cajero", 0, "2026-08-04T10:00:00")

    with patch("fuente_getonbrd.fetch_all",
               return_value=([], set(), None)) as m_gb, \
         patch("fuente_trabajando.fetch_all", return_value=([], set(), None)), \
         patch("fuente_laborum.fetch_all", return_value=([], set(), None)), \
         patch("fuente_computrabajo.fetch_all", return_value=([], set(), None)):
        resumen = buscar_en_vivo.buscar(eng, ["cajero"],
                                        ahora="2026-08-06T22:00:00")

    m_gb.assert_called_once()
    assert resumen["buscados"] == ["cajero"]


def test_buscar_ninguna_fuente_responde_no_registra_la_corrida(tmp_path):
    eng = db.engine(tmp_path / "b5.db")
    db.ensure_schema(eng)

    def falla(*a, **k):
        return [], set(), "boom: la red se cayó"

    with patch("fuente_getonbrd.fetch_all", falla), \
         patch("fuente_trabajando.fetch_all", falla), \
         patch("fuente_laborum.fetch_all", falla), \
         patch("fuente_computrabajo.fetch_all", falla):
        resumen = buscar_en_vivo.buscar(eng, ["cajero"], ahora="2026-08-07T10:00:00")

    fila = db.consultar(eng, "SELECT ultima_corrida FROM terminos_busqueda"
                             " WHERE termino = 'cajero'")[0]
    assert fila[0] is None, "no debe quedar marcado como corrido"

    assert "cajero" in resumen["en_cola"], \
        "un cargo nunca buscado (ninguna fuente respondió) debe quedar pendiente"
    assert "cajero" not in resumen["buscados"], \
        "no debe reportarse como buscado si ninguna fuente respondió"
    assert resumen["ofertas_nuevas"]["cajero"] == 0, \
        "el conteo debe reflejar que no se insertó nada, aunque el cargo" \
        " haya sido intentado (y no registrado como corrido)"


def test_buscar_corta_fuentes_por_presupuesto_dentro_de_un_cargo(tmp_path):
    eng = db.engine(tmp_path / "b6.db")
    db.ensure_schema(eng)

    with patch("fuente_getonbrd.fetch_all",
               return_value=([], set(), None)) as m_gb, \
         patch("fuente_trabajando.fetch_all",
               return_value=([], set(), None)) as m_tb, \
         patch("fuente_laborum.fetch_all",
               return_value=([], set(), None)) as m_lb, \
         patch("fuente_computrabajo.fetch_all",
               return_value=([], set(), None)) as m_ct, \
         patch("time.monotonic", side_effect=[0, 0, 0, 0, 100]):
        # inicio=0; chequeo antes del cargo=0 (ok); antes de getonbrd=0
        # (ok, corre); antes de trabajando=0 (ok, corre); antes de
        # laborum=100 (excede presupuesto de 50s, corta ahí).
        resumen = buscar_en_vivo.buscar(eng, ["cajero"], presupuesto_segundos=50,
                                        ahora="2026-08-07T10:00:00")

    m_gb.assert_called_once()
    m_tb.assert_called_once()
    m_lb.assert_not_called()
    m_ct.assert_not_called()
    assert resumen["agotado"] is True
    # El bucle de fuentes se cortó a mitad de camino (solo 2 de 4
    # respondieron) — no se registra como corrido, aunque algunas fuentes
    # sí hayan respondido: registrarlo excluiría el término de
    # `terminos_pendientes` por 24h y podría despriorizarlo como estéril
    # con datos incompletos.
    assert resumen["buscados"] == []
    assert resumen["en_cola"] == ["cajero"]

    fila = db.consultar(eng, "SELECT ultima_corrida FROM terminos_busqueda"
                             " WHERE termino = 'cajero'")[0]
    assert fila[0] is None, \
        "un cargo cortado por presupuesto no debe quedar marcado como corrido"


def test_buscar_reporta_lo_insertado_aunque_se_corte_por_presupuesto(tmp_path):
    """Getonbrd alcanza a responder (y a insertar una oferta) antes de que
    el presupuesto corte el resto de las fuentes — ese hallazgo no debe
    perderse del resumen, aunque el cargo termine en en_cola en vez de
    buscados: si no, la app diría "no encontramos nada" mientras la
    oferta ya está guardada y visible (la caché se limpia siempre)."""
    eng = db.engine(tmp_path / "b6b.db")
    db.ensure_schema(eng)

    with patch("fuente_getonbrd.fetch_all",
               return_value=([_fila_falsa("http://gb/1", "cajero")],
                             {"http://gb/1"}, None)), \
         patch("fuente_trabajando.fetch_all", return_value=([], set(), None)), \
         patch("fuente_laborum.fetch_all", return_value=([], set(), None)), \
         patch("fuente_computrabajo.fetch_all", return_value=([], set(), None)), \
         patch("time.monotonic", side_effect=[0, 0, 0, 100]):
        # inicio=0; chequeo antes del cargo=0 (ok); antes de getonbrd=0
        # (ok, corre e inserta); antes de trabajando=100 (excede
        # presupuesto de 50s, corta ahí).
        resumen = buscar_en_vivo.buscar(eng, ["cajero"], presupuesto_segundos=50,
                                        ahora="2026-08-07T10:00:00")

    assert resumen["en_cola"] == ["cajero"]
    assert resumen["ofertas_nuevas"]["cajero"] == 1
    assert db.escalar(eng, "SELECT COUNT(*) FROM ofertas") == 1


def test_buscar_dos_cargos_el_segundo_queda_en_cola_por_presupuesto(tmp_path):
    eng = db.engine(tmp_path / "b7.db")
    db.ensure_schema(eng)

    with patch("fuente_getonbrd.fetch_all", return_value=([], set(), None)), \
         patch("fuente_trabajando.fetch_all", return_value=([], set(), None)), \
         patch("fuente_laborum.fetch_all", return_value=([], set(), None)), \
         patch("fuente_computrabajo.fetch_all", return_value=([], set(), None)), \
         patch("time.monotonic", side_effect=[0, 0, 0, 0, 0, 0, 100]):
        # inicio=0; cargo1: chequeo=0(ok), 4 fuentes con chequeo=0 cada
        # una (todas corren); cargo2: chequeo=100 (excede, no llega a
        # scrapear, queda en cola).
        resumen = buscar_en_vivo.buscar(eng, ["cajero", "reponedor"],
                                        presupuesto_segundos=50,
                                        ahora="2026-08-07T10:00:00")

    assert resumen["buscados"] == ["cajero"]
    assert resumen["en_cola"] == ["reponedor"]
    assert resumen["agotado"] is True
    # el que quedó en cola igual se registra para la corrida programada
    assert db.escalar(
        eng, "SELECT COUNT(*) FROM terminos_busqueda WHERE termino = 'reponedor'"
    ) == 1


def test_buscar_refresca_last_seen_de_ofertas_confirmadas_vigentes(tmp_path):
    eng = db.engine(tmp_path / "b6b.db")
    db.ensure_schema(eng)
    # Oferta ya conocida (no nueva) con un last_seen viejo.
    fila_vieja = _fila_falsa("http://gb/viejo", "cajero")
    fila_vieja["last_seen"] = "2026-07-01"
    db.upsert_ofertas(eng, [fila_vieja], list(fila_vieja.keys()))

    with patch("fuente_getonbrd.fetch_all",
               return_value=([], {"http://gb/viejo"}, None)), \
         patch("fuente_trabajando.fetch_all", return_value=([], set(), None)), \
         patch("fuente_laborum.fetch_all", return_value=([], set(), None)), \
         patch("fuente_computrabajo.fetch_all", return_value=([], set(), None)):
        buscar_en_vivo.buscar(eng, ["cajero"], ahora="2026-08-07T10:00:00")

    fila = db.consultar(eng, "SELECT last_seen FROM ofertas"
                             " WHERE job_url = 'http://gb/viejo'")[0]
    assert fila[0] == "2026-08-07", \
        "una oferta confirmada vigente hoy debe refrescar su last_seen aunque no sea nueva"


def test_buscar_llama_on_progreso_por_cada_cargo(tmp_path):
    eng = db.engine(tmp_path / "b8.db")
    db.ensure_schema(eng)
    llamadas = []

    with patch("fuente_getonbrd.fetch_all", return_value=([], set(), None)), \
         patch("fuente_trabajando.fetch_all", return_value=([], set(), None)), \
         patch("fuente_laborum.fetch_all", return_value=([], set(), None)), \
         patch("fuente_computrabajo.fetch_all", return_value=([], set(), None)):
        buscar_en_vivo.buscar(eng, ["cajero", "reponedor"],
                              ahora="2026-08-07T10:00:00",
                              on_progreso=lambda i, t, c: llamadas.append((i, t, c)))

    assert llamadas == [(1, 2, "cajero"), (2, 2, "reponedor")]


def test_semaforo_permite_hasta_max_simultaneas():
    adquiridos = [buscar_en_vivo._semaforo.acquire(blocking=False)
                 for _ in range(buscar_en_vivo.MAX_SIMULTANEAS)]
    try:
        assert all(adquiridos)
        assert buscar_en_vivo._semaforo.acquire(blocking=False) is False
    finally:
        for ok in adquiridos:
            if ok:
                buscar_en_vivo._semaforo.release()


def test_buscar_con_el_cupo_lleno_no_scrapea_y_encola(tmp_path):
    eng = db.engine(tmp_path / "b9.db")
    db.ensure_schema(eng)
    for _ in range(buscar_en_vivo.MAX_SIMULTANEAS):
        buscar_en_vivo._semaforo.acquire()
    try:
        with patch("fuente_getonbrd.fetch_all") as m_gb, \
             patch("fuente_trabajando.fetch_all") as m_tb, \
             patch("fuente_laborum.fetch_all") as m_lb, \
             patch("fuente_computrabajo.fetch_all") as m_ct:
            resumen = buscar_en_vivo.buscar(eng, ["cajero"],
                                            ahora="2026-08-07T10:00:00")
        m_gb.assert_not_called()
        m_tb.assert_not_called()
        m_lb.assert_not_called()
        m_ct.assert_not_called()
        assert resumen == {"buscados": [], "reutilizados": [],
                           "en_cola": ["cajero"], "ofertas_nuevas": {},
                           "agotado": False}
        assert db.escalar(
            eng, "SELECT COUNT(*) FROM terminos_busqueda WHERE termino = 'cajero'"
        ) == 1
    finally:
        for _ in range(buscar_en_vivo.MAX_SIMULTANEAS):
            buscar_en_vivo._semaforo.release()
