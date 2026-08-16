# -*- coding: utf-8 -*-
"""El esquema debe crearse igual en SQLite (local) y en Postgres (nube).
Se prueba contra SQLite temporal; el SQL usado es portable."""
from sqlalchemy import inspect

import conexion
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


def test_upsert_marca_crea_y_actualiza(tmp_path):
    eng = db.engine(tmp_path / "m.db")
    db.ensure_schema(eng)
    db.upsert_marca(eng, "ana@x.cl", "http://x/1", "favorita", True,
                    "2026-07-30")
    marcas = db.cargar_marcas(eng, "ana@x.cl")
    assert marcas["http://x/1"]["favorita"] == 1

    db.upsert_marca(eng, "ana@x.cl", "http://x/1", "postulada", True,
                    "2026-07-30")
    marcas = db.cargar_marcas(eng, "ana@x.cl")
    assert marcas["http://x/1"]["favorita"] == 1    # no pisa la marca anterior
    assert marcas["http://x/1"]["postulada"] == 1

    db.upsert_marca(eng, "ana@x.cl", "http://x/1", "favorita", False,
                    "2026-07-31")
    marcas = db.cargar_marcas(eng, "ana@x.cl")
    assert marcas["http://x/1"]["favorita"] == 0
    assert db.escalar(eng, "SELECT COUNT(*) FROM marcas") == 1  # sin duplicar


def test_upsert_marca_rechaza_campo_invalido(tmp_path):
    eng = db.engine(tmp_path / "m2.db")
    db.ensure_schema(eng)
    try:
        db.upsert_marca(eng, "ana@x.cl", "http://x/1",
                        "borrar; DROP TABLE marcas", True, "x")
        assert False, "debió rechazar el campo"
    except ValueError:
        pass


def test_marcas_de_un_usuario_no_se_filtran_a_otro(tmp_path):
    # Requisito explícito del spec: privacidad entre usuarios.
    eng = db.engine(tmp_path / "m3.db")
    db.ensure_schema(eng)
    db.upsert_marca(eng, "ana@x.cl", "http://x/1", "favorita", True,
                    "2026-07-30")
    db.upsert_marca(eng, "beto@x.cl", "http://x/2", "postulada", True,
                    "2026-07-30")

    marcas_ana = db.cargar_marcas(eng, "ana@x.cl")
    marcas_beto = db.cargar_marcas(eng, "beto@x.cl")

    assert list(marcas_ana) == ["http://x/1"]
    assert list(marcas_beto) == ["http://x/2"]


def test_dos_usuarios_pueden_marcar_la_misma_oferta_distinto(tmp_path):
    eng = db.engine(tmp_path / "m4.db")
    db.ensure_schema(eng)
    db.upsert_marca(eng, "ana@x.cl", "http://x/1", "favorita", True,
                    "2026-07-30")
    db.upsert_marca(eng, "beto@x.cl", "http://x/1", "favorita", False,
                    "2026-07-30")

    assert db.cargar_marcas(eng, "ana@x.cl")["http://x/1"]["favorita"] == 1
    assert db.cargar_marcas(eng, "beto@x.cl")["http://x/1"]["favorita"] == 0


