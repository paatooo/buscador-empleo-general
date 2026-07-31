from motor.atributos import (anios_experiencia, ingles_excluyente, modalidad,
                             region, tipo_contrato, vigencia)


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


def test_anios_no_confunde_rango_de_edad_con_experiencia():
    # "de 20 a 45 años" es un rango de edad, no de experiencia — no debe
    # devolver un número inventado.
    assert anios_experiencia("Se buscan personas de 20 a 45 anos, buena presencia") is None


def test_anios_no_confunde_edad_minima_con_experiencia():
    assert anios_experiencia("minimo 18 anos de edad") is None


def test_anios_no_confunde_edad_para_conducir_con_experiencia():
    assert anios_experiencia("requisito: minimo 21 anos para conducir") is None


def test_ingles_excluyente_verdadero():
    assert ingles_excluyente("inglés avanzado excluyente") is True


def test_ingles_deseable_no_es_excluyente():
    assert ingles_excluyente("inglés deseable, no excluyente") is False


def test_ingles_no_es_requisito_no_es_excluyente():
    assert ingles_excluyente("El ingles no es requisito para este cargo") is False


def test_ingles_no_obligatorio_no_es_excluyente():
    assert ingles_excluyente("Ingles no obligatorio pero valorado") is False


def test_ingles_no_es_obligatorio_no_es_excluyente():
    assert ingles_excluyente("el ingles no es obligatorio para el cargo") is False


def test_ingles_no_es_indispensable_no_es_excluyente():
    assert ingles_excluyente("el ingles no es indispensable") is False


def test_sin_mencion_de_ingles():
    assert ingles_excluyente("Se busca cajero") is False


def test_vigencia_activa_dentro_de_la_ventana():
    from datetime import date
    resultado = vigencia("2026-07-01", "2026-07-20", date(2026, 7, 20),
                         "2026-07-20", ventana=30)
    assert resultado["estado"] == "activa"
    assert resultado["dias_publicada"] == 19


def test_vigencia_por_vencer_cerca_del_limite():
    from datetime import date
    resultado = vigencia("2026-07-01", "2026-07-25", date(2026, 7, 25),
                         "2026-07-25", ventana=30)
    assert resultado["estado"] == "por_vencer"


def test_vigencia_probablemente_cerrada_si_no_aparecio_en_la_ultima_corrida():
    from datetime import date
    # last_seen es anterior a la última corrida completa: no se vio hoy
    resultado = vigencia("2026-07-01", "2026-07-10", date(2026, 7, 25),
                         "2026-07-25", ventana=30)
    assert resultado["estado"] == "probablemente_cerrada"


def test_vigencia_sin_fecha_publicada():
    from datetime import date
    resultado = vigencia(None, "2026-07-25", date(2026, 7, 25), "2026-07-25")
    assert resultado["estado"] == "sin_fecha"
    assert resultado["dias_publicada"] is None


def test_vigencia_sin_ultima_corrida_no_marca_cerrada():
    from datetime import date
    resultado = vigencia("2026-07-01", "2026-07-20", date(2026, 7, 20), None)
    assert resultado["estado"] == "activa"
