# -*- coding: utf-8 -*-
"""Normalización de texto. Base de toda comparación del motor."""
import re
import unicodedata

# Palabras sin carga semántica para comparar cargos: aparecen en casi
# cualquier título y sumarían ruido a la afinidad.
VACIAS = {
    "de", "del", "la", "el", "los", "las", "y", "o", "en", "para", "con",
    "a", "un", "una", "por", "al", "e", "u",
}


def normalizar(s) -> str:
    """Minúsculas, sin tildes, espacios colapsados. None → cadena vacía."""
    texto = unicodedata.normalize("NFKD", str(s or "").lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).strip()


def tokens(s) -> list[str]:
    """Palabras significativas: sin vacías y sin letras sueltas."""
    crudos = re.findall(r"[a-z0-9]+", normalizar(s))
    return [t for t in crudos if t not in VACIAS and len(t) > 1]