def test_agregar_termino_no_duplica(tmp_path):
    eng = db.engine(tmp_path / "t.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "cajero", "base", "2026-07-30T00:00:00")
    db.agregar_termino(eng, "cajero", "usuario", "2026-08-01T00:00:00")
    assert db.escalar(eng, "SELECT COUNT(*) FROM terminos_busqueda") == 1
    assert db.escalar(
        eng, "SELECT origen FROM terminos_busqueda WHERE termino = 'cajero'"
    ) == "base"  # el segundo agregar_termino no pisa el origen original


def test_registrar_corrida_actualiza_termino_existente(tmp_path):
    eng = db.engine(tmp_path / "t2.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "cajero", "base", "2026-07-30T00:00:00")
    db.registrar_corrida_termino(eng, "cajero", 12, "2026-08-01T10:00:00")
    fila = db.consultar(
        eng, "SELECT ultima_corrida, ofertas_ultimas FROM terminos_busqueda"
             " WHERE termino = 'cajero'")[0]
    assert tuple(fila) == ("2026-08-01T10:00:00", 12)


def test_terminos_pendientes_prioriza_usuario_nunca_corrido(tmp_path):
    eng = db.engine(tmp_path / "t3.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "cajero", "base", "2026-07-01T00:00:00")
    db.agregar_termino(eng, "soldador", "usuario", "2026-08-01T00:00:00")
    pendientes = db.terminos_pendientes(eng)
    assert pendientes[0] == "soldador"


def test_terminos_pendientes_excluye_corridos_hace_poco(tmp_path):
    eng = db.engine(tmp_path / "t4.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "cajero", "base", "2026-07-01T00:00:00")
    db.registrar_corrida_termino(eng, "cajero", 5, "2026-08-01T09:00:00")
    # "ahora" es 2 horas después de la corrida: no debe reaparecer
    pendientes = db.terminos_pendientes(eng, ahora="2026-08-01T11:00:00")
    assert "cajero" not in pendientes


def test_terminos_pendientes_reaparece_pasadas_24_horas(tmp_path):
    eng = db.engine(tmp_path / "t5.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "cajero", "base", "2026-07-01T00:00:00")
    db.registrar_corrida_termino(eng, "cajero", 5, "2026-08-01T09:00:00")
    pendientes = db.terminos_pendientes(eng, ahora="2026-08-02T10:00:00")
    assert "cajero" in pendientes


def test_terminos_pendientes_respeta_el_limite(tmp_path):
    eng = db.engine(tmp_path / "t6.db")
    db.ensure_schema(eng)
    for i in range(5):
        db.agregar_termino(eng, f"termino{i}", "base", "2026-07-01T00:00:00")
    assert len(db.terminos_pendientes(eng, limite=2)) == 2


def test_terminos_pendientes_despriorizar_esteriles(tmp_path):
    # Requisito del spec: "se despriorizan los términos que llevan
    # corridas sin devolver nada" — un término sin resultados la última
    # vez debe quedar después de uno con resultados, aunque su corrida
    # anterior sea más antigua.
    eng = db.engine(tmp_path / "t7.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "con_resultados", "base", "2026-07-01T00:00:00")
    db.registrar_corrida_termino(eng, "con_resultados", 10,
                                 "2026-07-25T00:00:00")  # corrida reciente
    db.agregar_termino(eng, "esteril", "base", "2026-07-01T00:00:00")
    db.registrar_corrida_termino(eng, "esteril", 0,
                                 "2026-07-01T00:00:00")  # corrida antigua

    pendientes = db.terminos_pendientes(eng, ahora="2026-08-05T00:00:00")
    assert pendientes.index("con_resultados") < pendientes.index("esteril")


def test_termino_reciente_da_false_si_nunca_se_corrio(tmp_path):
    eng = db.engine(tmp_path / "tr1.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "cajero", "base", "2026-07-01T00:00:00")
    assert db.termino_reciente(eng, "cajero", "2026-08-01T00:00:00") is False


def test_termino_reciente_da_true_dentro_de_24_horas(tmp_path):
    eng = db.engine(tmp_path / "tr2.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "cajero", "base", "2026-07-01T00:00:00")
    db.registrar_corrida_termino(eng, "cajero", 5, "2026-08-01T09:00:00")
    assert db.termino_reciente(eng, "cajero", "2026-08-01T11:00:00") is True


def test_termino_reciente_da_false_pasadas_24_horas(tmp_path):
    eng = db.engine(tmp_path / "tr3.db")
    db.ensure_schema(eng)
    db.agregar_termino(eng, "cajero", "base", "2026-07-01T00:00:00")
    db.registrar_corrida_termino(eng, "cajero", 5, "2026-08-01T09:00:00")
    assert db.termino_reciente(eng, "cajero", "2026-08-02T10:00:00") is False


def test_termino_reciente_da_false_si_el_termino_no_existe(tmp_path):
    eng = db.engine(tmp_path / "tr4.db")
    db.ensure_schema(eng)
    assert db.termino_reciente(eng, "inexistente", "2026-08-01T00:00:00") is False


def test_upsert_ofertas_ignora_duplicados(tmp_path):
    eng = db.engine(tmp_path / "o.db")
    db.ensure_schema(eng)  # ensure_schema ya crea la tabla `ofertas`
    filas = [{"job_url": "http://x/1", "title": "Cajero", "company": "A",
              "site": "trabajando", "scrape_date": "2026-07-30"}]
    insertadas = db.upsert_ofertas(eng, filas, list(filas[0]))
    assert insertadas == 1
    insertadas_de_nuevo = db.upsert_ofertas(eng, filas, list(filas[0]))
    assert insertadas_de_nuevo == 0
    assert db.escalar(eng, "SELECT COUNT(*) FROM ofertas") == 1


def test_upsert_oferta_analisis_no_guarda_columnas_prohibidas(tmp_path):
    # No debe existir forma de guardar match/cargo_no_afin/electrico/detalle
    # — son dependientes de perfil, y esta tabla es genérica.
    eng = db.engine(tmp_path / "o2.db")
    db.ensure_schema(eng)
    columnas = {c["name"] for c in
                __import__("sqlalchemy").inspect(eng).get_columns("oferta_analisis")}
    prohibidas = {"match", "cargo_no_afin", "electrico", "detalle"}
    assert columnas.isdisjoint(prohibidas)


def test_upsert_oferta_analisis_reemplaza_atomico(tmp_path):
    eng = db.engine(tmp_path / "o3.db")
    db.ensure_schema(eng)
    filas = [{"job_url": "http://x/1", "habilidades": '["Excel"]',
              "areas": '["administracion"]', "region": "Metropolitana",
              "modalidad": "Presencial", "tipo_contrato": "Indefinido",
              "anios_experiencia_pedidos": 2, "ingles_excluyente": 0,
              "duplicada": 0, "vigencia_estimada": "2026-08-30",
              "analizado_en": "2026-07-30T10:00:00"}]
    db.upsert_oferta_analisis(eng, filas)
    fila = db.consultar(eng, "SELECT habilidades, region FROM oferta_analisis"
                             " WHERE job_url = 'http://x/1'")[0]
    assert tuple(fila) == ('["Excel"]', "Metropolitana")

    filas[0]["region"] = "Valparaíso"
    db.upsert_oferta_analisis(eng, filas)
    assert db.escalar(
        eng, "SELECT region FROM oferta_analisis WHERE job_url = 'http://x/1'"
    ) == "Valparaíso"
    assert db.escalar(eng, "SELECT COUNT(*) FROM oferta_analisis") == 1


def test_cargar_ofertas_hace_join_con_analisis(tmp_path):
    eng = db.engine(tmp_path / "o4.db")
    db.ensure_schema(eng)
    db.ejecutar(eng, "INSERT INTO ofertas (job_url, title, company, site,"
                     " scrape_date, description) VALUES ('http://x/1',"
                     " 'Cajero', 'A', 'trabajando', '2026-07-30',"
                     " 'Se busca cajero con experiencia')")
    db.upsert_oferta_analisis(eng, [{
        "job_url": "http://x/1", "habilidades": '[]', "areas": '[]',
        "region": "Metropolitana", "modalidad": "Presencial",
        "tipo_contrato": "Indefinido", "anios_experiencia_pedidos": None,
        "ingles_excluyente": 0, "duplicada": 0, "vigencia_estimada": None,
        "analizado_en": "2026-07-30T10:00:00"}])
    ofertas = db.cargar_ofertas(eng)
    assert len(ofertas) == 1
    assert ofertas[0]["job_url"] == "http://x/1"
    assert ofertas[0]["title"] == "Cajero"
    assert ofertas[0]["region"] == "Metropolitana"
    assert ofertas[0]["description"] == "Se busca cajero con experiencia"


def test_cargar_ofertas_sin_filas_da_lista_vacia(tmp_path):
    eng = db.engine(tmp_path / "o5.db")
    db.ensure_schema(eng)
    assert db.cargar_ofertas(eng) == []


def test_upsert_ofertas_rechaza_columna_invalida(tmp_path):
    eng = db.engine(tmp_path / "o6.db")
    db.ensure_schema(eng)
    try:
        db.upsert_ofertas(eng, [{"job_url": "x", "borrar; DROP TABLE ofertas": "y"}],
                          ["job_url", "borrar; DROP TABLE ofertas"])
        assert False, "debió rechazar la columna inválida"
    except ValueError:
        pass


def test_engine_nube_usa_el_dialecto_psycopg(monkeypatch):
    url = "postgresql://u:pass@host:5432/db_dialecto_test"
    monkeypatch.setenv("POSTGRES_URL", url)
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    # La clave de caché es ("nube", url_ya_normalizada); usamos una URL
    # exclusiva de este test para no pisar/reusar un Engine creado por otra
    # prueba en este mismo proceso.
    clave = ("nube", conexion.url_postgres())
    db._ENGINES.pop(clave, None)
    eng = db.engine()
    assert db.es_nube(eng) is True
    assert eng.url.drivername == "postgresql+psycopg"
