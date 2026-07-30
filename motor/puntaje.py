# -*- coding: utf-8 -*-
"""Combinación final: cargo primero, habilidades después, ajustes al final."""
from dataclasses import dataclass, field

from motor.cargo import UMBRAL_VISIBILIDAD, afinidad
from motor.texto import normalizar, tokens

# Reemplaza _PESO_CARGO y _PESO_HABILIDADES por una sola constante de bono.
# El cargo solo llega al máximo posible menos este margen; las habilidades
# solo pueden sumar el margen restante, nunca restar del piso de cargo.
# Así un calce de cargo perfecto nunca pierde frente a uno peor, sin
# importar qué habilidades declare el perfil o liste el aviso.
_BONO_HABILIDADES = 15

_AJUSTE_INGLES = -20
_AJUSTE_REGION = -25
_AJUSTE_SENIORITY = -15

# Cuántos años por encima de la experiencia declarada se toleran antes de
# considerar que el cargo queda grande.
_HOLGURA_ANIOS = 2


@dataclass(frozen=True)
class Perfil:
    cargos_buscados: list[str]
    habilidades: list[str] = field(default_factory=list)
    anios_experiencia: int | None = None
    region: str | None = None
    acepta_remoto: bool = True
    evitar: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Aviso:
    titulo: str
    texto: str
    habilidades: list[str] = field(default_factory=list)
    region: str = "Sin especificar"
    modalidad: str = "Sin especificar"
    anios_pedidos: int | None = None
    ingles_excluyente: bool = False


@dataclass(frozen=True)
class Puntaje:
    total: int
    afinidad_cargo: float
    ajustes: dict[str, int]
    visible: bool
    motivo_oculto: str | None = None


def puntuar(aviso: Aviso, perfil: Perfil) -> Puntaje:
    afin = afinidad(perfil.cargos_buscados, aviso.titulo)

    if _esta_evitado(aviso, perfil):
        return Puntaje(0, afin, {}, visible=False, motivo_oculto="evitado")

    base = _base(afin, aviso, perfil)
    ajustes = _ajustes(aviso, perfil)
    total = max(0, min(100, round(base + sum(ajustes.values()))))
    visible = afin >= UMBRAL_VISIBILIDAD
    return Puntaje(
        total=total,
        afinidad_cargo=afin,
        ajustes=ajustes,
        visible=visible,
        motivo_oculto=None if visible else "afinidad_baja",
    )


def _base(afin: float, aviso: Aviso, perfil: Perfil) -> float:
    """El cargo solo ya alcanza casi el máximo; las habilidades solo suman."""
    base_cargo = afin * (100 - _BONO_HABILIDADES)
    del_aviso = {normalizar(h) for h in aviso.habilidades}
    if not del_aviso:
        return base_cargo + _BONO_HABILIDADES
    del_perfil = {normalizar(h) for h in perfil.habilidades}
    cubiertas = len(del_aviso & del_perfil) / len(del_aviso)
    return base_cargo + cubiertas * _BONO_HABILIDADES


def _ajustes(aviso: Aviso, perfil: Perfil) -> dict[str, int]:
    ajustes = {}
    habilidades_normalizadas = {normalizar(h) for h in perfil.habilidades}
    if aviso.ingles_excluyente and normalizar("Inglés") not in habilidades_normalizadas:
        ajustes["ingles_excluyente"] = _AJUSTE_INGLES
    if _region_incompatible(aviso, perfil):
        ajustes["otra_region"] = _AJUSTE_REGION
    if _queda_grande(aviso, perfil):
        ajustes["seniority_excesivo"] = _AJUSTE_SENIORITY
    return ajustes


def _region_incompatible(aviso: Aviso, perfil: Perfil) -> bool:
    if not perfil.region or aviso.region == "Sin especificar":
        return False
    if aviso.modalidad == "Remoto" and perfil.acepta_remoto:
        return False
    return aviso.region != perfil.region


def _queda_grande(aviso: Aviso, perfil: Perfil) -> bool:
    """Solo cuando el aviso dice explícitamente cuántos años pide."""
    if aviso.anios_pedidos is None or perfil.anios_experiencia is None:
        return False
    return aviso.anios_pedidos > perfil.anios_experiencia + _HOLGURA_ANIOS


def _esta_evitado(aviso: Aviso, perfil: Perfil) -> bool:
    if not perfil.evitar:
        return False
    del_aviso = set(tokens(f"{aviso.titulo} {aviso.texto}"))
    singulares_aviso = {_sin_plural(t) for t in del_aviso}
    for termino in perfil.evitar:
        del_termino = tokens(termino)
        if del_termino and all(
            t in del_aviso or _sin_plural(t) in singulares_aviso
            for t in del_termino
        ):
            return True
    return False


def _sin_plural(token: str) -> str:
    """Plural simple del español ('plásticos' -> 'plastico'), sin tocar
    palabras cortas donde la 's' final es parte de la palabra (p. ej. 'gas')."""
    if token.endswith("es") and len(token) > 4:
        return token[:-2]
    if token.endswith("s") and len(token) > 3:
        return token[:-1]
    return token
