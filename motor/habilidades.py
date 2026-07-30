# -*- coding: utf-8 -*-
"""Catálogo de habilidades y su detección en el texto de un aviso.

Las habilidades refinan el puntaje, no lo determinan: un aviso que no
menciona ninguna sigue puntuando por afinidad de cargo. El catálogo cubre
varios rubros a propósito — el motor sirve a cualquier ocupación, no solo a
perfiles industriales. Crece con el uso.

Los patrones se evalúan sobre texto ya normalizado (minúsculas, sin tildes).
"""
import re

from motor.texto import normalizar

CATALOGO = {
    # Transversales
    "Excel": r"\bexcel\b",
    "Office": r"\boffice\b|word y excel",
    "Atención a público": r"atencion a (publico|clientes?)|servicio al cliente",
    "Trabajo en equipo": r"trabajo en equipo",
    "Inglés": r"\bingles\b|\benglish\b",
    "Licencia de conducir": r"licencia de conducir|licencia clase",
    # Comercio y retail
    "Manejo de caja": r"manejo de caja|caja registradora|cuadratura de caja",
    "Ventas": r"\bventas?\b|fuerza de venta",
    "Reposición": r"reposicion|reponedor",
    "Inventario": r"inventario|toma de inventario",
    # Administración y finanzas
    "Contabilidad": r"contabilidad|contable",
    "Facturación": r"facturacion|boletas? y facturas?",
    "Remuneraciones": r"remuneraciones|liquidaciones de sueldo",
    "SAP": r"\bsap\b",
    "ERP": r"\berp\b",
    # Datos y tecnología
    "SQL": r"\bsql\b",
    "Python": r"\bpython\b",
    "Power BI": r"power\s*bi",
    "Soporte TI": r"soporte (tecnico|ti)|mesa de ayuda|help ?desk",
    "Desarrollo web": r"desarrollo web|javascript|\breact\b|\bhtml\b",
    # Logística y transporte
    "Manejo de grúa horquilla": r"grua horquilla|montacargas",
    "Picking y packing": r"picking|packing|preparacion de pedidos",
    "Despacho": r"despacho|reparto|ultima milla",
    # Oficios y construcción
    "Soldadura": r"soldadura|soldador",
    "Electricidad": r"electricidad|instalaciones electricas|electrico",
    "Gasfitería": r"gasfiteria|gasfiter",
    "Lectura de planos": r"lectura de planos|interpretacion de planos",
    "AutoCAD": r"autocad",
    # Industria
    "Mantenimiento": r"mantenimiento|mantencion",
    "Operación de maquinaria": r"operacion de maquinaria|operar maquinas",
    "Mejora continua": r"mejora continua|\blean\b|six sigma|kaizen",
    "Control de calidad": r"control de calidad|aseguramiento de calidad",
    "ISO 9001": r"iso\s*9001",
    "Prevención de riesgos": r"prevencion de riesgos|\bsso\b|seguridad y salud",
    # Alimentación y servicios
    "Manipulación de alimentos": r"manipulacion de alimentos|resolucion sanitaria",
    "HACCP": r"haccp",
    "Cocina": r"\bcocina\b|cocinero|garzon",
    "Aseo y limpieza": r"\baseo\b|limpieza|sanitizacion",
    # Salud y educación
    "Cuidado de pacientes": r"cuidado de pacientes|atencion de pacientes",
    "Toma de signos vitales": r"signos vitales",
    "Planificación de clases": r"planificacion de clases|planificaciones",
}

_COMPILADO = {nombre: re.compile(patron) for nombre, patron in CATALOGO.items()}


def detectar(texto) -> list[str]:
    """Habilidades del catálogo presentes en el texto. Lista vacía si ninguna."""
    normalizado = normalizar(texto)
    return [n for n, p in _COMPILADO.items() if p.search(normalizado)]
