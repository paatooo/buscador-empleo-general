# -*- coding: utf-8 -*-
"""Pruebas de integración: texto real de un aviso a través de todo el motor.

Las pruebas unitarias de cada módulo usan valores ya calculados (habilidades,
atributos) escritos a mano. Estas pruebas construyen el Aviso desde texto
real usando habilidades.detectar() y atributos.*, exactamente como lo hará
la app — es el único lugar donde se detectan bugs que solo aparecen cuando
los módulos se combinan.
"""
from motor.atributos import anios_experiencia, ingles_excluyente, modalidad, region
from motor.habilidades import detectar
from motor.puntaje import Aviso, Perfil, puntuar


def _aviso_desde_texto(titulo, texto, ubicacion="", es_remoto=None):
    cuerpo = f"{titulo} {texto}"
    return Aviso(
        titulo=titulo,
        texto=texto,
        habilidades=detectar(cuerpo),
        region=region(ubicacion),
        modalidad=modalidad(cuerpo, es_remoto=es_remoto),
        anios_pedidos=anios_experiencia(cuerpo),
        ingles_excluyente=ingles_excluyente(cuerpo),
    )


def test_guardia_de_seguridad_sin_habilidades_detectadas_puntua_alto():
    aviso = _aviso_desde_texto(
        "Guardia de seguridad",
        "Se busca guardia de seguridad turno noche, buena presencia.")
    assert aviso.habilidades == []
    perfil = Perfil(cargos_buscados=["guardia de seguridad"], habilidades=[])
    resultado = puntuar(aviso, perfil)
    assert resultado.visible is True
    assert resultado.total >= 90


def test_conductor_con_edad_minima_no_penaliza_por_seniority():
    aviso = _aviso_desde_texto(
        "Conductor de reparto",
        "Requisito: minimo 21 anos para conducir, licencia clase B.")
    assert aviso.anios_pedidos is None
    # El texto real dispara dos habilidades legítimas del catálogo
    # ("Licencia de conducir" por "licencia clase B", "Despacho" por
    # "reparto" en el título) — no un falso positivo de detección. Un
    # perfil de conductor real declararía su licencia; con eso el punto
    # de este test (que la edad mínima mal leída no gatille penalización
    # de seniority) queda aislado del bono de habilidades, que es un
    # mecanismo aparte y ya probado en test_puntaje.py.
    perfil = Perfil(cargos_buscados=["conductor de reparto"],
                    anios_experiencia=1, habilidades=["Licencia de conducir"])
    resultado = puntuar(aviso, perfil)
    assert "seniority_excesivo" not in resultado.ajustes
    assert resultado.total >= 90


def test_analista_con_habilidades_de_relleno_no_pierde_contra_cargo_peor():
    mejor_cargo = _aviso_desde_texto(
        "Analista de datos junior",
        "Se busca analista de datos junior, se valora trabajo en equipo.")
    peor_cargo = _aviso_desde_texto(
        "Analista junior", "Se busca analista junior para el area comercial.")
    perfil = Perfil(cargos_buscados=["analista de datos junior"], habilidades=[])
    r_mejor = puntuar(mejor_cargo, perfil)
    r_peor = puntuar(peor_cargo, perfil)
    assert r_mejor.total > r_peor.total
