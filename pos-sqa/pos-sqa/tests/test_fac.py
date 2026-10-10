from decimal import Decimal as D
from src.impuestos import calcular_factura, redondear

def test_FAC02_gravados_y_exentos():
    r = calcular_factura([("10.00", 1, "gravado"), ("5.00", 1, "exento")])
    assert (r["base"], r["impuesto"], r["total"]) == (D("15.00"), D("1.50"), D("16.50"))

def test_FAC03_redondeo_por_linea():
    r = calcular_factura([("0.10", 1, "gravado")] * 3)
    assert r["impuesto"] == D("0.06") and r["total"] == D("0.36")
    # el impuesto sobre la base total daría 0,05 y no coincide con la suma de líneas
    assert redondear(D("0.30") * D("0.15")) == D("0.05")

def test_redondeo_mitad_sube():
    assert redondear(D("0.015")) == D("0.02")
