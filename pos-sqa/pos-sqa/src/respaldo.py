"""Respaldo y restauración de la base de datos (política del Anexo D)."""
import sqlite3, shutil, time, os, glob

def respaldar(db, carpeta, retencion=30):
    os.makedirs(carpeta, exist_ok=True)
    destino = os.path.join(carpeta, "respaldo_%s.db" % time.strftime("%Y%m%d_%H%M%S"))
    origen = sqlite3.connect(db); copia = sqlite3.connect(destino)
    origen.backup(copia); copia.close(); origen.close()
    viejos = sorted(glob.glob(os.path.join(carpeta, "respaldo_*.db")))
    for v in viejos[:-retencion]: os.remove(v)
    return destino

def restaurar(respaldo, db):
    t0 = time.perf_counter(); shutil.copyfile(respaldo, db)
    return (time.perf_counter() - t0) / 60  # minutos
