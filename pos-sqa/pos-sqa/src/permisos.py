"""Matriz de permisos por rol (Anexo C). Todo acceso no permitido se rechaza y se registra."""
SI, NO = True, False
PERMISOS = {
    "consultar_productos": {"administrador": SI, "cajero": SI, "bodega": SI},
    "crear_editar_productos": {"administrador": SI, "cajero": NO, "bodega": SI},
    "ajustar_stock": {"administrador": SI, "cajero": NO, "bodega": SI},
    "baja_producto": {"administrador": SI, "cajero": NO, "bodega": NO},
    "registrar_ventas": {"administrador": SI, "cajero": SI, "bodega": NO},
    "anular": {"administrador": SI, "cajero": NO, "bodega": NO},
    "emitir_facturas": {"administrador": SI, "cajero": SI, "bodega": NO},
    "editar_clientes": {"administrador": SI, "cajero": SI, "bodega": NO},
    "ver_datos_personales": {"administrador": SI, "cajero": "parcial", "bodega": NO},
    "reportes": {"administrador": SI, "cajero": "propia", "bodega": NO},
    "configurar": {"administrador": SI, "cajero": NO, "bodega": NO},
}
REGISTRO_RECHAZOS = []

def permitido(rol, accion):
    ok = PERMISOS[accion][rol]
    if ok is False:
        REGISTRO_RECHAZOS.append((rol, accion))
    return ok is not False
