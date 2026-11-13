# -*- coding: utf-8 -*-
"""
Prueba del VIDEO FINAL en una Mac real (GitHub Actions; en Windows corre igual, sin la parte de AVFoundation):

    python probar_video_mac.py <carpeta con CineSlide.py> <carpeta de salida> [verificar_av]

1) Crea 3 fotos JPEG de prueba (barras de color y patrones, en rango completo como las de una cámara) y una canción de 14 s.
2) Hace la presentación con el motor Express, como CREAR VIDEO con "Los dos (horizontal y vertical)", intro y música.
3) Revisa cada MP4 con ffprobe: nombre con _horizontal / _vertical, HEVC 'hvc1' (o H.264 'avc1') 4:2:0 de 8 bits, color
   BT.709 rango de TV con átomo 'colr', AAC 48 kHz estéreo tan largo como el video y 'moov' antes de 'mdat'.
4) Con verificar_av (AVFoundation: lo que usan QuickTime, Fotos y Safari): la Mac lo da por reproducible, decodifica TODOS
   los cuadros y el audio, lee el color BT.709 y ve los mismos colores que ffmpeg en dos cuadros (intro y fotos).
Lo nuevo de 9.53 (nombre y color) en versiones anteriores sale como AVISO, no como FALLA. La máquina de prueba no tiene
licencia: se salta solo esa comprobación (se prueba el motor, no la licencia).
"""
import json
import os
import struct
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
carpeta = os.path.abspath(sys.argv[1])
salida = os.path.abspath(sys.argv[2])
verificar_av = os.path.abspath(sys.argv[3]) if len(sys.argv) > 3 else None
os.makedirs(salida, exist_ok=True)
sys.path.insert(0, carpeta)
os.chdir(carpeta)
import CineSlide as c  # noqa: E402

c._lic_exigir = lambda *a, **k: None
NUEVO = tuple(int(x) for x in c.VERSION_MOTOR.split(".")[:2]) >= (9, 53)
FPS = 30.0
ff = c._ex_ffmpeg()
fp = c._ex_ffprobe(ff)
fallas = []


def revisar(ok, texto, desde_953=False):
    if ok:
        print("  OK    " + texto)
    elif desde_953 and not NUEVO:
        print("  AVISO " + texto + "   (cambio de 9.53; esta es la %s)" % c.VERSION_MOTOR)
    else:
        print("  FALLA " + texto)
        fallas.append(texto)


def correr(orden, **k):
    return subprocess.run(orden, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **k)


def cajas(ruta):
    """Orden de las cajas de primer nivel del MP4 y el contenido de 'moov'."""
    orden, moov = [], b""
    with open(ruta, "rb") as h:
        while True:
            cab = h.read(8)
            if len(cab) < 8:
                break
            tam, tipo = struct.unpack(">I4s", cab)
            resto = tam - 8
            if tam == 1:
                resto = struct.unpack(">Q", h.read(8))[0] - 16
            orden.append(tipo.decode("latin-1"))
            if tipo == b"moov":
                moov = h.read(resto)
            elif tam == 0:
                break
            else:
                h.seek(resto, 1)
    return orden, moov


def colr(moov):
    """(primarias, transferencia, matriz, rango completo) del átomo 'colr' nclx; None si no hay."""
    i = moov.find(b"colrnclx")
    if i < 0:
        return None
    pri, trc, mat = struct.unpack(">HHH", moov[i + 8:i + 14])
    return pri, trc, mat, moov[i + 14] >> 7


def diferencia(bgra, rgb, w, h, paso=4):
    """Diferencia media por canal (R, G, B) entre el cuadro de la Mac (BGRA) y el de ffmpeg (RGB), y el sesgo (Mac - ffmpeg)."""
    n, dif, s_mac, s_ff = 0, [0, 0, 0], [0, 0, 0], [0, 0, 0]
    for y in range(0, h, paso):
        fa, fr = y * w * 4, y * w * 3
        for x in range(0, w, paso):
            ia, ir = fa + x * 4, fr + x * 3
            for k, ka in ((0, 2), (1, 1), (2, 0)):
                m, f = bgra[ia + ka], rgb[ir + k]
                dif[k] += abs(m - f)
                s_mac[k] += m
                s_ff[k] += f
            n += 1
    return [d / float(n) for d in dif], [(s_mac[k] - s_ff[k]) / float(n) for k in range(3)]


