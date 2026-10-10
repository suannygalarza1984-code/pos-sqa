"""Casos de prueba del plan de SQA (Tablas 3 a 6 del informe). Un test por caso, nombrado con su ID."""
import os, sys, threading, time
from datetime import date
from decimal import Decimal as D
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pos


@pytest.fixture
def con(tmp_path):
    c = pos.conectar(str(tmp_path / "pos.db"))
    pos.iniciar_bd(c)
    pos.crear_producto(c, "P1", "Cuaderno", "2.50", 10, minimo=2)
    pos.crear_producto(c, "P2", "Lapiz", "1.00", 20)
    pos.crear_producto(c, "EX", "Arroz 1kg", "1.20", 50, gravado=False)
    return c


# ---------- INVENTARIO ----------
def test_INV_01_crear_producto_valido(con):
    pos.crear_producto(con, "N1", "Borrador", "0.50", 5)
    assert "N1" in pos.buscar_productos(con, "N1")

def test_INV_02_codigo_duplicado(con):
    with pytest.raises(ValueError, match="duplicado"):
        pos.crear_producto(con, "P1", "Otro", "1.00", 1)

def test_INV_03_precio_negativo_o_stock_no_numerico(con):
    with pytest.raises(ValueError):
        pos.crear_producto(con, "N2", "X", "-1", 5)
    with pytest.raises(ValueError):
        pos.crear_producto(con, "N3", "X", "1", "abc")

def test_INV_04_ajuste_con_movimiento(con):
    pos.ajustar_stock(con, "P1", 5, "bodega")
    pos.ajustar_stock(con, "P1", -3, "bodega")
    assert pos.stock_de(con, "P1") == 12
    m = con.execute("SELECT usuario,fecha FROM movimientos WHERE tipo='ajuste'").fetchall()
    assert len(m) == 2 and all(r["usuario"] == "bodega" and r["fecha"] for r in m)

def test_INV_05_alerta_stock_minimo(con):
    pos.ajustar_stock(con, "P1", -8, "bodega")  # queda en 2 = minimo
    assert "P1" in pos.productos_bajo_minimo(con)

def test_INV_06_baja_logica_conserva_historial(con):
    v = pos.registrar_venta(con, [("P1", 1)])
    pos.baja_logica(con, "P1")
    assert pos.obtener_producto(con, "P1") is not None
    assert pos.obtener_venta(con, v["id"]) is not None
    assert "P1" not in pos.buscar_productos(con, "P1")

def test_INV_07_busqueda_menos_de_2s(con):
    con.execute("BEGIN")
    for i in range(5000):
        con.execute("INSERT INTO productos(codigo,nombre,precio,stock) VALUES(?,?,?,?)",
                    (f"C{i:05d}", f"Producto {i}", "1.00", 1))
    con.execute("COMMIT")
    t = time.perf_counter()
    r = pos.buscar_productos(con, "Producto 49")
    assert time.perf_counter() - t < 2 and len(r) > 0

# ---------- VENTAS ----------
def test_VEN_01_venta_simple_descuenta_stock(con):
    v = pos.registrar_venta(con, [("P1", 2)])
    assert v["subtotal"] == D("5.00") and v["total"] == D("5.75")
    assert pos.stock_de(con, "P1") == 8

def test_VEN_02_varios_items_suma_exacta(con):
    v = pos.registrar_venta(con, [("P1", 3), ("P2", 2), ("EX", 5)])
    # subtotal 7.50+2.00+6.00 = 15.50 ; IVA 1.13 + 0.30 = 1.43 (por linea)
    assert v["subtotal"] == D("15.50") and v["impuesto"] == D("1.43") and v["total"] == D("16.93")

def test_VEN_03_no_vender_mas_que_stock(con):
    with pytest.raises(pos.StockInsuficiente):
        pos.registrar_venta(con, [("P1", 11)])
    assert pos.stock_de(con, "P1") == 10

def test_VEN_04_descuentos(con):
    v = pos.registrar_venta(con, [("P1", 4)], descuento=("pct", 10))   # 10.00 - 1.00
    assert v["descuento"] == D("1.00") and v["total"] == D("10.35")
    v2 = pos.registrar_venta(con, [("P1", 4)], descuento=("val", 2))
    assert v2["total"] == D("9.20")
    with pytest.raises(ValueError):
        pos.registrar_venta(con, [("P1", 1)], descuento=("val", 99))

