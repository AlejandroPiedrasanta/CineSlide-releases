# -*- coding: utf-8 -*-
"""
Prueba REAL de la actualización automática, como la vive un usuario (GitHub Actions en Mac; también en Windows, en una caja):

    python probar_actualizacion_real.py <carpeta de CineSlide instalado> [--desde=v9.63] [--sin-musica]

1) Pone en la carpeta el CineSlide.py de una versión ANTERIOR ya publicada (por defecto la penúltima; desde la 9.56, que son
   las que tienen actualizaciones firmadas).
2) Abre ESA versión (Qt sin pantalla): el chequeo automático encuentra la última versión publicada, la baja y la comprueba
   (firma + SHA-256); el aviso se contesta «Más tarde» y se cierra CineSlide. En Mac se instala SOLA al cerrar
   (_act_al_cerrar). En Windows instalar pide administrador: en la caja local se hace a mano lo mismo que hace la Mac.
3) Comprueba que quedó instalada la versión nueva, con el respaldo de la anterior y las «Novedades» pendientes.
4) Abre la versión nueva: salen las «Novedades» y, si faltaba, baja la música incluida y quedan sonando las de Boda.
Código 1 si algo falla.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
OPC = dict((a[2:].split("=", 1) + ["1"])[:2] for a in sys.argv[1:] if a.startswith("--"))
DIR = os.path.abspath(ARGS[0])
REPO = "AlejandroPiedrasanta/CineSlide-releases"
BASE = "https://github.com/%s/releases" % REPO
PY = sys.executable
FALLAS = []


def leer(url, json_=True):
    cab = {"User-Agent": "CineSlide-prueba"}
    if "api.github.com" in url and os.environ.get("GH_TOKEN"):
        cab["Authorization"] = "Bearer " + os.environ["GH_TOKEN"]
    with urllib.request.urlopen(urllib.request.Request(url, headers=cab), timeout=60) as r:
        datos = r.read()
    return json.loads(datos.decode("utf-8-sig")) if json_ else datos


def numeros(v):
    return [int(x) for x in re.findall(r"\d+", str(v or "0"))]


def version_de(ruta):
    m = re.search(r'^VERSION_MOTOR = "([\d.]+)"', open(ruta, encoding="utf-8").read(), re.M)
    return m.group(1) if m else None


def comprobar(ok, texto):
    print(("  OK    " if ok else "  FALLA ") + texto)
    if not ok:
        FALLAS.append(texto)
    sys.stdout.flush()
    return ok


# ---- la versión publicada y una anterior ----
ultima = leer(BASE + "/latest/download/version.json")["version"]
desde = OPC.get("desde")
if not desde:
    tags = [r["tag_name"] for r in leer("https://api.github.com/repos/%s/releases?per_page=30" % REPO)
            if not r.get("draft") and not r.get("prerelease")]
    viejas = sorted((t for t in tags if re.fullmatch(r"v\d+\.\d+", t) and (9, 56) <= tuple(numeros(t)) and numeros(t) < numeros(ultima)),
                    key=numeros, reverse=True)
    if not viejas:
        print("No hay una versión anterior con actualizaciones firmadas: nada que probar.")
        sys.exit(0)
    desde = viejas[0]
print("Última publicada: v%s · se prueba desde la %s · carpeta %s" % (ultima, desde, DIR))
destino = os.path.join(DIR, "CineSlide.py")
with open(destino, "wb") as f:
    f.write(leer("%s/download/%s/CineSlide.py" % (BASE, desde), json_=False))
comprobar(version_de(destino) == desde.lstrip("v"), "instalada la versión anterior (%s)" % desde)
# como un usuario que ya usó CineSlide: sin el asistente de bienvenida (es una ventana que espera un clic)
datos_dir = os.environ.get("CINESLIDE_DATOS") or os.path.join(DIR, "datos")
prefs_ruta = os.path.join(datos_dir, "presets", "_preferencias.json")
try:
    prefs0 = json.load(open(prefs_ruta, encoding="utf-8"))
except Exception:
    prefs0 = {}
prefs0["asistente_visto"] = True
os.makedirs(os.path.dirname(prefs_ruta), exist_ok=True)
json.dump(prefs0, open(prefs_ruta, "w", encoding="utf-8"), ensure_ascii=False)

# ---- fase A: la versión vieja se actualiza sola ----
FASE_A = r'''
import json, os, shutil, sys, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
carpeta = sys.argv[1]
sys.path.insert(0, carpeta)
os.chdir(carpeta)
import CineSlide as c
from PySide6 import QtWidgets
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["CineSlide"])
v = c._crear_clases_qt()(c._ProxyPrincipal())
v._licencia_pedir = lambda *a, **k: True           # la Mac de prueba no tiene licencia: su ventana esperaría un clic
avisos = []
def dialogo(info, modo):
    avisos.append([modo, info.get("version")])
    return "luego"                                  # el usuario pulsa "Más tarde"
v._act_mostrar_dialogo = dialogo
t0 = time.time()
v._act_revisar(False)                               # el chequeo automático (el mismo que hace al abrir y cada minuto)
while time.time() - t0 < 240:
    app.processEvents()
    time.sleep(0.05)
    p = v.__dict__.get("_act_prog")
    if p and p.get("fin") and avisos:
        break
p = v.__dict__.get("_act_prog") or {}
info = v.__dict__.get("_act_info") or {}
res = {"vieja": c.VERSION_MOTOR, "avisos": avisos, "bajada": bool(p.get("ruta")), "error": str(p.get("error") or ""),
       "nueva": info.get("version"), "segundos": round(time.time() - t0, 1), "datos": c._psc_base()}
if sys.platform != "darwin" and p.get("ruta"):
    # Windows (caja local): instalar pide administrador; se hace a mano lo mismo que la Mac al cerrar (_instalador_mac)
    destino = os.path.join(carpeta, "CineSlide.py")
    shutil.copyfile(destino, os.path.join(c._psc_sub("respaldo"), time.strftime("CineSlide_%Y%m%d_%H%M%S.py")))
    shutil.copyfile(p["ruta"], destino)
    v.prefs["act_novedades"] = {"version": info["version"], "notas": info.get("notas") or "", "novedades": info.get("novedades") or []}
v.close()                                           # Mac: _act_al_cerrar instala la versión ya bajada, sin preguntar
app.processEvents()
print("FASE " + json.dumps(res))
sys.stdout.flush()
os._exit(0)
'''
# ---- fase B: la versión nueva al abrir ----
FASE_B = r'''
import json, os, sys, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
carpeta, con_musica = sys.argv[1], sys.argv[2] == "1"
sys.path.insert(0, carpeta)
os.chdir(carpeta)
import CineSlide as c
from PySide6 import QtWidgets
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["CineSlide"])
v = c._crear_clases_qt()(c._ProxyPrincipal())
v._licencia_pedir = lambda *a, **k: True           # la Mac de prueba no tiene licencia: su ventana esperaría un clic
dialogos = []
def dialogo(info, modo):
    dialogos.append([modo, info.get("version"), len(info.get("novedades") or [])])
    return "listo" if modo == "novedades" else "luego"
v._act_mostrar_dialogo = dialogo
t0 = time.time()
limite = 600 if con_musica else 30
cats = []
while time.time() - t0 < limite:
    app.processEvents()
    time.sleep(0.05)
    if time.time() - t0 > 20 and not con_musica:
        break
    if con_musica and int(time.time() - t0) % 5 == 0:
        cats = [k for k, _r in c.musica_biblioteca()]
        if any(k.lower().startswith("boda") for k in cats) and not v.__dict__.get("_musica_ocupada") and time.time() - t0 > 20:
            break
for _ in range(40):                                 # lo que queda pendiente en la interfaz (activar la música, etc.)
    app.processEvents()
    time.sleep(0.05)
bib = c.musica_biblioteca()
activas = c._lista_musica(v.musica)
res = {"version": c.VERSION_MOTOR, "dialogos": dialogos, "categorias": [[k, len(r)] for k, r in bib],
       "activas": [os.path.basename(os.path.dirname(r)) + "/" + os.path.basename(r) for r in activas],
       "segundos": round(time.time() - t0, 1)}
v.close()
app.processEvents()
print("FASE " + json.dumps(res, ensure_ascii=False))
sys.stdout.flush()
os._exit(0)
'''


def fase(codigo, *args):
    p = subprocess.run([PY, "-c", codigo, DIR] + list(args), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=900,
                       env=dict(os.environ, QT_QPA_PLATFORM="offscreen"))
    salida = p.stdout.decode("utf-8", "replace")
    linea = [l for l in salida.splitlines() if l.startswith("FASE ")]
    if not linea:
        print(salida[-3000:])
        return None
    return json.loads(linea[-1][5:])


print("\n== A) CineSlide %s abierto: ¿encuentra la v%s, la baja y se instala al cerrar?" % (desde, ultima))
a = fase(FASE_A)
if comprobar(a is not None, "la versión vieja abrió y terminó"):
    print("  " + json.dumps(a, ensure_ascii=False))
    comprobar(a["nueva"] == ultima, "encontró la versión nueva (v%s)" % ultima)
    comprobar(any(x[0] == "nueva" and x[1] == ultima for x in a["avisos"]), "avisó de la versión nueva")
    comprobar(a["bajada"], "la bajó y comprobó en segundo plano (firma + SHA-256) en %.0f s %s" % (a["segundos"], a["error"]))
    comprobar(version_de(destino) == ultima, "al cerrar quedó instalada la v%s (está la %s)" % (ultima, version_de(destino)))
    resp = os.path.join(a["datos"], "respaldo")
    comprobar(os.path.isdir(resp) and any(n.startswith("CineSlide_") for n in os.listdir(resp)), "respaldo de la versión anterior")
    try:
        prefs = json.load(open(os.path.join(a["datos"], "presets", "_preferencias.json"), encoding="utf-8"))
    except Exception:
        prefs = {}
    comprobar((prefs.get("act_novedades") or {}).get("version") == ultima, "quedaron pendientes las Novedades de la v%s" % ultima)

    print("\n== B) Se abre la v%s" % ultima)
    b = fase(FASE_B, "0" if "sin-musica" in OPC else "1")
    if comprobar(b is not None, "la versión nueva abrió y terminó"):
        print("  " + json.dumps(b, ensure_ascii=False))
        comprobar(b["version"] == ultima, "corre la v%s" % ultima)
        comprobar(any(x[0] == "novedades" and x[1] == ultima for x in b["dialogos"]), "mostró las Novedades de la v%s" % ultima)
        if "sin-musica" not in OPC and numeros(ultima) >= [9, 65]:
            cats = dict((k.lower(), n) for k, n in b["categorias"])
            comprobar(cats.get("boda", 0) >= 1, "la música incluida está (Boda: %d canciones)" % cats.get("boda", 0))
            comprobar(b["activas"] and all(x.lower().startswith("boda/") for x in b["activas"]),
                      "suenan las de Boda (%d activas)" % len(b["activas"]))
print("\n%s" % ("TODO OK" if not FALLAS else "FALLAS: " + "; ".join(FALLAS)))
sys.exit(1 if FALLAS else 0)
