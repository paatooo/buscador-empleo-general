from motor.cargo import UMBRAL_VISIBILIDAD, afinidad


def test_cargo_exacto_da_afinidad_maxima():
    assert afinidad(["cajero"], "Cajero/a supermercado turno tarde") == 1.0


def test_cargo_sin_relacion_da_cero():
    assert afinidad(["cajero"], "Ingeniero de Procesos Senior") == 0.0


def test_tolera_plural():
    # "cajeros" y "cajero" son el mismo cargo
    assert afinidad(["cajero"], "Se buscan cajeros") >= UMBRAL_VISIBILIDAD


def test_tolera_genero():
    # "cajera" y "cajero" también. Este caso obliga a que el umbral de
    # similitud entre palabras no pase de 0.80.
    assert afinidad(["cajero"], "Cajera de local") >= UMBRAL_VISIBILIDAD


def test_todas_las_palabras_del_cargo_cuentan():
    # "asistente contable" contra un título que solo trae "asistente":
    # media afinidad, no afinidad total
    valor = afinidad(["asistente contable"], "Asistente administrativo")
    assert 0.4 < valor < 0.75


def test_toma_el_mejor_de_varios_cargos_buscados():
    assert afinidad(["cajero", "ingeniero de procesos"],
                    "Ingeniero de Procesos") == 1.0


def test_sin_cargos_buscados_da_cero():
    assert afinidad([], "Cajero") == 0.0


def test_titulo_vacio_da_cero():
    assert afinidad(["cajero"], "") == 0.0
