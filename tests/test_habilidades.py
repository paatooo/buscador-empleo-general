from motor.habilidades import CATALOGO, detectar


def test_detecta_habilidad_simple():
    assert "Excel" in detectar("Manejo de Excel nivel intermedio")


def test_detecta_sin_importar_tildes_ni_mayusculas():
    assert "Atención a público" in detectar("ATENCION A PUBLICO")


def test_no_detecta_lo_que_no_esta():
    assert "Soldadura" not in detectar("Manejo de Excel")


def test_aviso_sin_habilidades_devuelve_lista_vacia():
    assert detectar("Se busca persona responsable y puntual") == []


def test_catalogo_cubre_varios_rubros():
    # el motor debe servir más allá de perfiles industriales
    esperadas = {"Excel", "Manejo de caja", "Soldadura", "Atención a público"}
    assert esperadas.issubset(set(CATALOGO))


def test_todos_los_patrones_compilan():
    import re
    assert len(CATALOGO) >= 30, "el catálogo debe cubrir varios rubros"
    for nombre, patron in CATALOGO.items():
        assert re.compile(patron).pattern == patron, f"patrón inválido: {nombre}"
