# -*- coding: utf-8 -*-
import app_data
import db
from motor.puntaje import Aviso, Perfil


def _oferta(**cambios):
    base = dict(job_url="http://x/1", title="Cajero", company="Super X",
                site="trabajando", scrape_date="2026-08-01",
                description="Se busca cajero con experiencia",
                habilidades="[]", areas='["Ventas y retail"]',
                region="Metropolitana", modalidad="Presencial",
                tipo_contrato="Indefinido", anios_experiencia_pedidos=None,
                ingles_excluyente=0, duplicada=0, vigencia_estimada=None)
    base.update(cambios)
    return base


def test_cargar_perfil_inexistente_da_none(tmp_path):
    eng = db.engine(tmp_path / "a.db")
    db.ensure_schema(eng)
    assert app_data.cargar_perfil("ana@x.cl", db_path=tmp_path / "a.db") is None


def test_guardar_y_cargar_perfil_hace_roundtrip(tmp_path):
    perfil = Perfil(cargos_buscados=["cajero"], habilidades=["Excel"],
                    anios_experiencia=2, region="Metropolitana",
                    acepta_remoto=False, evitar=["plástico"])
    app_data.guardar_perfil("ana@x.cl", perfil, "2026-08-03",
                            db_path=tmp_path / "b.db")
    cargado = app_data.cargar_perfil("ana@x.cl", db_path=tmp_path / "b.db")
    assert cargado == perfil


def test_guardar_perfil_no_pisa_creado_en_al_actualizar(tmp_path):
    p1 = Perfil(cargos_buscados=["cajero"])
    app_data.guardar_perfil("ana@x.cl", p1, "2026-08-01", db_path=tmp_path / "c.db")
    p2 = Perfil(cargos_buscados=["guardia"])
    app_data.guardar_perfil("ana@x.cl", p2, "2026-08-05", db_path=tmp_path / "c.db")
    eng = db.engine(tmp_path / "c.db")
    fila = db.cargar_usuario(eng, "ana@x.cl")
    assert fila["creado_en"] == "2026-08-01"
    assert app_data.cargar_perfil("ana@x.cl", db_path=tmp_path / "c.db") == p2


def test_aviso_desde_oferta_mapea_los_campos():
    oferta = _oferta(habilidades='["Excel", "Manejo de caja"]',
                     anios_experiencia_pedidos=2, ingles_excluyente=1)
    aviso = app_data.aviso_desde_oferta(oferta)
    assert aviso.titulo == "Cajero"
    assert aviso.texto == "Se busca cajero con experiencia"
    assert aviso.habilidades == ["Excel", "Manejo de caja"]
    assert aviso.region == "Metropolitana"
    assert aviso.modalidad == "Presencial"
    assert aviso.anios_pedidos == 2
    assert aviso.ingles_excluyente is True


def test_aviso_desde_oferta_sin_habilidades_no_crashea():
    oferta = _oferta(habilidades=None)
    aviso = app_data.aviso_desde_oferta(oferta)
    assert aviso.habilidades == []


def test_puntuar_ofertas_agrega_match_y_ordena():
    ofertas = [
        _oferta(job_url="http://x/1", title="Cajero"),  # calce perfecto
        _oferta(job_url="http://x/2", title="Ingeniero de Procesos"),  # sin relación
    ]
    perfil = Perfil(cargos_buscados=["cajero"])
    resultado = app_data.puntuar_ofertas(ofertas, perfil)
    assert len(resultado) == 1  # el sin relación queda oculto (afinidad baja)
    assert resultado[0]["job_url"] == "http://x/1"
    assert resultado[0]["match"] == 100


def test_puntuar_ofertas_respeta_evitar_del_perfil():
    ofertas = [_oferta(job_url="http://x/1", title="Cajero",
                       description="Fábrica de envases plásticos")]
    perfil = Perfil(cargos_buscados=["cajero"], evitar=["plástico"])
    assert app_data.puntuar_ofertas(ofertas, perfil) == []


def test_puntuar_ofertas_de_un_usuario_no_afecta_a_otro():
    ofertas = [_oferta(job_url="http://x/1", title="Cajero",
                       description="Fábrica de envases plásticos")]
    con_evitar = app_data.puntuar_ofertas(
        ofertas, Perfil(cargos_buscados=["cajero"], evitar=["plástico"]))
    sin_evitar = app_data.puntuar_ofertas(
        ofertas, Perfil(cargos_buscados=["cajero"]))
    assert con_evitar == []
    assert len(sin_evitar) == 1


def test_set_marca_y_marcas_de_hacen_roundtrip(tmp_path):
    app_data.set_marca("ana@x.cl", "http://x/1", "favorita", True,
                       "2026-08-03", db_path=tmp_path / "m.db")
    marcas = app_data.marcas_de("ana@x.cl", db_path=tmp_path / "m.db")
    assert marcas["http://x/1"]["favorita"] == 1


