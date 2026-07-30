# -*- coding: utf-8 -*-
"""Afinidad entre los cargos que busca una persona y el título de un aviso.

Es la señal dominante del motor: reemplaza la noción de "cargo afín"
codificada a un perfil concreto por una comparación que sale del perfil de
cada usuario.
"""
from difflib import SequenceMatcher

from motor.texto import tokens

# Bajo esta afinidad el aviso no se muestra: es ruido, no un match malo.
# Equivale a "al menos la mitad de las palabras significativas del cargo
# buscado aparecen en el título".
# PROVISIONAL: calibrar contra datos reales apenas haya usuarios.
UMBRAL_VISIBILIDAD = 0.5

# Dos palabras se consideran la misma por encima de esta similitud. Cubre
# plurales y género ("cajero"/"cajeros"/"cajera") sin emparejar palabras
# distintas que comparten letras. No subirlo a 0.85: ahí "cajero" y
# "cajera" quedan en 0.833 y dejan de calzar, que es justo lo que no
# queremos. "cajero" contra "ingeniero" da 0.4, muy lejos del umbral.
_UMBRAL_TOKEN = 0.80


def afinidad(cargos_buscados: list[str], titulo: str) -> float:
    """0.0 a 1.0. Se queda con el mejor de los cargos buscados."""
    del_titulo = tokens(titulo)
    if not cargos_buscados or not del_titulo:
        return 0.0
    return max(_afinidad_de_uno(tokens(c), del_titulo) for c in cargos_buscados)


def _afinidad_de_uno(del_cargo: list[str], del_titulo: list[str]) -> float:
    """Fracción de las palabras del cargo que aparecen en el título."""
    if not del_cargo:
        return 0.0
    encontradas = sum(_mejor_coincidencia(p, del_titulo) for p in del_cargo)
    return encontradas / len(del_cargo)


def _mejor_coincidencia(palabra: str, candidatas: list[str]) -> float:
    """1.0 si calza exacto; si no, la mejor similitud que supere el umbral."""
    mejor = 0.0
    for c in candidatas:
        if c == palabra:
            return 1.0
        similitud = SequenceMatcher(None, palabra, c).ratio()
        mejor = max(mejor, similitud)
    return mejor if mejor >= _UMBRAL_TOKEN else 0.0