def revisar_en_mac(ruta, sv, dv, da):
    """Abre el MP4 con AVFoundation (verificar_av) y compara dos cuadros con los de ffmpeg."""
    dir_cuadros = os.path.splitext(ruta)[0] + "_cuadros"
    os.makedirs(dir_cuadros, exist_ok=True)
    tiempos = [1.5, round(dv * 0.75 * FPS) / FPS]                  # uno en la intro y otro en las fotos
    orden = [sys.executable, verificar_av] if verificar_av.endswith(".py") else [verificar_av]
    p = correr(orden + [ruta, dir_cuadros] + ["%.4f" % t for t in tiempos], timeout=900)
    lineas = p.stdout.decode("utf-8", "replace").strip().splitlines()
    try:
        m = json.loads(lineas[-1])
    except Exception:
        m = {}
    print("  AVFoundation: " + json.dumps(dict((k, v) for k, v in m.items() if k != "cuadros"), ensure_ascii=False, sort_keys=True))
    if p.returncode != 0 and p.stderr:
        print("  " + p.stderr.decode("utf-8", "replace")[-800:])
    revisar(p.returncode == 0 and not m.get("error"), "AVFoundation lo abrió sin errores %s" % (m.get("error") or ""))
    revisar(m.get("reproducible") is True and m.get("decodificable") is True, "la Mac lo da por reproducible y decodificable")
    n = int(sv.get("nb_frames") or 0)
    revisar(m.get("lectura_video") == "completa" and abs(int(m.get("cuadros_decodificados") or 0) - n) <= 1,
            "la Mac decodificó %s de %d cuadros (%s)" % (m.get("cuadros_decodificados"), n, m.get("lectura_video")))
    sa = float(m.get("audio_muestras") or 0) / float(m.get("audio_hz") or 48000)
    revisar(m.get("lectura_audio") == "completa" and abs(sa - da) < 0.15,
            "la Mac decodificó %.2f s de audio %s (%s)" % (sa, m.get("audio_codec"), m.get("lectura_audio")))
    revisar(m.get("codec") in ("hvc1", "avc1"), "la Mac lo lee como '%s'" % m.get("codec"))
    revisar(m.get("color_709") is True and m.get("rango_completo") is False,
            "la Mac lee el color: primarias %s, transferencia %s, matriz %s, rango completo %s" % (
                m.get("primarias") or "-", m.get("transferencia") or "-", m.get("matriz") or "-", m.get("rango_completo")), True)
    for cu in m.get("cuadros") or []:
        w, h, pts = int(cu["ancho"]), int(cu["alto"]), float(cu["pts"])
        with open(cu["archivo"], "rb") as f:
            bgra = f.read()
        mejor = None
        for corrimiento in (0.0, -1.0, 1.0):                         # por si un lector cuenta un cuadro distinto
            ss = max(0.0, pts + (corrimiento - 0.5) / FPS)
            rgb = correr([ff, "-v", "error", "-ss", "%.4f" % ss, "-i", ruta, "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24",
                          "-"]).stdout
            if len(bgra) != w * h * 4 or len(rgb) != w * h * 3:
                continue
            mad, sesgo = diferencia(bgra, rgb, w, h)
            if mejor is None or max(mad) < max(mejor[0]):
                mejor = (mad, sesgo)
        if mejor is None:
            revisar(False, "cuadro de %.2f s: no se pudo comparar (%d bytes de la Mac para %dx%d)" % (pts, len(bgra), w, h))
            continue
        mad, sesgo = mejor
        revisar(max(mad) <= 4.0 and max(abs(x) for x in sesgo) <= 3.0,
                "cuadro de %.2f s: la Mac ve los mismos colores que ffmpeg (diferencia R/G/B %.1f/%.1f/%.1f, sesgo %+.1f/%+.1f/%+.1f)"
                % (pts, mad[0], mad[1], mad[2], sesgo[0], sesgo[1], sesgo[2]), True)


print("CineSlide %s | %s | %s" % (c.VERSION_MOTOR, sys.platform, ff))
fotos = []
for i, fuente in enumerate(["smptehdbars=s=1920x1080", "testsrc2=s=1600x1200", "smptebars=s=1080x1440"]):
    ruta_foto = os.path.join(salida, "foto_%d.jpg" % (i + 1))
    correr([ff, "-v", "error", "-y", "-f", "lavfi", "-i", fuente, "-frames:v", "1", "-q:v", "2", ruta_foto], check=True)
    fotos.append((ruta_foto, False))
