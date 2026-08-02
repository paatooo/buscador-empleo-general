# -*- coding: utf-8 -*-
"""Buscador de empleo personalizado — interfaz Streamlit.

Ejecutar: .venv\\Scripts\\python.exe -m streamlit run app.py
"""
from datetime import datetime, timezone

import streamlit as st

import app_data
from motor.habilidades import CATALOGO
from motor.puntaje import Perfil

st.set_page_config(page_title="Buscador de empleo — Chile",
                   page_icon="🔎", layout="wide")

HABILIDADES_DISPONIBLES = sorted(CATALOGO)


def _ahora() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def pantalla_correo() -> str | None:
    st.title("🔎 Buscador de empleo personalizado")
    st.write("Escribe tu correo para entrar. Si ya armaste tu perfil antes, "
             "lo recuperamos; si no, te lo pedimos ahora.")
    correo = st.text_input("Correo", key="login_correo",
                           placeholder="tu@correo.cl")
    if st.button("Entrar", key="login_entrar") and correo.strip():
        return correo.strip().lower()
    return None


def formulario_perfil(perfil_actual: Perfil | None) -> Perfil | None:
    st.subheader("Tu perfil")
    st.caption("Esto define qué ofertas te mostramos. Podés volver a "
               "editarlo cuando quieras.")
    valores = perfil_actual or Perfil(cargos_buscados=[])
    with st.form("form_perfil", clear_on_submit=False):
        cargos_texto = st.text_area(
            "Cargos que buscás (uno por línea)", key="perfil_cargos",
            value="\n".join(valores.cargos_buscados),
            placeholder="cajero\nasistente contable")
        habilidades = st.multiselect(
            "Habilidades que tenés (opcional)", HABILIDADES_DISPONIBLES,
            key="perfil_habilidades", default=valores.habilidades)
        c1, c2 = st.columns(2)
        anios = c1.number_input(
            "Años de experiencia", key="perfil_anios",
            min_value=0, max_value=50,
            # Explícito por `is None`, no `or 0`: con `or`, un 0 guardado
            # coincide por casualidad con el default de "no especificado"
            # y el bug quedaría invisible si ese default cambiara.
            value=0 if valores.anios_experiencia is None
                 else valores.anios_experiencia)
        region = c2.selectbox(
            "Región", ["(sin preferencia)"] + app_data.REGIONES_CHILE,
            key="perfil_region",
            index=(["(sin preferencia)"] + app_data.REGIONES_CHILE)
                  .index(valores.region) if valores.region else 0)
        acepta_remoto = st.checkbox(
            "Acepto trabajo remoto", key="perfil_remoto",
            value=valores.acepta_remoto)
        evitar_texto = st.text_area(
            "Qué querés evitar (uno por línea, opcional)",
            key="perfil_evitar", value="\n".join(valores.evitar),
            placeholder="plástico\ncall center")
        enviado = st.form_submit_button("Guardar perfil", key="perfil_guardar")

    if not enviado:
        return None

    cargos = [c.strip() for c in cargos_texto.splitlines() if c.strip()]
    if not cargos:
        st.error("Escribí al menos un cargo que estés buscando.")
        return None

    evitar = [e.strip() for e in evitar_texto.splitlines() if e.strip()]
    nuevo = Perfil(
        cargos_buscados=cargos,
        habilidades=list(habilidades),
        # Siempre el valor tal cual está en la caja — un recién egresado
        # que escribe "0" quiere decir "cero años", no "no especificado".
        # `if anios else None` trataría 0 como falsy y lo guardaría como
        # None, con lo que motor.puntaje._queda_grande nunca penalizaría
        # avisos que piden mucha más experiencia que la que la persona
        # realmente declaró.
        anios_experiencia=int(anios),
        region=None if region == "(sin preferencia)" else region,
        acepta_remoto=acepta_remoto,
        evitar=evitar,
    )
    app_data.guardar_perfil(st.session_state["usuario_id"], nuevo, _ahora())
    st.success("Perfil guardado.")
    return nuevo


