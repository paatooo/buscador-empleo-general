from motor.texto import normalizar, tokens


def test_normalizar_quita_tildes_y_mayusculas():
    assert normalizar("Ingeniería QUÍMICA") == "ingenieria quimica"


def test_normalizar_colapsa_espacios():
    assert normalizar("  cajero   part  time ") == "cajero part time"


def test_normalizar_tolera_none():
    assert normalizar(None) == ""


def test_tokens_separa_por_no_alfanumerico():
    assert tokens("Cajero/a supermercado") == ["cajero", "supermercado"]


def test_tokens_descarta_palabras_vacias():
    assert tokens("ingeniero de procesos") == ["ingeniero", "procesos"]


def test_tokens_descarta_letras_sueltas():
    # la "a" de "Cajero/a" no aporta significado
    assert "a" not in tokens("Cajero/a")
