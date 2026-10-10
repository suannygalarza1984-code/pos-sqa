"""Sistema POS e inventarios (version minima para pruebas de SQA).
Reglas: dinero con Decimal, impuesto por linea con redondeo a 2 decimales (0,005 sube),
transacciones atomicas en SQLite, numeracion de facturas sin saltos.
"""
import re
import sqlite3
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

TASA_GENERAL = Decimal("0.15")
CENT = Decimal("0.01")


class StockInsuficiente(Exception): pass
class PagoIncompleto(Exception): pass
class DatosClienteIncompletos(Exception): pass


def d(v):
    return Decimal(str(v))


def r2(v):
    return d(v).quantize(CENT, rounding=ROUND_HALF_UP)


def conectar(ruta):
    con = sqlite3.connect(ruta, timeout=15, isolation_level=None)
    con.row_factory = sqlite3.Row
    return con


def iniciar_bd(con):
    con.executescript("""
    CREATE TABLE IF NOT EXISTS productos(codigo TEXT PRIMARY KEY, nombre TEXT NOT NULL,
        precio TEXT NOT NULL, stock INTEGER NOT NULL CHECK(stock>=0), minimo INTEGER DEFAULT 0,
        gravado INTEGER DEFAULT 1, activo INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS movimientos(id INTEGER PRIMARY KEY AUTOINCREMENT, codigo TEXT,
        tipo TEXT, cantidad INTEGER, usuario TEXT, fecha TEXT);
    CREATE TABLE IF NOT EXISTS clientes(id INTEGER PRIMARY KEY AUTOINCREMENT,
        identificacion TEXT UNIQUE NOT NULL, nombre TEXT NOT NULL, correo TEXT, telefono TEXT);
    CREATE TABLE IF NOT EXISTS ventas(id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT,
        cliente_id INTEGER, subtotal TEXT, descuento TEXT, impuesto TEXT, total TEXT,
        estado TEXT DEFAULT 'COMPLETADA');
    CREATE TABLE IF NOT EXISTS venta_items(venta_id INTEGER, codigo TEXT, cantidad INTEGER,
        precio TEXT, gravado INTEGER, neto TEXT, impuesto TEXT);
    CREATE TABLE IF NOT EXISTS facturas(numero INTEGER PRIMARY KEY, venta_id INTEGER,
        fecha TEXT, total TEXT, estado TEXT DEFAULT 'EMITIDA', contenido TEXT);
    CREATE TABLE IF NOT EXISTS auditoria(id INTEGER PRIMARY KEY AUTOINCREMENT, evento TEXT,
        ref TEXT, usuario TEXT, fecha TEXT);
    """)


def _ahora():
    return datetime.now().isoformat(timespec="seconds")


# ---------------- Inventario ----------------
def crear_producto(con, codigo, nombre, precio, stock, minimo=0, gravado=True):
    if not codigo or not nombre:
        raise ValueError("codigo y nombre son obligatorios")
    try:
        precio = d(precio)
    except Exception:
        raise ValueError("precio invalido")
    if precio < 0:
        raise ValueError("precio negativo")
    if not isinstance(stock, int) or isinstance(stock, bool) or stock < 0:
        raise ValueError("stock debe ser un entero no negativo")
    try:
        con.execute("INSERT INTO productos(codigo,nombre,precio,stock,minimo,gravado) VALUES(?,?,?,?,?,?)",
                    (codigo, nombre, str(r2(precio)), stock, minimo, int(gravado)))
    except sqlite3.IntegrityError:
        raise ValueError("codigo duplicado")


def obtener_producto(con, codigo):
    return con.execute("SELECT * FROM productos WHERE codigo=?", (codigo,)).fetchone()


def stock_de(con, codigo):
    return obtener_producto(con, codigo)["stock"]


def ajustar_stock(con, codigo, delta, usuario):
    p = obtener_producto(con, codigo)
    if p is None:
        raise ValueError("producto inexistente")
    if p["stock"] + delta < 0:
        raise StockInsuficiente("el ajuste dejaria stock negativo")
    con.execute("BEGIN IMMEDIATE")
    con.execute("UPDATE productos SET stock=stock+? WHERE codigo=?", (delta, codigo))
    con.execute("INSERT INTO movimientos(codigo,tipo,cantidad,usuario,fecha) VALUES(?,?,?,?,?)",
                (codigo, "ajuste", delta, usuario, _ahora()))
    con.execute("COMMIT")


def productos_bajo_minimo(con):
    return [r["codigo"] for r in con.execute(
        "SELECT codigo FROM productos WHERE stock<=minimo AND activo=1")]


def baja_logica(con, codigo):
    con.execute("UPDATE productos SET activo=0 WHERE codigo=?", (codigo,))