ESTADOS_VIGENCIA = {"activa": "🟢 Activa", "por_vencer": "🟠 Por vencer",
                    "probablemente_cerrada": "⚫ Prob. cerrada",
                    "sin_fecha": "⚪ Sin fecha"}


@st.cache_data(ttl=300)
def _ofertas_crudas(db_path=None):
    import db
    eng = db.engine(db_path)
    db.ensure_schema(eng)
    return db.cargar_ofertas(eng)


def _tarjeta_oferta(oferta: dict, marcas: dict, usuario_id: str, prefijo: str):
    url = oferta["job_url"]
    mk = marcas.get(url, {"revisada": 0, "favorita": 0, "postulada": 0})
    with st.container(border=True):
        st.markdown(f"**{oferta['title']}** — {oferta['company']}")
        st.caption(f"{oferta.get('region') or 'Sin especificar'} · "
                   f"{oferta.get('modalidad') or 'Sin especificar'} · "
                   f"Match: {oferta['match']}")
        c1, c2, c3 = st.columns(3)
        favorita = c1.checkbox("⭐ Favorita", value=bool(mk["favorita"]),
                               key=f"{prefijo}_fav_{url}")
        postulada = c2.checkbox("📨 Postulada", value=bool(mk["postulada"]),
                                key=f"{prefijo}_post_{url}")
        revisada = c3.checkbox("✔ Revisada", value=bool(mk["revisada"]),
                               key=f"{prefijo}_rev_{url}")
        if favorita != bool(mk["favorita"]):
            app_data.set_marca(usuario_id, url, "favorita", favorita, _ahora())
        if postulada != bool(mk["postulada"]):
            app_data.set_marca(usuario_id, url, "postulada", postulada, _ahora())
        if revisada != bool(mk["revisada"]):
            app_data.set_marca(usuario_id, url, "revisada", revisada, _ahora())
        with st.expander("Ver descripción"):
            st.write(oferta.get("description") or "(sin descripción)")
            st.caption(f"Fuente: {oferta['site']} · {url}")


def tab_ofertas(perfil, usuario_id: str):
    crudas = _ofertas_crudas()
    if not crudas:
        st.info("Todavía no hay ofertas recolectadas. Vuelve a intentarlo "
                "más tarde.")
        return
    puntuadas = app_data.puntuar_ofertas(crudas, perfil)
    if not puntuadas:
        st.info("No encontramos ofertas que calcen con los cargos que "
                "buscás todavía. Probá agregar otro cargo en tu perfil.")
        return
    st.write(f"{len(puntuadas)} ofertas para vos, ordenadas por match.")
    marcas = app_data.marcas_de(usuario_id)
    for oferta in puntuadas[:50]:
        _tarjeta_oferta(oferta, marcas, usuario_id, "of")


def main():
    if "usuario_id" not in st.session_state:
        correo = pantalla_correo()
        if correo is None:
            return
        st.session_state["usuario_id"] = correo
        st.rerun()

    usuario_id = st.session_state["usuario_id"]
    st.sidebar.write(f"Sesión: {usuario_id}")
    if st.sidebar.button("Cerrar sesión", key="sidebar_logout"):
        del st.session_state["usuario_id"]
        st.rerun()

    perfil = app_data.cargar_perfil(usuario_id)
    if perfil is None or st.sidebar.checkbox("Editar perfil", key="sidebar_editar"):
        nuevo = formulario_perfil(perfil)
        if nuevo is None:
            if perfil is None:
                return  # primera vez, sin perfil todavía: no hay nada más que mostrar
        else:
            perfil = nuevo

    if perfil is None:
        return

    (t1,) = st.tabs(["🎯 Ofertas para ti"])
    with t1:
        tab_ofertas(perfil, usuario_id)


if __name__ == "__main__":
    main()
