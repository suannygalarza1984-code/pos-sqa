import sqlite3
from src.respaldo import respaldar, restaurar

def test_restauracion_conserva_ventas(tmp_path):
    db = str(tmp_path / "pos.db"); c = sqlite3.connect(db)
    c.execute("create table ventas(id integer primary key, total text)")
    c.executemany("insert into ventas(total) values(?)", [(str(i),) for i in range(5000)]); c.commit(); c.close()
    r = respaldar(db, str(tmp_path / "resp"))
    c = sqlite3.connect(db); c.execute("delete from ventas"); c.commit(); c.close()
    minutos = restaurar(r, db)
    c = sqlite3.connect(db); n = c.execute("select count(*) from ventas").fetchone()[0]
    assert n == 5000 and minutos <= 60

def test_retencion_30(tmp_path):
    import os, time
    db = str(tmp_path / "pos.db"); sqlite3.connect(db).execute("create table t(x)")
    carpeta = str(tmp_path / "r"); os.makedirs(carpeta)
    for i in range(35): open(os.path.join(carpeta, "respaldo_2026%04d_000000.db" % i), "w").close()
    respaldar(db, carpeta)
    assert len(os.listdir(carpeta)) == 30
