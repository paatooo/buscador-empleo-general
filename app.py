# -*- coding: utf-8 -*-
"""Buscador de empleo personalizado — interfaz Streamlit.

Ejecutar: .venv\\Scripts\\python.exe -m streamlit run app.py
"""
from datetime import datetime, timezone

import plotly.express as px
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

    crudas = _ofertas_crudas()
    if not app_data.puntuar_ofertas(app_data.sin_duplicadas(crudas), nuevo):
        _buscar_en_vivo_con_progreso(nuevo.cargos_buscados)

    return nuevo


def _buscar_en_vivo_con_progreso(cargos: list[str]) -> None:
    """Ningún cargo del perfil recién guardado calza con nada — busca en
    vivo contra las cuatro fuentes (tope de tiempo, resultados parciales)
    en vez de dejar a la persona con la app vacía hasta la corrida
    programada de mañana."""
    import buscar_en_vivo
    import db

    # st.progress no es un widget con estado (no acepta key=) — es un
    # elemento de despliegue puro, así que no le aplica el problema de
    # DuplicateElementId que sí afecta a los widgets interactivos.
    barra = st.progress(
        0.0, text="Todavía no tenemos ofertas para tu perfil — buscando en "
                  "vivo (esta es una primera pasada; mañana habrá más).")

    def avance(indice, total, cargo):
        barra.progress(indice / total, text=f"Buscando «{cargo}»"
                       f" ({indice}/{total})...")

    eng = db.engine()
    try:
        resumen = buscar_en_vivo.buscar(eng, cargos, on_progreso=avance)
    except Exception as e:
        # El perfil ya se guardó (ver `st.success` más arriba) antes de
        # llegar acá — una falla transitoria a mitad de una búsqueda que
        # ahora puede tomar varios minutos (ver PRESUPUESTO_SEGUNDOS_DEFECTO
        # en buscar_en_vivo.py) no debe dejar a la persona con un
        # traceback crudo por algo que de todos modos ya funcionó.
        barra.empty()
        print(f"[ERROR] busqueda en vivo: {e}")
        st.warning("No pudimos completar la búsqueda en vivo — probá de "
                  "nuevo más tarde, o esperá a la próxima corrida "
                  "programada.")
        _ofertas_crudas.clear()
        return
    barra.empty()

    # Limpiar siempre, no solo cuando ofertas_nuevas trae algo: en un caso
    # extremo (una fuente devuelve filas junto con un error, así que
    # alguna_respondio queda en False) una oferta puede haberse insertado
    # sin que el cargo tenga clave en ofertas_nuevas — más barato limpiar
    # de más (una lectura extra a la base) que arriesgar una caché
    # desactualizada.
    _ofertas_crudas.clear()
    if not any(resumen["ofertas_nuevas"].values()):
        st.info("Todavía no encontramos ofertas publicadas para lo que "
                "buscás — seguimos intentando en las próximas corridas.")


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
                   f"Match: {oferta['match']} · "
                   f"{ESTADOS_VIGENCIA[app_data.estado_vigencia(oferta)]}")
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
    # Sin esto el mismo aviso republicado en otra fuente aparece dos veces
    # seguidas, con idéntico match — "Filtro avanzado" es el único lugar
    # donde las duplicadas se pueden ver, y así lo dice su propio texto.
    puntuadas = app_data.puntuar_ofertas(app_data.sin_duplicadas(crudas), perfil)
    if not puntuadas:
        st.info("No encontramos ofertas que calcen con los cargos que "
                "buscás todavía. Probá agregar otro cargo en tu perfil.")
        return
    st.write(f"{len(puntuadas)} ofertas para vos, ordenadas por match.")
    marcas = app_data.marcas_de(usuario_id)
    for oferta in puntuadas[:50]:
        _tarjeta_oferta(oferta, marcas, usuario_id, "of")


