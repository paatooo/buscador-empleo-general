# -*- coding: utf-8 -*-
"""Carga la lista base de términos de búsqueda en `terminos_busqueda`.

Se corre una vez, antes de la primera recolección: sin esto la app se ve
vacía para cualquiera que entre a mirar antes de armar su perfil, porque
`recolectar.py` solo busca lo que hay en esa tabla.

Ejecutar: .venv\\Scripts\\python.exe seed.py
"""
from datetime import datetime, timezone

import db

# Los bloques del spec (sección 3), tal cual: ventas y retail,
# administración, logística, servicios, salud, educación, construcción y
# oficios, industria, tecnología y atención al cliente.
#
# El spec pide explícitamente NO sobreinvertir acá: el único trabajo de
# esta lista es que la app no se vea vacía, porque la búsqueda en vivo al
# registrarse (plan aparte) cubre lo que falte. Tampoco se inventan
# términos por encima del borrador: el spec dice que la lista definitiva
# se deriva de las categorías que publican los propios portales, con su
# número de avisos, y esa validación recién se puede hacer con datos de
# una corrida real. Hasta entonces, esto es el punto de partida.
#
# Cada término trae ~50 resultados por sitio y los portales hacen su
# propia expansión difusa ("vendedor" arrastra ejecutivo comercial,
# asesor de ventas, promotor), así que 26 términos no son 26 ocupaciones.
TERMINOS_BASE = [
    # ventas y retail
    "vendedor", "cajero", "reponedor",
    # administración
    "asistente administrativo", "recepcionista", "asistente contable",
    # logística y transporte
    "bodeguero", "conductor",
    # servicios
    "guardia de seguridad", "auxiliar de aseo", "garzón", "cocinero",
    # salud
    "tens", "enfermera",
    # educación
    "profesor", "educadora de párvulos",
    # construcción y oficios
    "maestro", "eléctrico", "soldador",
    # industria
    "operario de producción", "supervisor de producción", "mantención",
    # tecnología
    "desarrollador", "soporte ti", "analista de datos",
    # atención al cliente
    "call center",
]


def run(eng, ahora: str) -> dict:
    """Agrega los términos base que falten. Idempotente: `agregar_termino`
    no pisa el origen ni la fecha de alta de un término que ya existe, así
    que volver a correr esto no degrada a "base" un término que alguien
    pidió (los de usuario van primero en `db.terminos_pendientes`)."""
    db.ensure_schema(eng)
    ya = {f[0] for f in db.consultar(
        eng, "SELECT termino FROM terminos_busqueda")}
    agregados = 0
    for termino in TERMINOS_BASE:
        if termino in ya:
            continue
        db.agregar_termino(eng, termino, "base", ahora)
        agregados += 1
    return {"agregados": agregados,
            "ya_estaban": len(TERMINOS_BASE) - agregados}


if __name__ == "__main__":
    eng = db.engine()
    ahora = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    resumen = run(eng, ahora)
    print(f"Términos base en {db.etiqueta(eng)}: "
          f"{resumen['agregados']} agregados, "
          f"{resumen['ya_estaban']} ya estaban.")
