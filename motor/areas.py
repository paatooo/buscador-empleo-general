# -*- coding: utf-8 -*-
"""Clasificador de áreas ocupacionales. Multi-rubro, como el catálogo de
habilidades — no solo industria/procesos. Un aviso puede calzar con más de
un área; si no calza con ninguna, es "Otra/Sin clasificar"."""
import re

from motor.texto import normalizar

CATALOGO_AREAS = {
    "Ventas y retail": r"venta|vendedor|cajero|reponedor|retail|tienda",
    "Administración": r"administrativ|contable|facturacion|recepcion|"
                      r"remuneraciones|rrhh|recursos humanos",
    "Logística y transporte": r"bodega|logistic|conductor|despacho|"
                              r"transporte|reparto|picking",
    "Servicios": r"guardia|seguridad|aseo|limpieza|garzon|cocinero|"
                 r"gastronomia|hoteleria",
    "Salud y educación": r"tens|enfermer|medic|salud|profesor|docente|"
                         r"educadora|parvulo|colegio",
    "Oficios y construcción": r"maestro|electric|soldador|gasfiter|obra|"
                              r"construccion|planos|albanil",
    "Industria": r"operario|produccion|mantenimiento|mantencion|"
                 r"supervisor de produccion|planta|maquinaria",
    "Tecnología y datos": r"desarrollador|programador|software|sql|python|"
                          r"power ?bi|analista de datos|soporte ti|"
                          r"help ?desk",
    "Atención al cliente": r"call ?center|atencion al cliente|telemarketing",
}

_COMPILADO = {nombre: re.compile(patron) for nombre, patron in CATALOGO_AREAS.items()}


def clasificar(texto) -> list[str]:
    normalizado = normalizar(texto)
    encontradas = [n for n, p in _COMPILADO.items() if p.search(normalizado)]
    return encontradas or ["Otra/Sin clasificar"]
