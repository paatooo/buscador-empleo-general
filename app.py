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
            value=valores.anios_experiencia or 0)
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
        enviado = st.form_submit_button("Guardar perfil")

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


if __name__ == "__main__":
    main()