def tab_filtro_avanzado(perfil, usuario_id: str):
    crudas = _ofertas_crudas()
    if not crudas:
        st.info("Todavía no hay ofertas recolectadas.")
        return
    puntuadas = app_data.puntuar_ofertas(crudas, perfil)
    df = app_data.a_dataframe(puntuadas)
    if df.empty:
        st.info("No hay ofertas que calcen con tu perfil todavía.")
        return

    st.caption("Filtro con control total sobre cada criterio — a "
               "diferencia de «Ofertas para ti», acá podés ver también lo "
               "que normalmente queda afuera (duplicadas, con inglés "
               "excluyente, etc.).")

    c1, c2 = st.columns(2)
    match_min, match_max = c1.slider("Rango de match", 0, 100, (0, 100),
                                     key="av_match")
    texto_libre = c2.text_input(
        "Buscar texto (cargo, empresa o descripción)",
        key="av_texto", placeholder="Ej: turno tarde")

    c1, c2, c3, c4, c5 = st.columns(5)
    areas_sel = c1.multiselect(
        "Áreas", sorted(df["areas"].explode().dropna().unique()),
        key="av_areas")
    regiones_sel = c2.multiselect(
        "Región", sorted(df["region"].dropna().unique()), key="av_regiones")
    modalidades_sel = c3.multiselect(
        "Modalidad", sorted(df["modalidad"].dropna().unique()),
        key="av_modalidades")
    contratos_sel = c4.multiselect(
        "Contrato", sorted(df["tipo_contrato"].dropna().unique()),
        key="av_contratos")
    fuentes_sel = c5.multiselect(
        "Fuente", sorted(df["site"].dropna().unique()), key="av_fuentes")

    c1, c2 = st.columns(2)
    incluir_duplicadas = c1.checkbox("Incluir duplicadas", False, key="av_dup")
    incluir_ingles = c2.checkbox("Incluir con inglés excluyente", True,
                                 key="av_ingles")

    sel = df.copy()
    if not incluir_duplicadas:
        sel = sel[sel["duplicada"] != 1]
    if not incluir_ingles:
        sel = sel[sel["ingles_excluyente"] != 1]
    sel = sel[sel["match"].between(match_min, match_max)]
    if texto_libre.strip():
        import re
        from motor.texto import normalizar
        t = normalizar(texto_libre)
        campo = (sel["title"].fillna("").map(normalizar) + " "
                 + sel["company"].fillna("").map(normalizar) + " "
                 + sel["description"].fillna("").map(normalizar))
        sel = sel[campo.str.contains(re.escape(t))]
    if areas_sel:
        objetivo = set(areas_sel)
        sel = sel[sel["areas"].map(lambda a: bool(objetivo & set(a)))]
    if regiones_sel:
        sel = sel[sel["region"].isin(regiones_sel)]
    if modalidades_sel:
        sel = sel[sel["modalidad"].isin(modalidades_sel)]
    if contratos_sel:
        sel = sel[sel["tipo_contrato"].isin(contratos_sel)]
    if fuentes_sel:
        sel = sel[sel["site"].isin(fuentes_sel)]

    st.write(f"{len(sel)} ofertas con estos filtros.")
    st.dataframe(
        sel[["title", "company", "region", "modalidad", "tipo_contrato",
             "match", "site"]].sort_values("match", ascending=False),
        width="stretch", key="av_tabla")


def _foto_del_momento(df):
    """Áreas y habilidades más pedidas en la única corrida que hay."""
    areas = app_data.conteo_areas(df)
    if not areas.empty:
        st.plotly_chart(
            px.bar(x=areas.values, y=areas.index, orientation="h",
                   labels={"x": "ofertas", "y": "área"},
                   title="Ofertas por área"),
            width="stretch", key="td_foto_areas")
    habilidades = app_data.conteo_habilidades(df)
    if habilidades.empty:
        st.caption("Ninguna de las ofertas capturadas menciona habilidades "
                   "del catálogo todavía.")
        return
    st.plotly_chart(
        px.bar(habilidades.head(10), x="ofertas", y="habilidad",
               orientation="h", title="Top 10 habilidades pedidas"),
        width="stretch", key="td_foto_habilidades")
    st.caption("«pct» es el porcentaje de las ofertas capturadas que pide "
               "esa habilidad.")
    st.dataframe(habilidades, width="stretch", key="td_foto_tabla")


