# Requisitos de calidad del POS, versión 0.2 (cierre de defectos altos)
- RQ-CAL-01 (D-01) Con 3 usuarios simultáneos y un catálogo de 5 000 productos, registrar una venta de hasta 20 ítems y emitir el comprobante toma 3 s o menos (percentil 95 de 100 ventas). Prueba: VEN-02, FAC-01.
- RQ-CAL-02 (D-08) Máximo 1 fallo que interrumpa una venta por cada 500 ventas, en 30 días de operación. Prueba: VEN-07.
- RQ-CAL-03 (D-09) Respaldo completo al cierre de cada jornada; se conservan 30; restauración en 60 min o menos; pérdida máxima 24 h. Prueba: tests/test_respaldo.py.
- RQ-CAL-04 (D-10) Un rol por usuario; solo las acciones del Anexo C; todo acceso no permitido se rechaza y se registra. Prueba: CLI-07, tests/test_cli07.py.
- RQ-CAL-05 (D-13) Tasa por tipo de producto (gravado 15 %, tarifa 0 %, exento); impuesto por línea con 2 decimales (0,005 sube); total = suma de líneas. Prueba: FAC-02, FAC-03.
