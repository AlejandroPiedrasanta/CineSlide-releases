#!/bin/bash
# (9.76) MEDIR CineSlide en una Mac REAL (con su GPU), sin tocar tus fotos, tus videos ni tus ajustes.
# En la Mac, abre Terminal y pega:
#   curl -fsSL https://raw.githubusercontent.com/AlejandroPiedrasanta/CineSlide-releases/main/medir_mac.sh | bash
# Usa el CineSlide ya instalado, crea fotos de prueba y datos APARTE (carpeta temporal), mide un video de 60 fotos, los 8 temas
# y la intro, y abre el informe. Tarda ~5-10 min. Al final, copia el resumen que sale aquí y mándalo.
set -u
DIR="$HOME/Library/Application Support/CineSlide"
PY="$DIR/python/bin/python3"
if [ ! -x "$PY" ] || [ ! -f "$DIR/CineSlide.py" ]; then
  echo "No encuentro CineSlide instalado en esta Mac ($DIR). Instálalo primero."; exit 1
fi
TMP="$(mktemp -d /tmp/cineslide_medir.XXXXXX)"
cd "$TMP" || exit 1
echo "CineSlide $(grep -m1 '^VERSION_MOTOR' "$DIR/CineSlide.py" | cut -d'"' -f2) · $(sw_vers -productVersion) · $(sysctl -n machdep.cpu.brand_string)"
echo "Bajando la batería de pruebas..."
curl -fsSL -o bateria_mac.py https://raw.githubusercontent.com/AlejandroPiedrasanta/CineSlide-releases/main/bateria_mac.py || {
  echo "No se pudo bajar la batería (¿sin internet?)."; exit 1; }
echo "Midiendo (no cierres esta ventana)..."
CINESLIDE_DATOS="$TMP/datos" QT_QPA_PLATFORM=offscreen "$PY" -u bateria_mac.py "$DIR" "$TMP/salida" \
  --solo=larga,temas,intro --larga=60 > "$TMP/registro.txt" 2>&1
codigo=$?
echo
echo "================ RESUMEN (cópialo y mándalo) ================"
grep -E "^\| |^Total:" "$TMP/salida/informe.md" 2>/dev/null || tail -30 "$TMP/registro.txt"
grep -m3 -E "motor de composición|DISPONIBLE|NO DISPONIBLE" "$TMP/datos/logs/motor.log" 2>/dev/null | cut -c25-200
echo "=============================================================="
[ $codigo -eq 0 ] && echo "Todo bien." || echo "Algo falló: el detalle está en $TMP/registro.txt"
open "$TMP/salida/informe.md" 2>/dev/null
