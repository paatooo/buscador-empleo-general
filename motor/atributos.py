# -*- coding: utf-8 -*-
"""Atributos que se leen del aviso y no dependen de ningún perfil.

Todo lo de acá se puede precalcular y guardar una sola vez por oferta,
compartido entre todos los usuarios.
"""
import re

from motor.texto import normalizar

_REGIONES = {
    "Arica y Parinacota": r"arica|parinacota",
    "Tarapacá": r"iquique|tarapaca|alto hospicio",
    "Antofagasta": r"antofagasta|calama|tocopilla|mejillones",
    "Atacama": r"copiapo|atacama|vallenar|caldera",
    "Coquimbo": r"la serena|coquimbo|ovalle|illapel",
    "Valparaíso": r"valparaiso|vina del mar|quilpue|concon|quillota"
                  r"|san antonio|los andes|villa alemana|quintero",
    "Metropolitana": r"santiago|metropolitana|quilicura|maipu|las condes"
                     r"|providencia|pudahuel|colina|san bernardo|puente alto"
                     r"|renca|huechuraba|nunoa|vitacura|cerrillos|la florida"
                     r"|macul|penalolen|lo barnechea|recoleta|conchali"
                     r"|estacion central|quinta normal|melipilla|talagante"
                     r"|buin|la reina|san miguel|independencia",
    "O'Higgins": r"rancagua|o'?higgins|machali|rengo|san fernando",
    "Maule": r"\btalca\b|maule|curico|linares|constitucion",
    "Ñuble": r"chillan|nuble",
    "Biobío": r"concepcion|biobio|bio bio|talcahuano|coronel|hualpen"
              r"|los angeles|san pedro de la paz|penco",
    "La Araucanía": r"temuco|araucania|angol|villarrica",
    "Los Ríos": r"valdivia|los rios|la union",
    "Los Lagos": r"puerto montt|osorno|los lagos|castro|puerto varas",
    "Aysén": r"coyhaique|aysen",
    "Magallanes": r"punta arenas|magallanes|puerto natales",
}

_EXIGENCIA = r"excluyente|indispensable|requisito|obligatorio|fluido|avanzado"
_SUAVIZA = (r"deseable|idealmente|plus\b|valorable"
            r"|no (?:es )?(?:excluyente|obligatorio|indispensable|requisito|requerido|necesario)")

_NUM_PALABRA = {
    "un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4,
    "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
}
_NUM = r"(\d{1,2}|" + "|".join(_NUM_PALABRA) + r")"


def region(ubicacion) -> str:
    """Región de Chile a partir de un campo de ubicación (ciudad/comuna).

    Espera un campo de ubicación acotado, no el cuerpo completo del aviso:
    algunos nombres de comuna (p. ej. "Independencia", "Coronel") coinciden
    con palabras comunes del español y producirían falsos positivos si se
    buscaran sobre texto libre.
    """
    texto = normalizar(ubicacion)
    for nombre, patron in _REGIONES.items():
        if re.search(patron, texto):
            return nombre
    return "Sin especificar"


def modalidad(texto, es_remoto=None) -> str:
    if es_remoto:
        return "Remoto"
    normalizado = normalizar(texto)
    if re.search(r"hibrid", normalizado):
        return "Híbrido"
    if re.search(r"remoto|teletrabajo|home ?office", normalizado):
        return "Remoto"
    if re.search(r"presencial", normalizado):
        return "Presencial"
    return "Sin especificar"


def tipo_contrato(texto) -> str:
    normalizado = normalizar(texto)
    if re.search(r"part[ -]?time|media jornada|jornada parcial", normalizado):
        return "Part-time"
    if re.search(r"indefinido", normalizado):
        return "Indefinido"
    if re.search(r"plazo fijo|reemplazo|temporal", normalizado):
        return "Plazo fijo"
    if re.search(r"honorarios|boleta de honorarios", normalizado):
        return "Honorarios"
    return "No especificado"


def anios_experiencia(texto) -> int | None:
    """Años pedidos, o None si el aviso no los menciona.

    Ante un rango se toma el menor: es el mínimo real para postular.
    Nunca inventa un valor — la omisión no debe penalizar a nadie.
    """
    normalizado = normalizar(texto)
    # No hace falta un patrón anclado a "mínimo"/"al menos": ese texto
    # siempre viene acompañado en algún punto de "N años de experiencia",
    # y el patrón general de abajo ya lo cubre sin exigir la palabra
    # "mínimo" explícitamente. Un patrón anclado a esas palabras sería
    # estrictamente más específico (nunca calzaría un caso que el
    # general no calce ya) y por eso quedaría muerto en la lista.
    patrones = [
        rf"de {_NUM} a {_NUM} anos de experiencia",
        rf"entre {_NUM} y {_NUM} anos de experiencia",
        rf"{_NUM}\+? anos? de experiencia",
        rf"experiencia (?:minima )?de {_NUM} anos?",
    ]
    for patron in patrones:
        encontrado = re.search(patron, normalizado)
        if encontrado:
            return _a_numero(encontrado.group(1))
    return None


def _a_numero(s: str) -> int:
    return int(s) if s.isdigit() else _NUM_PALABRA[s]


def ingles_excluyente(texto) -> bool:
    """True solo si se exige inglés. "Deseable" no cuenta como exigencia."""
    normalizado = normalizar(texto)
    for encontrado in re.finditer(r"\bingles\b|\benglish\b", normalizado):
        ventana = normalizado[max(0, encontrado.start() - 60):encontrado.end() + 60]
        if re.search(_SUAVIZA, ventana):
            continue
        if re.search(_EXIGENCIA, ventana):
            return True
    return False


def vigencia(date_posted, last_seen, hoy, ultima_corrida: str | None,
            ventana: int = 30) -> dict:
    """Estado estimado de una oferta y días de vigencia restante.

    "probablemente_cerrada": la oferta no apareció en la última corrida
    completa de recolección (su last_seen es anterior), lo que sugiere que
    ya no está publicada aunque siga en la base."""
    posted = _parse_fecha_iso(date_posted)
    seen = _parse_fecha_iso(last_seen)
    corrida = _parse_fecha_iso(ultima_corrida) if ultima_corrida else None
    out = {"dias_publicada": None, "dias_restantes_est": None, "estado": "sin_fecha"}
    if seen and corrida and seen < corrida:
        out["estado"] = "probablemente_cerrada"
        if posted:
            out["dias_publicada"] = (hoy - posted).days
        return out
    if not posted:
        return out
    dias = (hoy - posted).days
    restantes = max(0, ventana - dias)
    out.update(
        dias_publicada=dias,
        dias_restantes_est=restantes,
        estado="por_vencer" if restantes <= 7 else "activa",
    )
    return out


def _parse_fecha_iso(s):
    from datetime import date as _date
    if not s:
        return None
    try:
        return _date.fromisoformat(str(s)[:10])
    except ValueError:
        return None
