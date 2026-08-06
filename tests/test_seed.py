# -*- coding: utf-8 -*-
import db
import seed


def test_run_inserta_los_terminos_base(tmp_path):
    eng = db.engine(tmp_path / "s1.db")
    db.ensure_schema(eng)
    resumen = seed.run(eng, "2026-08-05T00:00:00")
    assert resumen["agregados"] == len(seed.TERMINOS_BASE)
    filas = db.consultar(eng, "SELECT termino, origen FROM terminos_busqueda")
    assert {t for t, _ in filas} == set(seed.TERMINOS_BASE)
    assert {o for _, o in filas} == {"base"}


def test_run_dos_veces_no_duplica_ni_repisa(tmp_path):
    eng = db.engine(tmp_path / "s2.db")
    db.ensure_schema(eng)
    seed.run(eng, "2026-08-05T00:00:00")
    resumen = seed.run(eng, "2026-09-01T00:00:00")
    assert resumen["agregados"] == 0
    assert resumen["ya_estaban"] == len(seed.TERMINOS_BASE)
    fechas = {f[0] for f in db.consultar(
        eng, "SELECT agregado_en FROM terminos_busqueda")}
    assert fechas == {"2026-08-05T00:00:00"}


def test_run_no_le_roba_el_origen_a_un_termino_de_usuario(tmp_path):
    """Un término que alguien ya pidió tiene prioridad sobre los base en
    `db.terminos_pendientes` — el seed no puede degradarlo a "base"."""
    eng = db.engine(tmp_path / "s3.db")
    db.ensure_schema(eng)
    de_usuario = seed.TERMINOS_BASE[0]
    db.agregar_termino(eng, de_usuario, "usuario", "2026-08-01T00:00:00")
    seed.run(eng, "2026-08-05T00:00:00")
    origen = db.consultar(
        eng, "SELECT origen FROM terminos_busqueda WHERE termino = :t",
        {"t": de_usuario})[0][0]
    assert origen == "usuario"


def test_terminos_base_no_tiene_repetidos_ni_espacios_de_sobra():
    assert len(seed.TERMINOS_BASE) == len(set(seed.TERMINOS_BASE))
    assert all(t == t.strip().lower() and t for t in seed.TERMINOS_BASE)


def test_los_terminos_base_quedan_pendientes_para_la_proxima_corrida(tmp_path):
    eng = db.engine(tmp_path / "s4.db")
    db.ensure_schema(eng)
    seed.run(eng, "2026-08-05T00:00:00")
    assert set(db.terminos_pendientes(eng)) == set(seed.TERMINOS_BASE)
