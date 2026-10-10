from src.permisos import permitido, REGISTRO_RECHAZOS

def test_CLI07_bodega_no_ve_datos_personales_y_se_registra():
    assert permitido("bodega", "ver_datos_personales") is False
    assert ("bodega", "ver_datos_personales") in REGISTRO_RECHAZOS

def test_roles_segun_anexo_c():
    assert permitido("cajero", "anular") is False
    assert permitido("administrador", "configurar") is True
    assert permitido("cajero", "registrar_ventas") is True
