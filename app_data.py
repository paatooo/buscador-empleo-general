# -*- coding: utf-8 -*-
"""Consultas y agregaciones para la app — sin dependencia de Streamlit,
para poder probarlas con pytest sin levantar el runtime de la interfaz."""
import json

import db
from motor.puntaje import Aviso, Perfil, puntuar

REGIONES_CHILE = [
    "Arica y Parinacota", "Tarapacá", "Antofagasta", "Atacama", "Coquimbo",
    "Valparaíso", "Metropolitana", "O'Higgins", "Maule", "Ñuble", "Biobío",
    "La Araucanía", "Los Ríos", "Los Lagos", "Aysén", "Magallanes",
]


def cargar_perfil(usuario_id: str, db_path=None) -> Perfil | None:
    eng = db.engine(db_path)
    db.ensure_schema(eng)
    fila = db.cargar_usuario(eng, usuario_id)
    if fila is None:
        return None
    datos = json.loads(fila["perfil_json"])
    return Perfil(
        cargos_buscados=datos.get("cargos_buscados", []),
        habilidades=datos.get("habilidades", []),
        anios_experiencia=datos.get("anios_experiencia"),
        region=datos.get("region"),
        acepta_remoto=datos.get("acepta_remoto", True),
        evitar=datos.get("evitar", []),
    )


def guardar_perfil(usuario_id: str, perfil: Perfil, ahora: str,
                   db_path=None) -> None:
    eng = db.engine(db_path)
    db.ensure_schema(eng)
    datos = {
        "cargos_buscados": perfil.cargos_buscados,
        "habilidades": perfil.habilidades,
        "anios_experiencia": perfil.anios_experiencia,
        "region": perfil.region,
        "acepta_remoto": perfil.acepta_remoto,
        "evitar": perfil.evitar,
    }
    db.upsert_usuario(eng, usuario_id, json.dumps(datos, ensure_ascii=False), ahora)


def aviso_desde_oferta(oferta: dict) -> Aviso:
    habilidades = json.loads(oferta["habilidades"]) if oferta.get("habilidades") else []
    return Aviso(
        titulo=oferta.get("title") or "",
        texto=oferta.get("description") or "",
        habilidades=habilidades,
        region=oferta.get("region") or "Sin especificar",
        modalidad=oferta.get("modalidad") or "Sin especificar",
        anios_pedidos=oferta.get("anios_experiencia_pedidos"),
        ingles_excluyente=bool(oferta.get("ingles_excluyente")),
    )


def puntuar_ofertas(ofertas: list[dict], perfil: Perfil) -> list[dict]:
    """Puntúa cada oferta contra `perfil` al vuelo — nada de esto se
    guarda. Devuelve solo las visibles (afinidad de cargo por encima del
    umbral), ordenadas de mayor a menor match."""
    resultado = []
    for oferta in ofertas:
        aviso = aviso_desde_oferta(oferta)
        puntaje = puntuar(aviso, perfil)
        if not puntaje.visible:
            continue
        fila = dict(oferta)
        fila["match"] = puntaje.total
        fila["afinidad_cargo"] = puntaje.afinidad_cargo
        fila["ajustes"] = puntaje.ajustes
        resultado.append(fila)
    resultado.sort(key=lambda f: f["match"], reverse=True)
    return resultado


def marcas_de(usuario_id: str, db_path=None) -> dict:
    eng = db.engine(db_path)
    db.ensure_schema(eng)
    return db.cargar_marcas(eng, usuario_id)


def set_marca(usuario_id: str, job_url: str, campo: str, valor: bool,
             ahora: str, db_path=None) -> None:
    if campo not in db.CAMPOS_MARCA:
        raise ValueError(f"campo inválido: {campo}")
    eng = db.engine(db_path)
    db.ensure_schema(eng)
    db.upsert_marca(eng, usuario_id, job_url, campo, valor, ahora)


def es_seleccion_nueva(estado_sesion: dict, key: str, valor: str) -> bool:
    """¿Este valor es una selección genuinamente nueva en esta tabla?

    Streamlit recuerda "la fila en tal posición" seleccionada entre
    recargas (por `key`), pero la lista se reordena todo el tiempo (nuevo
    match, nuevos datos) — así que esa misma posición puede apuntar a OTRA
    oferta en la siguiente recarga. Sin este chequeo, cada recarga volvía a
    marcar como revisada lo que fuera que hubiera en esa fila en ese
    momento, sin que la persona hiciera click. Por eso solo se marca la
    primera vez que ESTE valor en particular queda seleccionado.

    Función pura sobre un dict (en producción, st.session_state) para
    poder probarla sin levantar el runtime de Streamlit."""
    clave = f"_ultima_vista_{key}"
    es_nueva = estado_sesion.get(clave) != valor
    estado_sesion[clave] = valor
    return es_nueva
