# -*- coding: utf-8 -*-
# Ajustes de dmgbuild para el DMG de CineSlide (los usa construir-dmg.yml):
#   dmgbuild -s dmg_ajustes.py -D app=<CineSlide.app> -D fondo=<fondo.tiff> -D icono=<volumen.icns> "CineSlide 9.60" x.dmg
# (9.60) Como el de CineCaptions: "Arrástralo a Aplicaciones". CineSlide.app a la izquierda y el acceso "Aplicaciones" (enlace a
# /Applications) a la derecha, centrados donde el fondo deja la flecha: (200, 185) y (460, 185), en puntos (los mismos que
# ICONO_APP / ICONO_APLICACIONES de Construir_Instalador_Mac.py). El fondo mide 660 x 400; la ventana, 28 más por la barra de título.
import os.path

app = defines["app"]  # noqa: F821  (dmgbuild define "defines")
nombre = os.path.basename(app)

format = "ULFO"                 # lzfse: abre rápido (macOS 10.11+)
filesystem = "HFS+"
size = None
files = [app]
symlinks = {"Aplicaciones": "/Applications"}
hide_extension = [nombre]       # "CineSlide", sin ".app"
icon = defines.get("icono")  # noqa: F821
icon_locations = {nombre: (200, 185), "Aplicaciones": (460, 185)}
background = defines["fondo"]  # noqa: F821
show_status_bar = False
show_tab_view = False
show_toolbar = False
show_pathbar = False
show_sidebar = False
sidebar_width = 180
window_rect = ((200, 120), (660, 428))   # 400 del fondo + 28 de la barra de título
default_view = "icon-view"
show_icon_preview = False
include_icon_view_settings = "auto"
include_list_view_settings = "auto"
arrange_by = None
grid_offset = (0, 0)
grid_spacing = 100
scroll_position = (0, 0)
label_pos = "bottom"
text_size = 14
icon_size = 128
