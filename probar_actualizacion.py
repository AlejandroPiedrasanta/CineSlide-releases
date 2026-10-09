# -*- coding: utf-8 -*-
"""
Prueba de la actualización automática de CineSlide (sin pantalla). Se usa en GitHub Actions (macOS) y también en Windows:

    python probar_actualizacion.py <carpeta con CineSlide.py>

1) Se hace pasar por una versión vieja (9.0) y lee el version.json REAL del último Release.
2) Descarga CineSlide.py y comprueba SHA-256 + contrato + sintaxis.
3) Abre la ventana principal (Qt "offscreen") y comprueba que SALE el aviso "Actualización disponible" con la versión nueva.
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
carpeta = os.path.abspath(sys.argv[1])
sys.path.insert(0, carpeta)
os.chdir(carpeta)
import CineSlide as c  # noqa: E402

c.VERSION_MOTOR = "9.0"
info = c.actualizacion_buscar()
assert info, "actualizacion_buscar no encontró la versión publicada (URL: %s)" % c.ACT_URL_VERSION
print("Versión publicada:", info["version"], "| notas:", info["notas"])
ruta = c.actualizacion_descargar(info)
assert os.path.getsize(ruta) > 1000000, "CineSlide.py descargado demasiado pequeño"
print("Descarga verificada (sha256 + contrato + sintaxis):", ruta)

from PySide6 import QtWidgets  # noqa: E402

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["CineSlide"])
Ventana = c._crear_clases_qt()
visto = {}


def pregunta(self, titulo, texto, *a, **k):
    visto["titulo"], visto["texto"] = titulo, texto
    return QtWidgets.QMessageBox.StandardButton.No          # el usuario pulsa "No": no instala nada


QtWidgets.QMessageBox.question = staticmethod(pregunta)
ventana = Ventana(None, c._ProxyPrincipal())
ventana._act_ofrecer(info, True)
assert visto.get("titulo") == "Actualización disponible", "no salió el aviso de versión nueva: %r" % visto
assert ("v" + info["version"]) in visto["texto"], visto["texto"]
print("AVISO OK ->", visto["titulo"], "|", visto["texto"].splitlines()[0])
os._exit(0)
