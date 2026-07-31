# -*- coding: utf-8 -*-
import conexion


def test_leer_desde_variable_de_entorno(monkeypatch):
    monkeypatch.setenv("POSTGRES_URL", "postgresql://x/y")
    monkeypatch.setenv("POSTGRES_PASSWORD", "secreta")
    datos = conexion.leer()
    assert datos == {"postgres_url": "postgresql://x/y", "password": "secreta"}


def test_leer_sin_configuracion_da_vacio(monkeypatch, tmp_path):
    monkeypatch.delenv("POSTGRES_URL", raising=False)
    monkeypatch.setattr(conexion, "SECRETS", tmp_path / "no_existe.toml")
    assert conexion.leer() == {}


def test_url_postgres_reemplaza_el_marcador(monkeypatch):
    monkeypatch.setenv("POSTGRES_URL",
                       "postgresql://u:[YOUR-PASSWORD]@host/db")
    monkeypatch.setenv("POSTGRES_PASSWORD", "cl@ve#rara")
    url = conexion.url_postgres()
    assert url is not None
    assert "[YOUR-PASSWORD]" not in url
    assert "cl%40ve%23rara" in url  # @ y # codificados


def test_url_postgres_sin_configuracion_da_none(monkeypatch, tmp_path):
    monkeypatch.delenv("POSTGRES_URL", raising=False)
    monkeypatch.setattr(conexion, "SECRETS", tmp_path / "no_existe.toml")
    assert conexion.url_postgres() is None


def test_url_postgres_normaliza_prefijo_postgres(monkeypatch):
    monkeypatch.setenv("POSTGRES_URL", "postgres://u:pass@host/db")
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    url = conexion.url_postgres()
    assert url.startswith("postgresql://")


def test_diagnostico_sin_secrets_explica_que_falta(monkeypatch, tmp_path):
    monkeypatch.delenv("POSTGRES_URL", raising=False)
    monkeypatch.setattr(conexion, "SECRETS", tmp_path / "no_existe.toml")
    mensaje = conexion.diagnostico()
    assert mensaje is not None
    assert "secrets.toml" in mensaje


def test_diagnostico_todo_listo_da_none(monkeypatch):
    monkeypatch.setenv("POSTGRES_URL", "postgresql://u:pass@host/db")
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    assert conexion.diagnostico() is None
