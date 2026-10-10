"""Cálculo de impuestos del POS (regla de D-13): impuesto por línea, 2 decimales, 0,005 sube."""
from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")
TASAS = {"gravado": Decimal("0.15"), "tarifa0": Decimal("0"), "exento": Decimal("0")}

def redondear(valor: Decimal) -> Decimal:
    return valor.quantize(CENT, rounding=ROUND_HALF_UP)

def calcular_factura(lineas, tasas=TASAS):
    """lineas: lista de (precio, cantidad, tipo). Devuelve base, impuesto y total."""
    base = Decimal("0"); impuesto = Decimal("0")
    for precio, cantidad, tipo in lineas:
        subtotal = redondear(Decimal(str(precio)) * Decimal(str(cantidad)))
        base += subtotal
        impuesto += redondear(subtotal * tasas[tipo])
    return {"base": base, "impuesto": impuesto, "total": base + impuesto}
