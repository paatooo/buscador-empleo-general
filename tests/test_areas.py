# -*- coding: utf-8 -*-
from motor.areas import CATALOGO_AREAS, clasificar


def test_clasifica_ventas_y_retail():
    assert "Ventas y retail" in clasificar("Se busca cajero para supermercado")


def test_clasifica_administracion():
    assert "Administración" in clasificar("Asistente contable, manejo de facturación")


def test_clasifica_tecnologia():
    assert "Tecnología y datos" in clasificar("Desarrollador Python, SQL")


def test_clasifica_oficios_y_construccion():
    assert "Oficios y construcción" in clasificar("Soldador con experiencia en planos")


def test_clasifica_salud_y_educacion():
    assert "Salud y educación" in clasificar("TENS para clínica")


def test_sin_calce_da_otra_sin_clasificar():
    assert clasificar("xyz sin ninguna coincidencia") == ["Otra/Sin clasificar"]


def test_puede_calzar_mas_de_un_area():
    areas = clasificar("Analista de ventas con manejo de Excel y Power BI")
    assert len(areas) >= 1  # al menos una calza; no exige exclusividad


def test_catalogo_cubre_varios_rubros():
    assert len(CATALOGO_AREAS) >= 8
