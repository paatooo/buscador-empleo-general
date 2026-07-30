# -*- coding: utf-8 -*-
"""Combinación final: cargo primero, habilidades después, ajustes al final."""
from dataclasses import dataclass, field

from motor.cargo import UMBRAL_VISIBILIDAD, afinidad
from motor.texto import normalizar

# El cargo pesa más que las habilidades. Cuando el aviso no menciona ninguna
# habilidad, el cargo se lleva los 100 puntos: así un aviso de oficio no
# queda estructuralmente por debajo de uno corporativo que sí las lista.
_PESO_CARGO = 70
_PESO_HABILIDADES = 30

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
    """Cargo solo si el aviso no lista habilidades; cargo + habilidades si sí."""
    if not aviso.habilidades:
        return afin * (_PESO_CARGO + _PESO_HABILIDADES)
    mias = set(perfil.habilidades) & set(aviso.habilidades)
    cubiertas = len(mias) / len(aviso.habilidades)
    return afin * _PESO_CARGO + cubiertas * _PESO_HABILIDADES


def _ajustes(aviso: Aviso, perfil: Perfil) -> dict[str, int]:
    ajustes = {}
    if aviso.ingles_excluyente and "Inglés" not in perfil.habilidades:
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
    texto = normalizar(f"{aviso.titulo} {aviso.texto}")
    return any(normalizar(t) in texto for t in perfil.evitar if str(t).strip())
