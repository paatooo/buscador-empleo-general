from motor.atributos import (anios_experiencia, ingles_excluyente, modalidad,
                             region, tipo_contrato)


def test_region_desde_ciudad():
    assert region("Antofagasta, Chile") == "Antofagasta"


def test_region_reconoce_comuna_de_santiago():
    assert region("Las Condes") == "Metropolitana"


def test_region_desconocida():
    assert region("Ciudad Inventada") == "Sin especificar"


def test_modalidad_remoto_por_bandera():
    assert modalidad("trabajo de oficina", es_remoto=True) == "Remoto"


def test_modalidad_hibrida_desde_texto():
    assert modalidad("modalidad hibrida, 3 dias presencial") == "Híbrido"


def test_modalidad_presencial_por_defecto_si_lo_dice():
    assert modalidad("trabajo 100% presencial") == "Presencial"


def test_contrato_part_time():
    assert tipo_contrato("Contrato part time fin de semana") == "Part-time"


def test_contrato_no_especificado():
    assert tipo_contrato("Buscamos personal") == "No especificado"


def test_anios_numero_explicito():
    assert anios_experiencia("Se requieren 3 años de experiencia") == 3


def test_anios_escritos_con_palabra():
    assert anios_experiencia("mínimo dos años de experiencia") == 2


def test_anios_toma_el_menor_de_un_rango():
    assert anios_experiencia("de 2 a 4 años de experiencia") == 2


def test_anios_ausente_es_none():
    # nunca penalizar por omisión
    assert anios_experiencia("Buscamos vendedor proactivo") is None


def test_ingles_excluyente_verdadero():
    assert ingles_excluyente("inglés avanzado excluyente") is True


def test_ingles_deseable_no_es_excluyente():
    assert ingles_excluyente("inglés deseable, no excluyente") is False


def test_sin_mencion_de_ingles():
    assert ingles_excluyente("Se busca cajero") is False