def buscar_productos(con, texto):
    t = f"%{texto}%"
    return [r["codigo"] for r in con.execute(
        "SELECT codigo FROM productos WHERE activo=1 AND (codigo LIKE ? OR nombre LIKE ?)", (t, t))]


# ---------------- Clientes ----------------
def crear_cliente(con, identificacion, nombre, correo="", telefono=""):
    if not re.fullmatch(r"\d{10}|\d{13}", identificacion or ""):
        raise ValueError("identificacion invalida")
    if not nombre:
        raise ValueError("nombre obligatorio")
    if correo and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", correo):
        raise ValueError("correo invalido")
    if telefono and not re.fullmatch(r"\d{7,10}", telefono):
        raise ValueError("telefono invalido")
    try:
        cur = con.execute("INSERT INTO clientes(identificacion,nombre,correo,telefono) VALUES(?,?,?,?)",
                          (identificacion, nombre, correo, telefono))
    except sqlite3.IntegrityError:
        raise ValueError("identificacion duplicada")
    return cur.lastrowid


def editar_cliente(con, cliente_id, **campos):
    for k, v in campos.items():
        if k not in ("nombre", "correo", "telefono"):
            raise ValueError("campo no editable")
        con.execute(f"UPDATE clientes SET {k}=? WHERE id=?", (v, cliente_id))


def historial_compras(con, cliente_id):
    return [r["id"] for r in con.execute(
        "SELECT id FROM ventas WHERE cliente_id=? ORDER BY id", (cliente_id,))]


# ---------------- Ventas ----------------
def registrar_venta(con, items, descuento=None, pagos=None, cliente_id=None, _falla_en=None):
    """items: [(codigo, cantidad)]. descuento: ('pct', 10) o ('val', 5).
    pagos: [('efectivo', 20)]. Si no hay pagos se asume pago exacto."""
    con.execute("BEGIN IMMEDIATE")
    try:
        lineas = []
        for codigo, cant in items:
            p = obtener_producto(con, codigo)
            if p is None or not p["activo"]:
                raise ValueError(f"producto {codigo} no disponible")
            cur = con.execute("UPDATE productos SET stock=stock-? WHERE codigo=? AND stock>=?",
                              (cant, codigo, cant))
            if cur.rowcount == 0:
                raise StockInsuficiente(f"stock insuficiente de {codigo}")
            con.execute("INSERT INTO movimientos(codigo,tipo,cantidad,usuario,fecha) VALUES(?,?,?,?,?)",
                        (codigo, "venta", -cant, "caja", _ahora()))
            lineas.append([codigo, cant, d(p["precio"]), bool(p["gravado"])])
        if _falla_en == "despues_de_stock":
            raise RuntimeError("falla simulada a mitad de la transaccion")
        subtotal = sum((pr * c for _, c, pr, _ in lineas), Decimal("0"))
        desc = Decimal("0")
        if descuento:
            tipo, val = descuento
            desc = r2(subtotal * d(val) / 100) if tipo == "pct" else r2(val)
            if desc > subtotal or desc < 0:
                raise ValueError("descuento mayor al subtotal")
        asignado = Decimal("0")
        impuesto_total = Decimal("0")
        detalle = []
        for i, (codigo, c, pr, grav) in enumerate(lineas):
            bruto = pr * c
            if i == len(lineas) - 1:
                dl = desc - asignado
            else:
                dl = r2(desc * bruto / subtotal) if subtotal else Decimal("0")
            asignado += dl
            neto = bruto - dl
            imp = r2(neto * TASA_GENERAL) if grav else Decimal("0")
            impuesto_total += imp
            detalle.append((codigo, c, pr, grav, neto, imp))
        total = r2(subtotal - desc + impuesto_total)
        vuelto = Decimal("0")
        if pagos is not None:
            pagado = sum((d(m) for _, m in pagos), Decimal("0"))
            if pagado < total:
                raise PagoIncompleto("el pago no cubre el total")
            hay_efectivo = any(t == "efectivo" for t, _ in pagos)
            vuelto = pagado - total if hay_efectivo else Decimal("0")
            if pagado > total and not hay_efectivo:
                raise ValueError("pago electronico mayor al total")
        cur = con.execute(
            "INSERT INTO ventas(fecha,cliente_id,subtotal,descuento,impuesto,total) VALUES(?,?,?,?,?,?)",
            (_ahora(), cliente_id, str(r2(subtotal)), str(desc), str(impuesto_total), str(total)))
        vid = cur.lastrowid
        for codigo, c, pr, grav, neto, imp in detalle:
            con.execute("INSERT INTO venta_items VALUES(?,?,?,?,?,?,?)",
                        (vid, codigo, c, str(pr), int(grav), str(neto), str(imp)))
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return {"id": vid, "subtotal": r2(subtotal), "descuento": desc,
            "impuesto": impuesto_total, "total": total, "vuelto": vuelto}