def test_marcas_de_un_usuario_no_incluye_las_de_otro(tmp_path):
    app_data.set_marca("ana@x.cl", "http://x/1", "favorita", True,
                       "2026-08-03", db_path=tmp_path / "m2.db")
    app_data.set_marca("beto@x.cl", "http://x/2", "postulada", True,
                       "2026-08-03", db_path=tmp_path / "m2.db")
    assert list(app_data.marcas_de("ana@x.cl", db_path=tmp_path / "m2.db")) == ["http://x/1"]


def test_set_marca_rechaza_campo_invalido(tmp_path):
    try:
        app_data.set_marca("ana@x.cl", "http://x/1", "campo_invalido", True,
                           "2026-08-03", db_path=tmp_path / "m3.db")
        assert False, "debió rechazar el campo"
    except ValueError:
        pass


def test_es_seleccion_nueva_la_primera_vez():
    estado = {}
    assert app_data.es_seleccion_nueva(estado, "tabla1", "http://x/1") is True


def test_es_seleccion_nueva_no_se_repite_para_la_misma_url():
    estado = {}
    app_data.es_seleccion_nueva(estado, "tabla1", "http://x/1")
    assert app_data.es_seleccion_nueva(estado, "tabla1", "http://x/1") is False


def test_es_seleccion_nueva_vuelve_a_ser_true_con_otra_url():
    estado = {}
    app_data.es_seleccion_nueva(estado, "tabla1", "http://x/1")
    assert app_data.es_seleccion_nueva(estado, "tabla1", "http://x/2") is True


def test_es_seleccion_nueva_no_cruza_entre_tablas_distintas():
    estado = {}
    app_data.es_seleccion_nueva(estado, "tabla1", "http://x/1")
    # la misma url, pero en OTRA tabla (key distinta): sigue siendo nueva
    assert app_data.es_seleccion_nueva(estado, "tabla2", "http://x/1") is True


def test_a_dataframe_decodifica_habilidades_y_areas():
    ofertas = [_oferta(habilidades='["Excel"]', areas='["Ventas y retail"]')]
    df = app_data.a_dataframe(ofertas)
    assert df.iloc[0]["habilidades"] == ["Excel"]
    assert df.iloc[0]["areas"] == ["Ventas y retail"]


def test_a_dataframe_con_lista_vacia_da_dataframe_vacio():
    df = app_data.a_dataframe([])
    assert len(df) == 0


def test_conteo_areas_cuenta_por_area():
    ofertas = [
        _oferta(job_url="http://x/1", areas='["Ventas y retail"]'),
        _oferta(job_url="http://x/2", areas='["Ventas y retail", "Administración"]'),
    ]
    conteo = app_data.conteo_areas(app_data.a_dataframe(ofertas))
    assert conteo["Ventas y retail"] == 2
    assert conteo["Administración"] == 1


def test_conteo_habilidades_calcula_porcentaje():
    ofertas = [
        _oferta(job_url="http://x/1", habilidades='["Excel"]'),
        _oferta(job_url="http://x/2", habilidades='[]'),
    ]
    tabla = app_data.conteo_habilidades(app_data.a_dataframe(ofertas))
    fila = tabla[tabla["habilidad"] == "Excel"].iloc[0]
    assert fila["ofertas"] == 1
    assert fila["pct"] == 50.0


def test_conteo_habilidades_sin_ninguna_da_tabla_vacia():
    ofertas = [_oferta(job_url="http://x/1", habilidades="[]")]
    tabla = app_data.conteo_habilidades(app_data.a_dataframe(ofertas))
    assert len(tabla) == 0
    assert list(tabla.columns) == ["habilidad", "ofertas", "pct"]


def test_tendencias_por_fecha_none_con_una_sola_fecha():
    ofertas = [_oferta(job_url="http://x/1", scrape_date="2026-08-01")]
    assert app_data.tendencias_por_fecha(app_data.a_dataframe(ofertas)) is None


def test_tendencias_por_fecha_con_varias_fechas():
    ofertas = [
        _oferta(job_url="http://x/1", scrape_date="2026-08-01",
               habilidades='["Excel"]'),
        _oferta(job_url="http://x/2", scrape_date="2026-08-02",
               habilidades='["Excel"]'),
    ]
    resultado = app_data.tendencias_por_fecha(app_data.a_dataframe(ofertas))
    assert resultado is not None
    assert set(resultado["habilidades"]["scrape_date"]) == {"2026-08-01", "2026-08-02"}


def test_radar_empresas_agrupa_por_empresa():
    ofertas = [
        _oferta(job_url="http://x/1", company="Super X",
               habilidades='["Excel"]', areas='["Ventas y retail"]'),
        _oferta(job_url="http://x/2", company="Super X",
               habilidades='["Manejo de caja"]', areas='["Ventas y retail"]'),
    ]
    tabla = app_data.radar_empresas(app_data.a_dataframe(ofertas))
    fila = tabla[tabla["empresa"] == "Super X"].iloc[0]
    assert fila["ofertas"] == 2
    assert "Excel" in fila["top_habilidades"]