def test_VEN_05_anulacion_restituye_stock_y_audita(con):
    v = pos.registrar_venta(con, [("P1", 4)])
    pos.anular_venta(con, v["id"], "admin")
    assert pos.stock_de(con, "P1") == 10
    assert pos.obtener_venta(con, v["id"])["estado"] == "ANULADA"
    assert con.execute("SELECT COUNT(*) c FROM auditoria WHERE evento='anulacion_venta'").fetchone()["c"] == 1

def test_VEN_06_medios_de_pago(con):
    v = pos.registrar_venta(con, [("P1", 2)], pagos=[("efectivo", 10)])
    assert v["vuelto"] == D("4.25")
    v = pos.registrar_venta(con, [("P1", 2)], pagos=[("tarjeta", "5.75")])
    assert v["vuelto"] == 0
    v = pos.registrar_venta(con, [("P1", 2)], pagos=[("tarjeta", 3), ("efectivo", 3)])
    assert v["vuelto"] == D("0.25")
    antes = pos.stock_de(con, "P1")
    with pytest.raises(pos.PagoIncompleto):
        pos.registrar_venta(con, [("P1", 2)], pagos=[("efectivo", 3)])
    assert pos.stock_de(con, "P1") == antes   # la venta incompleta no se cierra

def test_VEN_07_falla_a_mitad_no_deja_datos_inconsistentes(con):
    ventas_antes = con.execute("SELECT COUNT(*) c FROM ventas").fetchone()["c"]
    with pytest.raises(RuntimeError):
        pos.registrar_venta(con, [("P1", 3), ("P2", 2)], _falla_en="despues_de_stock")
    assert pos.stock_de(con, "P1") == 10 and pos.stock_de(con, "P2") == 20
    assert con.execute("SELECT COUNT(*) c FROM ventas").fetchone()["c"] == ventas_antes

def test_VEN_08_dos_cajeros_ultima_unidad(tmp_path):
    ruta = str(tmp_path / "conc.db")
    c = pos.conectar(ruta); pos.iniciar_bd(c)
    pos.crear_producto(c, "U1", "Ultima", "1.00", 1)
    resultados, barrera = [], threading.Barrier(2)
    def cajero():
        cx = pos.conectar(ruta)
        barrera.wait()
        try:
            pos.registrar_venta(cx, [("U1", 1)]); resultados.append("ok")
        except pos.StockInsuficiente:
            resultados.append("rechazada")
    hilos = [threading.Thread(target=cajero) for _ in range(2)]
    [h.start() for h in hilos]; [h.join() for h in hilos]
    assert sorted(resultados) == ["ok", "rechazada"] and pos.stock_de(c, "U1") == 0

# ---------- CLIENTES ----------
def test_CLI_01_cliente_valido(con):
    cid = pos.crear_cliente(con, "0912345678", "Ana Perez", "ana@mail.com", "0991234567")
    assert cid > 0

def test_CLI_02_identificacion_invalida_o_duplicada(con):
    pos.crear_cliente(con, "0912345678", "Ana")
    with pytest.raises(ValueError, match="duplicada"):
        pos.crear_cliente(con, "0912345678", "Otra")
    with pytest.raises(ValueError, match="invalida"):
        pos.crear_cliente(con, "12AB", "Mala")

def test_CLI_03_correo_o_telefono_invalido(con):
    with pytest.raises(ValueError):
        pos.crear_cliente(con, "0912345679", "X", correo="no-es-correo")
    with pytest.raises(ValueError):
        pos.crear_cliente(con, "0912345680", "X", telefono="12")

def test_CLI_04_editar_cliente_mantiene_historial(con):
    cid = pos.crear_cliente(con, "0912345678", "Ana")
    v = pos.registrar_venta(con, [("P1", 1)], cliente_id=cid)
    pos.editar_cliente(con, cid, nombre="Ana Maria")
    assert pos.historial_compras(con, cid) == [v["id"]]

