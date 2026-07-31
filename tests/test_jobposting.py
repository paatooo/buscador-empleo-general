# -*- coding: utf-8 -*-
import jobposting

HTML_CON_JOBPOSTING = """
<html><head>
<script type="application/ld+json">
{"@context": "https://schema.org", "@type": "JobPosting",
 "title": "Cajero/a", "description": "<p>Se busca cajero.</p><ul><li>Turno tarde</li></ul>",
 "datePosted": "2026-07-01", "validThrough": "2026-08-01T00:00:00",
 "employmentType": "FULL_TIME",
 "hiringOrganization": {"@type": "Organization", "name": "Supermercado X"},
 "jobLocation": {"@type": "Place", "address": {"@type": "PostalAddress",
   "streetAddress": "Av. Principal 123", "addressLocality": "Santiago",
   "addressRegion": "Metropolitana"}},
 "jobLocationType": "TELECOMMUTE"}
</script>
</head><body></body></html>
"""

HTML_SIN_JOBPOSTING = "<html><body><p>Sin datos estructurados</p></body></html>"


def test_extraer_encuentra_el_bloque_jobposting():
    d = jobposting.extraer(HTML_CON_JOBPOSTING)
    assert d is not None
    assert d["title"] == "Cajero/a"


def test_extraer_sin_bloque_da_none():
    assert jobposting.extraer(HTML_SIN_JOBPOSTING) is None


def test_extraer_ignora_bloques_ld_json_de_otro_tipo():
    html = """<script type="application/ld+json">
    {"@type": "Organization", "name": "X"}
    </script>"""
    assert jobposting.extraer(html) is None


def test_texto_convierte_parrafos_y_listas():
    resultado = jobposting.texto("<p>Se busca cajero.</p><ul><li>Turno tarde</li></ul>")
    assert "Se busca cajero." in resultado
    assert "- Turno tarde" in resultado


def test_texto_con_html_vacio_da_cadena_vacia():
    assert jobposting.texto("") == ""


def test_texto_con_none_da_cadena_vacia():
    assert jobposting.texto(None) == ""


def test_ubicacion_arma_direccion_legible():
    loc = {"address": {"streetAddress": "Av. Principal 123",
                       "addressLocality": "Santiago",
                       "addressRegion": "Metropolitana"}}
    assert jobposting.ubicacion({"jobLocation": loc}) == \
        "Av. Principal 123, Santiago, Metropolitana"


def test_ubicacion_sin_direccion_da_chile():
    assert jobposting.ubicacion({}) == "Chile"


def test_ubicacion_con_joblocation_no_dict_no_crashea():
    # HTML mal formado real: jobLocation como texto suelto en vez de un
    # objeto Place — no debe lanzar AttributeError.
    assert jobposting.ubicacion({"jobLocation": "Remote"}) == "Remote"
    assert jobposting.ubicacion({"jobLocation": ["Remote"]}) == "Remote"


def test_a_fila_arma_la_fila_completa():
    d = jobposting.extraer(HTML_CON_JOBPOSTING)
    fila = jobposting.a_fila(d, "http://x/1", "trabajando")
    assert fila["site"] == "trabajando"
    assert fila["job_url"] == "http://x/1"
    assert fila["title"] == "Cajero/a"
    assert fila["company"] == "Supermercado X"
    assert fila["date_posted"] == "2026-07-01"
    assert fila["is_remote"] == "True"
    assert "Postulación vigente hasta 2026-08-01" in fila["description"]
    assert "Se busca cajero." in fila["description"]


def test_a_fila_sin_empresa_da_no_informada():
    d = {"title": "Cajero", "description": ""}
    fila = jobposting.a_fila(d, "http://x/2", "laborum")
    assert fila["company"] == "No informada"