def tab_tendencias(perfil, usuario_id: str):
    # Igual que en "Ofertas para ti": contar dos veces el mismo aviso
    # republicado infla la serie de un área o una habilidad sin que haya
    # más demanda real detrás.
    crudas = app_data.sin_duplicadas(_ofertas_crudas())
    df = app_data.a_dataframe(crudas)
    if df.empty:
        st.info("Todavía no hay ofertas recolectadas.")
        return
    tendencias = app_data.tendencias_por_fecha(df)
    if tendencias is None:
        # Con una sola corrida no hay serie en el tiempo, pero sí hay algo
        # que mirar: la foto del momento. Sin esto la pestaña queda vacía
        # justamente el día 1, que es cuando más gente la abre.
        st.info("Todavía hay una sola fecha de captura, así que no hay "
                "tendencia en el tiempo para mostrar — por ahora, la foto "
                "de lo que se está pidiendo hoy.")
        _foto_del_momento(df)
        return
    st.plotly_chart(
        px.line(tendencias["areas"], x="scrape_date", y="ofertas",
               color="area", title="Ofertas por área en el tiempo"),
        width="stretch", key="td_areas")
    top_habilidades = (tendencias["habilidades"].groupby("habilidad")["ofertas"]
                       .sum().nlargest(10).index)
    hab_top = tendencias["habilidades"][
        tendencias["habilidades"]["habilidad"].isin(top_habilidades)]
    st.plotly_chart(
        px.line(hab_top, x="scrape_date", y="ofertas", color="habilidad",
               title="Top 10 habilidades pedidas en el tiempo"),
        width="stretch", key="td_habilidades")


def tab_empresas(perfil, usuario_id: str):
    crudas = app_data.sin_duplicadas(_ofertas_crudas())
    df = app_data.a_dataframe(crudas)
    if df.empty:
        st.info("Todavía no hay ofertas recolectadas.")
        return
    tabla = app_data.radar_empresas(df)
    st.write(f"{len(tabla)} empresas con avisos publicados.")
    st.dataframe(tabla, width="stretch", key="em_tabla")


def tab_acerca(perfil, usuario_id: str):
    crudas = _ofertas_crudas()
    unicas = len(app_data.sin_duplicadas(crudas))
    st.write(f"**Ofertas en la base:** {len(crudas)}")
    repetidas = len(crudas) - unicas
    if repetidas:
        cuantas = ("Una es" if repetidas == 1
                   else f"{repetidas} son")
        st.caption(f"{cuantas} el mismo aviso publicado en más de una "
                   f"fuente: el resto de las pestañas trabaja con las "
                   f"{unicas} ofertas distintas.")
    if crudas:
        ultima = max((o.get("scrape_date") or "" for o in crudas), default="")
        st.write(f"**Última corrida con datos:** {ultima or 'sin registro'}")
    st.write("**Fuentes:** Get on Board, Computrabajo, Trabajando.cl, "
             "Laborum.cl.")
    st.write("El puntaje de cada oferta se calcula al momento de cargar la "
             "página, contra tu perfil — no se guarda en ningún lado ni se "
             "comparte entre usuarios.")
    st.caption("Mientras el ingreso sea solo por correo, evitá compartir "
               "esta app con desconocidos: cualquiera que escriba tu "
               "correo puede ver tu perfil y tus marcas.")


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

    t1, t2, t3, t4, t5 = st.tabs(
        ["🎯 Ofertas para ti", "🔬 Filtro avanzado", "📈 Tendencias",
         "🏢 Empresas", "ℹ️ Acerca de los datos"])
    with t1:
        tab_ofertas(perfil, usuario_id)
    with t2:
        tab_filtro_avanzado(perfil, usuario_id)
    with t3:
        tab_tendencias(perfil, usuario_id)
    with t4:
        tab_empresas(perfil, usuario_id)
    with t5:
        tab_acerca(perfil, usuario_id)


if __name__ == "__main__":
    main()