def test_CLI_05_consumidor_final(con):
    v = pos.registrar_venta(con, [("P1", 1)], cliente_id=None)
    assert pos.obtener_venta(con, v["id"])["cliente_id"] is None

def test_CLI_06_historial_completo(con):
    cid = pos.crear_cliente(con, "0912345678", "Ana")
    ids = [pos.registrar_venta(con, [("P1", 1)], cliente_id=cid)["id"] for _ in range(3)]
    assert pos.historial_compras(con, cid) == ids

# ---------- FACTURACION ----------
def test_FAC_01_factura_simple(con):
    v = pos.registrar_venta(con, [("P1", 2)])
    n = pos.emitir_factura(con, v["id"], {"nombre": "Ana", "identificacion": "0912345678"})
    t = pos.reimprimir(con, n)
    assert "Ana" in t and "Subtotal 5.00" in t and "Impuesto 0.75" in t and "TOTAL 5.75" in t

def test_FAC_04_numeracion_secuencial_con_anulaciones(con):
    nums = []
    for _ in range(4):
        v = pos.registrar_venta(con, [("P2", 1)])
        nums.append(pos.emitir_factura(con, v["id"]))
    pos.anular_factura(con, nums[1], "admin")
    v = pos.registrar_venta(con, [("P2", 1)])
    nums.append(pos.emitir_factura(con, v["id"]))
    assert nums == [1, 2, 3, 4, 5] and len(set(nums)) == 5

def test_FAC_05_anular_no_elimina(con):
    v = pos.registrar_venta(con, [("P2", 1)])
    n = pos.emitir_factura(con, v["id"])
    pos.anular_factura(con, n, "admin")
    assert pos.obtener_factura(con, n)["estado"] == "ANULADA"

def test_FAC_06_reimpresion_identica(con, tmp_path):
    v = pos.registrar_venta(con, [("P1", 2)])
    n = pos.emitir_factura(con, v["id"])
    assert pos.reimprimir(con, n) == pos.reimprimir(con, n) == pos.obtener_factura(con, n)["contenido"]
    pytest.importorskip("reportlab")
    ruta = str(tmp_path / "f.pdf")
    pos.exportar_pdf(con, n, ruta)
    assert os.path.getsize(ruta) > 0

def test_FAC_07_datos_de_cliente_incompletos(con):
    v = pos.registrar_venta(con, [("P1", 1)])
    with pytest.raises(pos.DatosClienteIncompletos):
        pos.emitir_factura(con, v["id"], {"nombre": "Ana", "identificacion": ""})
    n = pos.emitir_factura(con, v["id"])   # sin datos = consumidor final
    assert "CONSUMIDOR FINAL" in pos.reimprimir(con, n)

def test_FAC_08_conciliacion_del_dia(con):
    for _ in range(3):
        v = pos.registrar_venta(con, [("P1", 1), ("EX", 2)])
        pos.emitir_factura(con, v["id"])
    assert pos.conciliacion_dia(con, date.today().isoformat()) == 0

# ---------- INTEGRACION ----------
def test_INT_01_venta_stock_factura_coherentes(con):
    v = pos.registrar_venta(con, [("P1", 3), ("EX", 4)])
    n = pos.emitir_factura(con, v["id"])
    f = pos.obtener_factura(con, n)
    assert D(f["total"]) == v["total"] and pos.stock_de(con, "P1") == 7 and pos.stock_de(con, "EX") == 46

def test_INT_02_anular_revierte_stock_y_factura(con):
    v = pos.registrar_venta(con, [("P1", 3)])
    n = pos.emitir_factura(con, v["id"])
    pos.anular_venta(con, v["id"], "admin")
    assert pos.stock_de(con, "P1") == 10 and pos.obtener_factura(con, n)["estado"] == "ANULADA"

def test_INT_03_cierre_de_caja_cuadra(con):
    ids = [pos.registrar_venta(con, [("P2", i + 1)])["id"] for i in range(4)]
    for i in ids:
        pos.emitir_factura(con, i)
    pos.anular_venta(con, ids[2], "admin")
    assert pos.conciliacion_dia(con, date.today().isoformat()) == 0
