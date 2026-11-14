# -*- coding: utf-8 -*-
# (9.58) Ajustes de dmgbuild para el DMG de CineSlide (los usa construir-dmg.yml):
#   dmgbuild -s dmg_ajustes.py -D app=<Instalar CineSlide.app> -D fondo=<fondo.tiff> -D icono=<volumen.icns> "CineSlide 9.58" x.dmg
# La ventana mide lo mismo que el fondo (660x420, lo dibuja Construir_Instalador_Mac.py) y el icono va donde el fondo deja su aro
# y la píldora del nombre: centrado en (330, 200), de 128 px.
import os.path

app = defines["app"]  # noqa: F821  (dmgbuild define "defines")
nombre = os.path.basename(app)

format = "ULFO"                 # lzfse: abre rápido (macOS 10.11+)
filesystem = "HFS+"
size = None
files = [app]
symlinks = {}
hide_extension = [nombre]       # "Instalar CineSlide", sin ".app"
icon = defines.get("icono")  # noqa: F821
icon_locations = {nombre: (330, 200)}
background = defines["fondo"]  # noqa: F821
show_status_bar = False
show_tab_view = False
show_toolbar = False
show_pathbar = False
show_sidebar = False
sidebar_width = 180
window_rect = ((200, 120), (660, 420))
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
