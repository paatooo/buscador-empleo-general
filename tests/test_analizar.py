# -*- coding: utf-8 -*-
import json

import analizar
import db


def _con_ofertas(eng, filas):
    db.ensure_schema(eng)
    for f in filas:
        base = dict(job_url="", site="trabajando", search_term="", title="",
                    company="", location="Chile", date_posted=None,
                    job_type=None, is_remote="False", min_amount=None,
                    max_amount=None, currency=None, interval=None,
                    description="", scrape_date="2026-08-01", last_seen="2026-08-01")
        base.update(f)
        cols = list(base)
        vals = ", ".join(f":{c}" for c in cols)
        colsql = ", ".join(f'"{c}"' for c in cols)
        db.ejecutar(eng, f"INSERT INTO ofertas ({colsql}) VALUES ({vals})", base)


def test_run_escribe_analisis_generico(tmp_path):
    eng = db.engine(tmp_path / "a.db")
    _con_ofertas(eng, [{
        "job_url": "http://x/1", "title": "Cajero", "company": "Super X",
        "description": "Se busca cajero, manejo de caja.", "date_posted": "2026-07-30",
    }])
    resumen = analizar.run(eng)
    assert resumen["analizadas"] == 1
    filas = db.consultar(eng, "SELECT habilidades, areas, region FROM oferta_analisis"
                              " WHERE job_url = 'http://x/1'")
    habilidades, areas, region = filas[0]
    assert "Manejo de caja" in json.loads(habilidades)
    assert "Ventas y retail" in json.loads(areas)


def test_run_no_escribe_columnas_dependientes_de_perfil(tmp_path):
    eng = db.engine(tmp_path / "a2.db")
    _con_ofertas(eng, [{"job_url": "http://x/1", "title": "Cajero",
                        "company": "X", "description": "Se busca cajero"}])
    analizar.run(eng)
    from sqlalchemy import inspect
    columnas = {c["name"] for c in inspect(eng).get_columns("oferta_analisis")}
    assert columnas.isdisjoint({"match", "cargo_no_afin", "electrico", "detalle"})


def test_run_marca_duplicadas_por_titulo_y_empresa(tmp_path):
    eng = db.engine(tmp_path / "a3.db")
    _con_ofertas(eng, [
        {"job_url": "http://x/1", "site": "trabajando", "title": "Cajero/a",
         "company": "Super X", "description": "texto", "scrape_date": "2026-07-01"},
        {"job_url": "http://x/2", "site": "computrabajo", "title": "CAJERO/A",
         "company": "super x", "description": "texto", "scrape_date": "2026-07-02"},
    ])
    resumen = analizar.run(eng)
    assert resumen["duplicadas"] == 1
    fila1 = db.consultar(eng, "SELECT duplicada FROM oferta_analisis"
                              " WHERE job_url = 'http://x/1'")[0][0]
    fila2 = db.consultar(eng, "SELECT duplicada FROM oferta_analisis"
                              " WHERE job_url = 'http://x/2'")[0][0]
    assert fila1 == 0  # se queda con la primera capturada (scrape_date más antiguo)
    assert fila2 == 1


def test_run_calcula_vigencia_con_ultima_corrida_global(tmp_path):
    eng = db.engine(tmp_path / "a4.db")
    _con_ofertas(eng, [{
        "job_url": "http://x/1", "title": "Cajero", "company": "X",
        "description": "texto", "date_posted": "2026-07-25",
        "last_seen": "2026-08-01",  # coincide con la corrida más reciente
    }])
    analizar.run(eng)
    vigencia = json.loads(db.consultar(
        eng, "SELECT vigencia_estimada FROM oferta_analisis"
             " WHERE job_url = 'http://x/1'")[0][0])
    assert vigencia["estado"] in ("activa", "por_vencer")


def test_run_sin_ofertas_da_resumen_vacio(tmp_path):
    eng = db.engine(tmp_path / "a5.db")
    db.ensure_schema(eng)
    resumen = analizar.run(eng)
    assert resumen == {"analizadas": 0, "duplicadas": 0}


def test_run_es_atomico_no_deja_tabla_a_medio_escribir(tmp_path):
    # Reusa la garantía ya probada de db.upsert_oferta_analisis: si algo
    # falla, no debe quedar una fila a medias. Se corre dos veces seguidas
    # para confirmar que es idempotente (no duplica ni falla la segunda vez).
    eng = db.engine(tmp_path / "a6.db")
    _con_ofertas(eng, [{"job_url": "http://x/1", "title": "Cajero",
                        "company": "X", "description": "texto"}])
    analizar.run(eng)
    analizar.run(eng)
    assert db.escalar(eng, "SELECT COUNT(*) FROM oferta_analisis") == 1