cancion = os.path.join(salida, "cancion.m4a")
correr([ff, "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=14", "-ac", "2", "-c:a", "aac", cancion], check=True)
musica = {"ruta": cancion, "lista": [cancion]}
v = {"formato_video": c.FORMATOS_VIDEO[2], "t1_segundos_por_foto": 2.0, "t_segundos_por_foto": 2.0, "intro_activar": True,
     "express_resolucion": "1080p", "carpeta_exportacion": salida}

videos = []
for W, H, sufijo in c.formatos_de_video(v):
    r = c.crear_presentacion_express(list(fotos), dict(v), W, H, FPS, musica=dict(musica), carpeta_salida=salida,
                                     nombre="Presentacion" + sufijo)
    print("VIDEO %s | %s | %.1f s" % (os.path.basename(r["ruta"]), r.get("codificador"), float(r.get("segundos") or 0)))
    videos.append((r["ruta"], H > W))

for ruta, vertical in videos:
    nombre = os.path.basename(ruta)
    print("\n== %s (%s)" % (nombre, "vertical" if vertical else "horizontal"))
    j = json.loads(correr([fp, "-v", "error", "-show_streams", "-show_format", "-of", "json", ruta]).stdout.decode("utf-8", "replace"))
    sv = ([s for s in j.get("streams", []) if s.get("codec_type") == "video"] or [{}])[0]
    sa = ([s for s in j.get("streams", []) if s.get("codec_type") == "audio"] or [{}])[0]
    revisar(bool(sv) and bool(sa), "tiene video y audio")
    revisar(("_vertical" if vertical else "_horizontal") in nombre, "el nombre dice la orientación", True)
    ancho, alto = (1080, 1920) if vertical else (1920, 1080)
    revisar((sv.get("width"), sv.get("height")) == (ancho, alto), "tamaño %sx%s" % (sv.get("width"), sv.get("height")))
    cod, tag = sv.get("codec_name"), sv.get("codec_tag_string")
    revisar((cod, tag) in (("hevc", "hvc1"), ("h264", "avc1")), "códec %s con etiqueta '%s' (QuickTime pide hvc1 o avc1)" % (cod, tag))
    revisar(sv.get("profile") in ("Main", "High", "Constrained Baseline", "Baseline"), "perfil %s (8 bits)" % sv.get("profile"))
    revisar(sv.get("pix_fmt") == "yuv420p", "píxeles %s" % sv.get("pix_fmt"), True)
    color = (sv.get("color_range"), sv.get("color_space"), sv.get("color_primaries"), sv.get("color_transfer"))
    revisar(color == ("tv", "bt709", "bt709", "bt709"), "color del video: rango %s, matriz %s, primarias %s, transferencia %s" % color,
            True)
    orden, moov = cajas(ruta)
    revisar(colr(moov) == (1, 1, 1, 0), "átomo colr del MP4: %s (BT.709 en rango de TV = (1, 1, 1, 0))" % (colr(moov),), True)
    revisar("moov" in orden and "mdat" in orden and orden.index("moov") < orden.index("mdat"),
            "moov antes de mdat, empieza a reproducir enseguida: %s" % orden)
    revisar(sv.get("r_frame_rate") == "30/1", "%s cuadros por segundo" % sv.get("r_frame_rate"))
    dv, da = float(sv.get("duration") or 0), float(sa.get("duration") or 0)
    revisar(dv > 5, "dura %.2f s" % dv)
    revisar((sa.get("codec_name"), sa.get("profile"), sa.get("sample_rate"), sa.get("channels")) == ("aac", "LC", "48000", 2),
            "audio %s %s %s Hz %s canales" % (sa.get("codec_name"), sa.get("profile"), sa.get("sample_rate"), sa.get("channels")))
    revisar(abs(dv - da) < 0.15, "audio de %.2f s para %.2f s de video" % (da, dv))
    if verificar_av:
        revisar_en_mac(ruta, sv, dv, da)

print("")
if fallas:
    print("FALLAS (%d):" % len(fallas))
    for f in fallas:
        print("  - " + f)
else:
    print("TODO OK: %d videos (%s)" % (len(videos), "con AVFoundation" if verificar_av else "sin AVFoundation: no es una Mac"))
sys.stdout.flush()
os._exit(1 if fallas else 0)
