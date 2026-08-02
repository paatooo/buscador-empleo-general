# -*- coding: utf-8 -*-
"""Consultas y agregaciones para la app — sin dependencia de Streamlit,
para poder probarlas con pytest sin levantar el runtime de la interfaz."""
import json

import pandas as pd

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


def a_dataframe(ofertas: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(ofertas)
    if df.empty:
        return df
    df["habilidades"] = df["habilidades"].map(
        lambda s: json.loads(s) if s else [])
    df["areas"] = df["areas"].map(lambda s: json.loads(s) if s else [])
    return df


def conteo_areas(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype="int64")
    return df["areas"].explode().value_counts()


_COLUMNAS_CONTEO_HABILIDADES = {
    "habilidad": "object", "ofertas": "int64", "pct": "float64"}


def conteo_habilidades(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        conteo = pd.Series(dtype="int64")
    else:
        conteo = df["habilidades"].explode().dropna().value_counts()
    if conteo.empty:
        return pd.DataFrame({c: pd.Series(dtype=t)
                             for c, t in _COLUMNAS_CONTEO_HABILIDADES.items()})
    out = conteo.rename_axis("habilidad").reset_index(name="ofertas")
    out["pct"] = (100 * out["ofertas"] / max(1, len(df))).round(1)
    return out


def tendencias_por_fecha(df: pd.DataFrame):
    """None si hay menos de 2 fechas de captura distintas — aún no hay
    tendencia real que mostrar, solo una foto."""
    if df.empty or df["scrape_date"].nunique() < 2:
        return None
    hab = (df.explode("habilidades").dropna(subset=["habilidades"])
           .groupby(["scrape_date", "habilidades"]).size()
           .rename("ofertas").reset_index()
           .rename(columns={"habilidades": "habilidad"}))
    areas = (df.explode("areas").dropna(subset=["areas"])
             .groupby(["scrape_date", "areas"]).size()
             .rename("ofertas").reset_index()
             .rename(columns={"areas": "area"}))
    return {"habilidades": hab, "areas": areas}


def radar_empresas(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["empresa", "ofertas", "areas", "top_habilidades"])
    g = df.groupby("company")
    out = pd.DataFrame({
        "ofertas": g.size(),
        "areas": g["areas"].apply(
            lambda s: ", ".join(sorted({a for row in s for a in row}))),
        "top_habilidades": g["habilidades"].apply(
            lambda s: ", ".join(pd.Series(
                [h for row in s for h in row]).value_counts().head(5).index)),
    })
    return (out.sort_values("ofertas", ascending=False)
            .rename_axis("empresa").reset_index())