def obtener_venta(con, vid):
    return con.execute("SELECT * FROM ventas WHERE id=?", (vid,)).fetchone()


def anular_venta(con, vid, usuario):
    v = obtener_venta(con, vid)
    if v is None or v["estado"] == "ANULADA":
        raise ValueError("venta inexistente o ya anulada")
    con.execute("BEGIN IMMEDIATE")
    for it in con.execute("SELECT codigo,cantidad FROM venta_items WHERE venta_id=?", (vid,)).fetchall():
        con.execute("UPDATE productos SET stock=stock+? WHERE codigo=?", (it["cantidad"], it["codigo"]))
        con.execute("INSERT INTO movimientos(codigo,tipo,cantidad,usuario,fecha) VALUES(?,?,?,?,?)",
                    (it["codigo"], "anulacion", it["cantidad"], usuario, _ahora()))
    con.execute("UPDATE ventas SET estado='ANULADA' WHERE id=?", (vid,))
    con.execute("UPDATE facturas SET estado='ANULADA' WHERE venta_id=?", (vid,))
    con.execute("INSERT INTO auditoria(evento,ref,usuario,fecha) VALUES(?,?,?,?)",
                ("anulacion_venta", str(vid), usuario, _ahora()))
    con.execute("COMMIT")


# ---------------- Facturacion ----------------
def emitir_factura(con, vid, datos_cliente=None):
    """datos_cliente None = consumidor final. Si se envia, exige nombre e identificacion."""
    v = obtener_venta(con, vid)
    if v is None or v["estado"] != "COMPLETADA":
        raise ValueError("venta no facturable")
    if datos_cliente is not None and not (datos_cliente.get("nombre") and datos_cliente.get("identificacion")):
        raise DatosClienteIncompletos("faltan nombre o identificacion del cliente")
    nombre = datos_cliente["nombre"] if datos_cliente else "CONSUMIDOR FINAL"
    ident = datos_cliente["identificacion"] if datos_cliente else "9999999999"
    con.execute("BEGIN IMMEDIATE")
    try:
        ultimo = con.execute("SELECT COALESCE(MAX(numero),0) m FROM facturas").fetchone()["m"]
        numero = ultimo + 1
        lineas = con.execute("SELECT * FROM venta_items WHERE venta_id=?", (vid,)).fetchall()
        txt = [f"FACTURA {numero:09d}", f"Cliente: {nombre} ({ident})"]
        for it in lineas:
            txt.append(f"{it['codigo']} x{it['cantidad']} neto {it['neto']} IVA {it['impuesto']}")
        txt += [f"Subtotal {v['subtotal']}", f"Descuento {v['descuento']}",
                f"Impuesto {v['impuesto']}", f"TOTAL {v['total']}"]
        con.execute("INSERT INTO facturas(numero,venta_id,fecha,total,contenido) VALUES(?,?,?,?,?)",
                    (numero, vid, _ahora(), v["total"], "\n".join(txt)))
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return numero


def obtener_factura(con, numero):
    return con.execute("SELECT * FROM facturas WHERE numero=?", (numero,)).fetchone()


def anular_factura(con, numero, usuario):
    f = obtener_factura(con, numero)
    if f is None:
        raise ValueError("factura inexistente")
    con.execute("UPDATE facturas SET estado='ANULADA' WHERE numero=?", (numero,))
    con.execute("INSERT INTO auditoria(evento,ref,usuario,fecha) VALUES(?,?,?,?)",
                ("anulacion_factura", str(numero), usuario, _ahora()))


def reimprimir(con, numero):
    return obtener_factura(con, numero)["contenido"]


def exportar_pdf(con, numero, ruta):
    from reportlab.pdfgen import canvas  # pip install reportlab
    c = canvas.Canvas(ruta)
    y = 800
    for linea in reimprimir(con, numero).split("\n"):
        c.drawString(50, y, linea)
        y -= 18
    c.save()


def conciliacion_dia(con, fecha_iso):
    """Diferencia entre el total de ventas vigentes y el de facturas vigentes del dia."""
    tv = sum((d(r["total"]) for r in con.execute(
        "SELECT total FROM ventas WHERE estado='COMPLETADA' AND fecha LIKE ?", (fecha_iso + "%",))), Decimal("0"))
    tf = sum((d(r["total"]) for r in con.execute(
        "SELECT total FROM facturas WHERE estado='EMITIDA' AND fecha LIKE ?", (fecha_iso + "%",))), Decimal("0"))
    return tv - tf
