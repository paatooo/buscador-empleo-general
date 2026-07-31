# -*- coding: utf-8 -*-
"""El esquema debe crearse igual en SQLite (local) y en Postgres (nube).
Se prueba contra SQLite temporal; el SQL usado es portable."""
from sqlalchemy import inspect

import db


def test_engine_local_es_sqlite(tmp_path):
    assert not db.es_nube(db.engine(tmp_path / "x.db"))


def test_engine_reusa_el_mismo_objeto_para_la_misma_ruta(tmp_path):
    """Antes cada llamada a engine() abría una conexión nueva desde cero
    (TCP+TLS) incluso con la misma ruta en el mismo proceso — eso
    multiplicaba la latencia de cada operación cruzando de región hacia
    Supabase. Debe reusar el Engine."""
    a = db.engine(tmp_path / "x.db")
    b = db.engine(tmp_path / "x.db")
    assert a is b


def test_engine_rutas_distintas_dan_motores_distintos(tmp_path):
    a = db.engine(tmp_path / "a.db")
    b = db.engine(tmp_path / "b.db")
    assert a is not b


def test_ensure_schema_crea_todas_las_tablas(tmp_path):
    eng = db.engine(tmp_path / "test.db")
    db.ensure_schema(eng)
    tablas = set(inspect(eng).get_table_names())
    assert {"usuarios", "marcas", "terminos_busqueda", "ofertas",
            "snapshots", "oferta_analisis"} <= tablas


def test_ensure_schema_es_idempotente(tmp_path):
    eng = db.engine(tmp_path / "test.db")
    db.ensure_schema(eng)
    db.ensure_schema(eng)  # segunda corrida no debe fallar


def test_ejecutar_consultar_escalar(tmp_path):
    eng = db.engine(tmp_path / "test.db")
    db.ejecutar(eng, "CREATE TABLE t (x TEXT)")
    db.ejecutar(eng, "INSERT INTO t VALUES (:v)", {"v": "hola"})
    assert db.escalar(eng, "SELECT x FROM t") == "hola"
    assert db.consultar(eng, "SELECT x FROM t") == [("hola",)]


def test_upsert_usuario_crea_y_actualiza(tmp_path):
    eng = db.engine(tmp_path / "u.db")
    db.ensure_schema(eng)
    db.upsert_usuario(eng, "ana@x.cl", '{"cargos_buscados": ["cajero"]}',
                      "2026-07-30")
    fila = db.cargar_usuario(eng, "ana@x.cl")
    assert fila["perfil_json"] == '{"cargos_buscados": ["cajero"]}'
    assert fila["creado_en"] == "2026-07-30"

    db.upsert_usuario(eng, "ana@x.cl", '{"cargos_buscados": ["guardia"]}',
                      "2026-08-01")
    fila = db.cargar_usuario(eng, "ana@x.cl")
    assert fila["perfil_json"] == '{"cargos_buscados": ["guardia"]}'
    assert fila["creado_en"] == "2026-07-30"  # no se pisa al actualizar
    assert db.escalar(eng, "SELECT COUNT(*) FROM usuarios") == 1  # sin duplicar


def test_cargar_usuario_inexistente_da_none(tmp_path):
    eng = db.engine(tmp_path / "u2.db")
    db.ensure_schema(eng)
    assert db.cargar_usuario(eng, "no-existe@x.cl") is None
