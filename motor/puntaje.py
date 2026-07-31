# -*- coding: utf-8 -*-
"""Combinación final: cargo primero, habilidades después, ajustes al final."""
from dataclasses import dataclass, field

from motor.cargo import UMBRAL_VISIBILIDAD, afinidad
from motor.texto import normalizar, tokens

# Cuánto puede mover el puntaje la cobertura de habilidades. El bono se
# escala por la afinidad de cargo en _base() (no se suma plano), para que
# un calce de cargo perfecto nunca pierda frente a uno peor sin importar
# qué habilidades declare el perfil o liste el aviso.
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
    """El cargo domina y el bono de habilidades escala con la afinidad.

    El bono nunca es un monto fijo: si fuera fijo, un aviso de afinidad
    baja sin habilidades listadas podría superar a uno de afinidad alta
    con una habilidad no cubierta (bono fijo pesa más cuanto menor es la
    afinidad). Al escalar el bono con `afin`, el piso de un calce
    perfecto (afin=1.0) siempre domina sobre cualquier calce peor con el
    mismo o peor resultado de habilidades.
    """
    del_aviso = {normalizar(h) for h in aviso.habilidades}
    if not del_aviso:
        bono_fraccion = 1.0
    else:
        del_perfil = {normalizar(h) for h in perfil.habilidades}
        bono_fraccion = len(del_aviso & del_perfil) / len(del_aviso)
    return afin * (100 - _BONO_HABILIDADES * (1 - bono_fraccion))


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
    del_aviso = tokens(f"{aviso.titulo} {aviso.texto}")
    for termino in perfil.evitar:
        del_termino = tokens(termino)
        if del_termino and _contiene_secuencia(del_aviso, del_termino):
            return True
    return False


def _contiene_secuencia(tokens_aviso: list[str], tokens_termino: list[str]) -> bool:
    """True si tokens_termino aparece como subsecuencia contigua en
    tokens_aviso, permitiendo que cada palabra calce por raíz (singular
    o plural)."""
    n = len(tokens_termino)
    for i in range(len(tokens_aviso) - n + 1):
        ventana = tokens_aviso[i:i + n]
        if all(_raices_posibles(a) & _raices_posibles(t)
               for a, t in zip(ventana, tokens_termino)):
            return True
    return False


def _raices_posibles(token: str) -> set[str]:
    """Formas singulares candidatas de una palabra en español.

    En vez de decidir qué regla de pluralización aplica (ambiguo sin
    contexto morfológico), se generan las dos raíces candidatas — quitar
    una "s" (envases -> envase) o quitar "es" (gases -> gas) — y se
    acepta calce con cualquiera. Solo se recorta si la palabra termina en
    "s": sin ese resguardo, pares sin relación como "carne"/"carnet" o
    "mesa"/"meses" también calzan por quitar la última letra.
    """
    raices = {token}
    if token.endswith("s"):
        if len(token) > 3:
            raices.add(token[:-1])
        if token.endswith("es") and len(token) > 4:
            raices.add(token[:-2])
    return raices
