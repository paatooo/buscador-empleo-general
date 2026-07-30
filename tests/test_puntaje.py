import pytest

from motor.puntaje import Aviso, Perfil, puntuar


def aviso(**cambios):
    base = dict(titulo="Cajero/a supermercado", texto="Se busca cajero",
                habilidades=[], region="Metropolitana", modalidad="Presencial",
                anios_pedidos=None, ingles_excluyente=False)
    base.update(cambios)
    return Aviso(**base)


def perfil(**cambios):
    base = dict(cargos_buscados=["cajero"], habilidades=[],
                anios_experiencia=None, region=None, acepta_remoto=True,
                evitar=[])
    base.update(cambios)
    return Perfil(**base)


def test_aviso_sin_habilidades_igual_puntua_alto():
    # EL requisito central: los oficios no listan habilidades y aun así
    # deben rankear. Con el motor anterior esto daba puntaje nulo.
    resultado = puntuar(aviso(), perfil())
    assert resultado.total >= 90
    assert resultado.visible is True


def test_cargo_sin_relacion_queda_oculto():
    resultado = puntuar(aviso(titulo="Ingeniero de Procesos"), perfil())
    assert resultado.visible is False
    assert resultado.motivo_oculto == "afinidad_baja"


def test_habilidades_que_tengo_suben_el_puntaje():
    con = puntuar(aviso(habilidades=["Excel", "Manejo de caja"]),
                  perfil(habilidades=["Excel", "Manejo de caja"]))
    sin = puntuar(aviso(habilidades=["Excel", "Manejo de caja"]),
                  perfil(habilidades=[]))
    assert con.total > sin.total


def test_ingles_excluyente_penaliza_si_no_lo_tengo():
    resultado = puntuar(aviso(ingles_excluyente=True), perfil())
    assert resultado.ajustes["ingles_excluyente"] < 0


def test_ingles_excluyente_no_penaliza_si_lo_tengo():
    resultado = puntuar(aviso(ingles_excluyente=True),
                        perfil(habilidades=["Inglés"]))
    assert "ingles_excluyente" not in resultado.ajustes


def test_otra_region_penaliza():
    resultado = puntuar(aviso(region="Antofagasta"),
                        perfil(region="Metropolitana"))
    assert resultado.ajustes["otra_region"] < 0


def test_remoto_no_penaliza_por_region():
    resultado = puntuar(aviso(region="Antofagasta", modalidad="Remoto"),
                        perfil(region="Metropolitana", acepta_remoto=True))
    assert "otra_region" not in resultado.ajustes


def test_piden_mucha_mas_experiencia_penaliza():
    resultado = puntuar(aviso(anios_pedidos=8), perfil(anios_experiencia=1))
    assert resultado.ajustes["seniority_excesivo"] < 0


def test_experiencia_no_mencionada_nunca_penaliza():
    resultado = puntuar(aviso(anios_pedidos=None), perfil(anios_experiencia=1))
    assert "seniority_excesivo" not in resultado.ajustes


def test_lista_evitar_oculta_el_aviso():
    resultado = puntuar(aviso(texto="Fábrica de envases plásticos"),
                        perfil(evitar=["plástico"]))
    assert resultado.visible is False
    assert resultado.motivo_oculto == "evitado"


def test_evitar_de_una_persona_no_afecta_a_otra():
    con_filtro = puntuar(aviso(texto="Fábrica de envases plásticos"),
                         perfil(evitar=["plástico"]))
    sin_filtro = puntuar(aviso(texto="Fábrica de envases plásticos"), perfil())
    assert con_filtro.visible is False
    assert sin_filtro.visible is True


def test_el_puntaje_nunca_sale_del_rango():
    resultado = puntuar(
        aviso(ingles_excluyente=True, region="Antofagasta", anios_pedidos=15),
        perfil(region="Metropolitana", anios_experiencia=0, acepta_remoto=False))
    assert 0 <= resultado.total <= 100


@pytest.mark.parametrize("titulo", ["Cajero", "CAJERA", "Cajero/a part time"])
def test_variantes_del_mismo_cargo_son_visibles(titulo):
    assert puntuar(aviso(titulo=titulo), perfil()).visible is True
