# -*- coding: utf-8 -*-
"""
BATERÍA DE PRUEBAS de CineSlide en una Mac real (GitHub Actions, bateria-mac.yml). También corre en Windows, sin AVFoundation:

    python bateria_mac.py <carpeta con CineSlide.py> <carpeta de salida> [verificar_av] [--larga=30] [--solo=temas,videos]

Crea varias presentaciones con el motor Express, con los ajustes de fábrica como CREAR VIDEO, y revisa cada MP4 con ffprobe.
En Mac también lo abre con AVFoundation (QuickTime): todos los cuadros, el audio y un cuadro comparado con ffmpeg.
  fotos      JPG de 12 MP girada por EXIF, 48 MP, diminuta, panorámica, vertical, en gris, PNG con transparencia, WEBP, TIFF,
             BMP y HEIC de iPhone (en Mac, hecha con sips)
  videos     video de iPhone (HEVC guardado girado), video HDR de 10 bits (HLG) y MP4 H.264, todos con sonido
  temas      los 8 temas (720p)
  intro      intro + textos (vienen activados) + música MP3
  vertical   formato 9:16 (Reels, TikTok, estados)
  rutas      carpeta y nombres con acentos, espacios, & y emoji
  larga      N fotos de 12 MP: mide el rendimiento
  vista      la vista previa de un tema (la usa la interfaz)
  interfaz   abre la ventana principal (Qt sin pantalla), mide cuánto tarda y guarda una imagen de ella
Mide cada etapa con el registro del motor y deja informe.md e informe.json. Código 1 si algo falla.
La máquina de prueba no tiene licencia: se salta solo esa comprobación (se prueba el motor, no la licencia).
"""
import json
import os
import platform
import struct
import subprocess
import sys
import time
import traceback

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
OPC = dict((a[2:].split("=", 1) + ["1"])[:2] for a in sys.argv[1:] if a.startswith("--"))
CARPETA, SALIDA = os.path.abspath(ARGS[0]), os.path.abspath(ARGS[1])
VERIFICAR_AV = os.path.abspath(ARGS[2]) if len(ARGS) > 2 else None
N_LARGA = int(OPC.get("larga", "30"))
SOLO = set(x for x in OPC.get("solo", "").split(",") if x)
os.makedirs(SALIDA, exist_ok=True)
sys.path.insert(0, CARPETA)
os.chdir(CARPETA)
import CineSlide as c  # noqa: E402

c._lic_exigir = lambda *a, **k: None
REGISTRO = []
_log_original = c._log


def _log(nivel, mensaje, *args):
    """Copia de cada línea del registro del motor (ahí están los tiempos de cada etapa y los avisos)."""
    try:
        REGISTRO.append((nivel, (mensaje % args) if args else str(mensaje)))
    except Exception:
        REGISTRO.append((nivel, str(mensaje)))
    return _log_original(nivel, mensaje, *args)


c._log = _log
MAC = sys.platform == "darwin"
NUEVO = tuple(int(x) for x in c.VERSION_MOTOR.split(".")[:2]) >= (9, 53)
FPS = 30.0
FF = c._ex_ffmpeg()
FP = c._ex_ffprobe(FF)
MAN = c.MANIFEST["variables"]
BASE = dict((x["id"], x["default"]) for x in MAN)
TEMAS = [x for x in MAN if x["id"] == "estilo_diseno"][0]["choices"]
HORIZONTAL, VERTICAL = c.FORMATOS_VIDEO[0], c.FORMATOS_VIDEO[1]
RESULTADOS = []


def correr(orden, **k):
    return subprocess.run(orden, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **k)


def carpeta(nombre):
    d = os.path.join(SALIDA, nombre)
    os.makedirs(d, exist_ok=True)
    return d


# ------------------------------------------------------------------------------------------------ material de prueba
def imagen(destino, fuente, *extra):
    """Crea una imagen con ffmpeg (fuente lavfi). None si este ffmpeg no sabe escribir ese formato."""
    p = correr([FF, "-v", "error", "-y", "-f", "lavfi", "-i", fuente, "-frames:v", "1"] + list(extra) + [destino])
    if p.returncode or not os.path.isfile(destino):
        print("  (no se pudo crear %s: %s)" % (os.path.basename(destino), p.stderr.decode("utf-8", "replace").strip()[-160:]))
        return None
    return destino


def fotos_camara(d, semilla, n, ancho=4032, alto=3024, prefijo="foto"):
    """n fotos distintas 'de cámara' (degradados con grano), JPEG de buena calidad como las de un teléfono."""
    lista = []
    for i in range(n):
        r = imagen(os.path.join(d, "%s_%03d.jpg" % (prefijo, i + 1)),
                   "gradients=s=%dx%d:seed=%d:nb_colors=5,noise=alls=10:allf=t" % (ancho, alto, semilla + i), "-q:v", "3")
        if r:
            lista.append(r)
    return lista


def con_orientacion(ruta, valor):
    """Le pone a un JPEG la etiqueta EXIF Orientation (6 = cámara girada: así guardan muchas fotos verticales)."""
    with open(ruta, "rb") as f:
        datos = f.read()
    ifd = struct.pack(">H", 1) + struct.pack(">HHIHH", 0x0112, 3, 1, valor, 0) + struct.pack(">I", 0)
    exif = b"Exif\x00\x00" + b"MM\x00\x2a" + struct.pack(">I", 8) + ifd
    with open(ruta, "wb") as f:
        f.write(datos[:2] + b"\xff\xe1" + struct.pack(">H", len(exif) + 2) + exif + datos[2:])
    return ruta


def video(destino, fuente, segundos, args_video, rotacion=None):
    """Crea un video con sonido (un tono). rotacion: lo guarda girado, como el iPhone cuando se graba en vertical."""
    tmp = destino + ".tmp" + os.path.splitext(destino)[1]
    p = correr([FF, "-v", "error", "-y", "-f", "lavfi", "-i", fuente, "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=48000",
                "-t", str(segundos)] + list(args_video) + ["-c:a", "aac", "-b:a", "128k", tmp])
    if p.returncode or not os.path.isfile(tmp):
        print("  (no se pudo crear %s: %s)" % (os.path.basename(destino), p.stderr.decode("utf-8", "replace").strip()[-160:]))
        return None
    if rotacion is None:
        os.replace(tmp, destino)
    else:
        tag = ["-tag:v", "hvc1"] if "libx265" in args_video else []
        p = correr([FF, "-v", "error", "-y", "-display_rotation", str(rotacion), "-i", tmp, "-c", "copy"] + tag + [destino])
        os.remove(tmp)
        if p.returncode:
            print("  (no se pudo girar %s: %s)" % (os.path.basename(destino), p.stderr.decode("utf-8", "replace").strip()[-160:]))
            return None
    return destino


def cancion(destino, segundos):
    """Canción de prueba (MP3 si este ffmpeg tiene LAME; si no, M4A)."""
    fuente = "sine=frequency=440:duration=%d,volume=0.4" % segundos
    p = correr([FF, "-v", "error", "-y", "-f", "lavfi", "-i", fuente, "-ac", "2", "-c:a", "libmp3lame", "-b:a", "192k", destino])
    if p.returncode == 0:
        return destino
    destino = os.path.splitext(destino)[0] + ".m4a"
    correr([FF, "-v", "error", "-y", "-f", "lavfi", "-i", fuente, "-ac", "2", "-c:a", "aac", destino], check=True)
    return destino


# ------------------------------------------------------------------------------------------------ revisar un MP4
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
    i = moov.find(b"colrnclx")
    if i < 0:
        return None
    pri, trc, mat = struct.unpack(">HHH", moov[i + 8:i + 14])
    return pri, trc, mat, moov[i + 14] >> 7


def diferencia(bgra, rgb, w, h, paso=4):
    """Diferencia media por canal (R, G, B) entre el cuadro de la Mac (BGRA) y el de ffmpeg (RGB)."""
    n, dif = 0, [0, 0, 0]
    for y in range(0, h, paso):
        fa, fr = y * w * 4, y * w * 3
        for x in range(0, w, paso):
            ia, ir = fa + x * 4, fr + x * 3
            dif[0] += abs(bgra[ia + 2] - rgb[ir])
            dif[1] += abs(bgra[ia + 1] - rgb[ir + 1])
            dif[2] += abs(bgra[ia] - rgb[ir + 2])
            n += 1
    return [d / float(n) for d in dif]


def revisar_mp4(ruta, vertical, con_audio, ancho_alto):
    """Lista de (ok, texto, solo_desde_9.53) con lo que dice ffprobe y, en Mac, AVFoundation."""
    r = []
    j = json.loads(correr([FP, "-v", "error", "-show_streams", "-show_format", "-of", "json", ruta]).stdout.decode("utf-8", "replace") or "{}")
    sv = ([s for s in j.get("streams", []) if s.get("codec_type") == "video"] or [{}])[0]
    sa = ([s for s in j.get("streams", []) if s.get("codec_type") == "audio"] or [{}])[0]
    r.append((bool(sv), "tiene video", False))
    r.append((bool(sa) == con_audio, "audio %s" % ("presente" if sa else "ausente"), False))
    if ancho_alto:
        r.append(((sv.get("width"), sv.get("height")) == ancho_alto, "tamaño %sx%s" % (sv.get("width"), sv.get("height")), False))
    r.append(((sv.get("codec_name"), sv.get("codec_tag_string")) in (("hevc", "hvc1"), ("h264", "avc1")),
              "códec %s/%s" % (sv.get("codec_name"), sv.get("codec_tag_string")), False))
    r.append((sv.get("pix_fmt") == "yuv420p", "píxeles %s" % sv.get("pix_fmt"), True))
    color = (sv.get("color_range"), sv.get("color_space"), sv.get("color_primaries"), sv.get("color_transfer"))
    r.append((color == ("tv", "bt709", "bt709", "bt709"), "color %s/%s/%s/%s" % color, True))
    orden, moov = cajas(ruta)
    r.append((colr(moov) == (1, 1, 1, 0), "átomo colr %s" % (colr(moov),), True))
    r.append(("moov" in orden and "mdat" in orden and orden.index("moov") < orden.index("mdat"), "moov antes de mdat", False))
    dv = float(sv.get("duration") or 0)
    r.append((dv >= 2, "dura %.1f s" % dv, False))
    if sa:
        da = float(sa.get("duration") or 0)
        r.append((abs(dv - da) < 0.2 and sa.get("codec_name") == "aac", "audio %s de %.1f s" % (sa.get("codec_name"), da), False))
    if VERIFICAR_AV and sv:
        r += revisar_en_mac(ruta, sv, dv, float(sa.get("duration") or 0) if sa else 0.0)
    return r, dv


def revisar_en_mac(ruta, sv, dv, da):
    r = []
    dir_cuadros = os.path.splitext(ruta)[0] + "_cuadros"
    os.makedirs(dir_cuadros, exist_ok=True)
    t = round(dv * 0.4 * FPS) / FPS
    orden = [sys.executable, VERIFICAR_AV] if VERIFICAR_AV.endswith(".py") else [VERIFICAR_AV]
    p = correr(orden + [ruta, dir_cuadros, "%.4f" % t], timeout=900)
    lineas = p.stdout.decode("utf-8", "replace").strip().splitlines()
    try:
        m = json.loads(lineas[-1])
    except Exception:
        m = {"error": (p.stderr.decode("utf-8", "replace") or "sin salida")[-300:]}
    r.append((p.returncode == 0 and not m.get("error"), "AVFoundation lo abre %s" % (m.get("error") or ""), False))
    r.append((m.get("reproducible") is True and m.get("decodificable") is True, "la Mac lo da por reproducible", False))
    n = int(sv.get("nb_frames") or 0)
    r.append((m.get("lectura_video") == "completa" and abs(int(m.get("cuadros_decodificados") or 0) - n) <= 1,
              "la Mac decodificó %s de %d cuadros" % (m.get("cuadros_decodificados"), n), False))
    if da:
        sa_mac = float(m.get("audio_muestras") or 0) / float(m.get("audio_hz") or 48000)
        r.append((m.get("lectura_audio") == "completa" and abs(sa_mac - da) < 0.2, "la Mac decodificó %.1f s de audio" % sa_mac, False))
    r.append((m.get("color_709") is True and m.get("rango_completo") is False,
              "la Mac lee el color %s/%s/%s" % (m.get("primarias") or "-", m.get("transferencia") or "-", m.get("matriz") or "-"), True))
    for cu in m.get("cuadros") or []:
        w, h, pts = int(cu["ancho"]), int(cu["alto"]), float(cu["pts"])
        with open(cu["archivo"], "rb") as f:
            bgra = f.read()
        mejor = None
        for corr in (0.0, -1.0, 1.0):
            rgb = correr([FF, "-v", "error", "-ss", "%.4f" % max(0.0, pts + (corr - 0.5) / FPS), "-i", ruta, "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]).stdout
            if len(bgra) == w * h * 4 and len(rgb) == w * h * 3:
                mad = diferencia(bgra, rgb, w, h)
                mejor = mad if mejor is None or max(mad) < max(mejor) else mejor
        r.append((mejor is not None and max(mejor) <= 4.0,
                  "colores Mac = ffmpeg en %.1f s (dif. %s)" % (pts, "/".join("%.1f" % x for x in mejor) if mejor else "?"), True))
    return r


# ------------------------------------------------------------------------------------------------ tiempos del motor
def tiempos(registro, etapas):
    """Tiempos de cada etapa, del registro del motor y de los avisos de progreso."""
    t = {}
    for nivel, m in registro:
        if m.startswith("Express: fotos y ") and " listos en " in m:
            t["fotos_y_tramos_s"] = float(m.split(" listos en ")[1].split(" s")[0])
            t["cuadros_por_s"] = float(m.split("(")[-1].split(" fotogramas")[0])
        elif m.startswith("Express: pasada final (") and " en " in m:
            t["pasada_final_s"] = float(m.rsplit(" en ", 1)[1].split(" s")[0])
        elif m.startswith("Express: motor de composición"):
            t["motor"] = m.split("= ", 1)[-1].rstrip(".")
        elif m.startswith("Express: ") and " tramos en " in m and "codificador de tramos=" in m:
            t["tramos"] = int(m.split("Express: ")[1].split(" tramos")[0])
            t["codificador_tramos"] = m.split("codificador de tramos=")[1].split(";")[0]
        elif m.startswith("Express: tema ") and " procesos x " in m:
            t["procesos"] = m.split("; ")[1].split(" (")[0] if "; " in m else ""
    marcas = {}
    for seg, frac, texto in etapas:
        clave = texto.split(" ")[0]
        marcas.setdefault(clave, seg)
    if "Calculando" in marcas:
        t["preparar_s"] = marcas["Calculando"]
    if "Verificando" in marcas and etapas:
        t["verificar_s"] = round(etapas[-1][0] - marcas["Verificando"], 2)
    return t


# ------------------------------------------------------------------------------------------------ correr un escenario
def escenario(nombre, items, cambios, W=1920, H=1080, musica=None, nombre_video=None, con_audio=None, esperar_todo=True):
    if SOLO and nombre not in SOLO:
        return None
    print("\n" + "=" * 100 + "\n## %s: %d archivos, %dx%d%s" % (nombre, len(items), W, H, " + música" if musica else ""))
    v = dict(BASE)
    v.update({"formato_video": VERTICAL if H > W else HORIZONTAL, "express_resolucion": "%dp" % min(W, H),
              "carpeta_exportacion": carpeta(nombre)})
    v.update(cambios)
    del REGISTRO[:]
    etapas, t0 = [], time.time()
    res = {"escenario": nombre, "archivos": len(items), "formato": "%dx%d" % (W, H), "ok": False, "fallas": []}
    try:
        r = c.crear_presentacion_express(list(items), v, W, H, FPS, musica=dict(musica) if musica else None,
                                         carpeta_salida=carpeta(nombre), nombre=nombre_video or nombre,
                                         al_progresar=lambda f, tx: etapas.append((round(time.time() - t0, 2), round(f, 3), tx)))
    except Exception as e:
        traceback.print_exc()
        res.update(segundos=round(time.time() - t0, 1), error="%s: %s" % (type(e).__name__, str(e)[:400]))
        res["fallas"].append(res["error"])
        res["avisos_motor"] = [m for n, m in REGISTRO if n in ("WARN", "WARNING", "ERROR")][:12]
        RESULTADOS.append(res)
        print("  FALLA %s" % res["error"])
        return res
    res["segundos"] = round(time.time() - t0, 1)
    res["video"] = os.path.basename(r["ruta"])
    res["mb"] = round(os.path.getsize(r["ruta"]) / 1048576.0, 1)
    res["codificador"] = r.get("codificador")
    res["omitidos"] = [os.path.basename(str(x)) for x in (r.get("omitidos") or [])]
    res["tiempos"] = tiempos(REGISTRO, etapas)
    res["avisos_motor"] = [m for n, m in REGISTRO if n in ("WARN", "WARNING", "ERROR")][:12]
    if con_audio is None:
        con_audio = bool(musica) or any(es_video for _r, es_video in items)
    comprobaciones, dv = revisar_mp4(r["ruta"], H > W, con_audio, (W, H))
    if esperar_todo and res["omitidos"]:
        comprobaciones.append((False, "no se pudieron usar: %s" % ", ".join(res["omitidos"]), False))
    res["duracion_video"] = round(dv, 1)
    for ok, texto, desde_953 in comprobaciones:
        if ok:
            print("  OK    " + texto)
        elif desde_953 and not NUEVO:
            print("  AVISO " + texto + "  (cambio de 9.53)")
        else:
            print("  FALLA " + texto)
            res["fallas"].append(texto)
    for a in res["avisos_motor"]:
        print("  aviso del motor: " + a[:200])
    res["ok"] = not res["fallas"]
    print("  %s en %.1f s (%.1f s de video; %s)" % (res["video"], res["segundos"], dv, json.dumps(res["tiempos"], ensure_ascii=False)))
    RESULTADOS.append(res)
    return res


def sistema():
    info = {"cineslide": c.VERSION_MOTOR, "so": "%s %s" % (platform.system(), platform.mac_ver()[0] or platform.release()),
            "maquina": platform.machine(), "nucleos": os.cpu_count()}
    if MAC:
        info["cpu"] = correr(["sysctl", "-n", "machdep.cpu.brand_string"]).stdout.decode().strip()
        try:
            info["ram_gb"] = round(int(correr(["sysctl", "-n", "hw.memsize"]).stdout.decode().strip()) / 1073741824.0, 1)
        except Exception:
            pass
    else:
        info["cpu"] = platform.processor()
    info["ffmpeg"] = correr([FF, "-version"]).stdout.decode("utf-8", "replace").splitlines()[0][:80]
    return info


def informe(info, total_s):
    filas = ["| Escenario | Resultado | Video | Tiempo | Velocidad | Fotos y tramos | Pasada final | Codificador | Motor |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in RESULTADOS:
        t = r.get("tiempos") or {}
        vel = ("%.2fx" % (r["duracion_video"] / r["segundos"])) if r.get("duracion_video") and r.get("segundos") else "-"
        filas.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["escenario"], "OK" if r["ok"] else "**FALLA**", ("%.1f s" % r["duracion_video"]) if r.get("duracion_video") else "-",
            ("%.1f s" % r["segundos"]) if r.get("segundos") is not None else "-", vel,
            ("%.1f s" % t["fotos_y_tramos_s"]) if "fotos_y_tramos_s" in t else "-",
            ("%.1f s" % t["pasada_final_s"]) if "pasada_final_s" in t else "-",
            r.get("codificador") or t.get("codificador_tramos") or "-", t.get("motor", "-")))
    lineas = ["# Batería CineSlide %s · %s" % (info["cineslide"], info["so"]), "",
              "%s · %s núcleos%s · %s" % (info.get("cpu") or info["maquina"], info["nucleos"],
                                          (" · %s GB" % info["ram_gb"]) if info.get("ram_gb") else "", info["ffmpeg"]),
              "", "Total: %.0f s · %d escenarios · %d con fallas" % (total_s, len(RESULTADOS), sum(1 for r in RESULTADOS if not r["ok"])),
              ""] + filas
    for r in RESULTADOS:
        if r["fallas"] or r.get("avisos_motor"):
            lineas += ["", "### %s" % r["escenario"]] + ["- FALLA: %s" % f for f in r["fallas"]] + \
                      ["- aviso del motor: %s" % a[:300] for a in r.get("avisos_motor") or []]
    texto = "\n".join(lineas) + "\n"
    with open(os.path.join(SALIDA, "informe.md"), "w", encoding="utf-8") as f:
        f.write(texto)
    with open(os.path.join(SALIDA, "informe.json"), "w", encoding="utf-8") as f:
        json.dump({"sistema": info, "total_s": round(total_s, 1), "escenarios": RESULTADOS}, f, ensure_ascii=False, indent=1)
    return texto


# ------------------------------------------------------------------------------------------------ escenarios
T_INICIO = time.time()
INFO = sistema()
print("CineSlide %s | %s | %s" % (c.VERSION_MOTOR, INFO["so"], INFO.get("cpu")))
MAT = carpeta("material")
POZO = fotos_camara(MAT, 1, 8)
MP3 = cancion(os.path.join(MAT, "cancion.mp3"), 40)
CORTOS = {"t_segundos_por_foto": 2.0, "t1_segundos_por_foto": 2.0}

if not SOLO or "fotos" in SOLO:
    d = carpeta("material_fotos")
    variadas = [con_orientacion(fotos_camara(d, 50, 1, prefijo="girada_exif")[0], 6)]
    variadas += [imagen(os.path.join(d, "enorme_48mp.jpg"), "gradients=s=8064x6048:seed=51", "-q:v", "4"),
                 imagen(os.path.join(d, "diminuta.jpg"), "testsrc2=s=320x240"),
                 imagen(os.path.join(d, "panoramica.jpg"), "gradients=s=6000x1500:seed=52", "-q:v", "3"),
                 fotos_camara(d, 53, 1, 3024, 4032, prefijo="vertical")[0],
                 imagen(os.path.join(d, "gris.jpg"), "testsrc2=s=1600x1200,format=gray", "-pix_fmt", "gray"),
                 imagen(os.path.join(d, "transparente.png"), "testsrc2=s=1600x1200,format=rgba,colorchannelmixer=aa=0.6"),
                 imagen(os.path.join(d, "foto.webp"), "smptehdbars=s=1600x1200", "-c:v", "libwebp", "-quality", "85"),
                 imagen(os.path.join(d, "foto.tif"), "testsrc2=s=1600x1200"),
                 imagen(os.path.join(d, "foto.bmp"), "testsrc2=s=800x600")]
    if MAC:
        heic = os.path.join(d, "iphone.heic")
        correr(["sips", "-s", "format", "heic", POZO[0], "--out", heic])
        variadas.append(heic if os.path.isfile(heic) else None)
    escenario("fotos", [(x, False) for x in variadas if x], CORTOS)

if not SOLO or "videos" in SOLO:
    d = carpeta("material_videos")
    x265 = ["-c:v", "libx265", "-preset", "ultrafast", "-x265-params", "log-level=error"]
    clips = [video(os.path.join(d, "iphone_vertical.mov"), "testsrc2=s=1920x1080:r=30", 4, x265 + ["-pix_fmt", "yuv420p"], rotacion=90),
             video(os.path.join(d, "iphone_hdr_hlg.mov"), "testsrc2=s=1920x1080:r=30", 3,
                   x265 + ["-pix_fmt", "yuv420p10le", "-color_primaries", "bt2020", "-color_trc", "arib-std-b67", "-colorspace", "bt2020nc",
                           "-tag:v", "hvc1"]),
             video(os.path.join(d, "camara_h264.mp4"), "testsrc2=s=1280x720:r=30", 3,
                   ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"])]
    items = [(POZO[1], False), (clips[0], True), (POZO[2], False), (clips[1], True), (clips[2], True), (POZO[3], False)]
    escenario("videos", [x for x in items if x[0]], CORTOS)

if not SOLO or "temas" in SOLO:
    for i, tema in enumerate(TEMAS):
        cambios = dict(CORTOS, estilo_diseno=tema)
        escenario("tema_%d" % (i + 1), [(f, False) for f in POZO[i % 4:i % 4 + 4]], cambios, 1280, 720)

if not SOLO or "intro" in SOLO:
    for estilo in (c.INTRO_ESTILOS[0], c.INTRO_ESTILOS[-1]):
        escenario("intro_%s" % estilo.split(" ")[0].lower(), [(f, False) for f in POZO[:6]],
                  dict(CORTOS, intro_activar=True, intro_estilo=estilo, intro_titulo="Ana & Luis"), musica={"ruta": MP3, "lista": [MP3]})

if not SOLO or "vertical" in SOLO:
    escenario("vertical", [(f, False) for f in POZO[2:8]], CORTOS, 1080, 1920, musica={"ruta": MP3, "lista": [MP3]})

if not SOLO or "rutas" in SOLO:
    d = carpeta("Fotos de Mamá & Papá 😊 (2026)")
    raras = []
    for i, nombre in enumerate(["foto número 1 (copia).jpg", "Ñandú – atardecer.jpg", "año nuevo #2 '25.jpg"]):
        destino = os.path.join(d, nombre)
        with open(POZO[i], "rb") as fo, open(destino, "wb") as fd:
            fd.write(fo.read())
        raras.append((destino, False))
    res = escenario("rutas", raras, CORTOS, nombre_video="Boda de María José – 15 años 💍")
    if res and res.get("video") and "María José" not in res["video"]:
        res["fallas"].append("el nombre del video perdió los acentos: %s" % res["video"])
        res["ok"] = False

if not SOLO or "larga" in SOLO:
    d = carpeta("material_larga")
    escenario("larga", [(f, False) for f in fotos_camara(d, 1000, N_LARGA)],
              {"t_segundos_por_foto": 3.0, "t1_segundos_por_foto": 3.0}, musica={"ruta": MP3, "lista": [MP3]})

if not SOLO or "vista" in SOLO:
    print("\n" + "=" * 100 + "\n## vista (vista previa de un tema, la usa la interfaz)")
    t0 = time.time()
    res = {"escenario": "vista_previa", "archivos": 4, "formato": "%dx%d" % (c.VISTA_ANCHO, c.VISTA_ALTO), "ok": False, "fallas": []}
    try:
        n = c.generar_vista_previa(3, POZO[:4], carpeta("vista"), segundos=6, imprimir=lambda *a: None)
        res.update(ok=bool(n), cuadros=n)
        if not n:
            res["fallas"].append("la vista previa no dejó cuadros")
    except Exception as e:
        traceback.print_exc()
        res["fallas"].append("%s: %s" % (type(e).__name__, str(e)[:300]))
    res["segundos"] = round(time.time() - t0, 1)
    print("  %s: %s cuadros en %.1f s %s" % ("OK" if res["ok"] else "FALLA", res.get("cuadros"), res["segundos"], res["fallas"]))
    RESULTADOS.append(res)

if not SOLO or "interfaz" in SOLO:
    print("\n" + "=" * 100 + "\n## interfaz (ventana principal sin pantalla)")
    t0 = time.time()
    res = {"escenario": "interfaz", "archivos": 0, "formato": "-", "ok": False, "fallas": []}
    try:                                   # como la app real: QEventLoop hasta 'cerrada'; se cierra como con el botón
        from PySide6 import QtCore, QtWidgets
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["CineSlide"])
        Ventana = c._crear_clases_qt()
        ventana = Ventana(c._ProxyPrincipal())
        ventana.resize(1400, 900)
        bucle = QtCore.QEventLoop()
        ventana.cerrada.connect(bucle.quit)
        ventana.show()
        app.processEvents()
        res["abrir_s"] = round(time.time() - t0, 2)

        def capturar_y_cerrar():
            ventana.grab().save(os.path.join(SALIDA, "interfaz.png"))
            ventana.close()
        QtCore.QTimer.singleShot(1500, capturar_y_cerrar)
        QtCore.QTimer.singleShot(30000, bucle.quit)                     # por si no se cerrara
        bucle.exec()
        res["ok"] = os.path.isfile(os.path.join(SALIDA, "interfaz.png"))
        if not res["ok"]:
            res["fallas"].append("la ventana no se pudo dibujar ni cerrar")
    except Exception as e:
        traceback.print_exc()
        res["fallas"].append("%s: %s" % (type(e).__name__, str(e)[:300]))
    res["segundos"] = round(time.time() - t0, 1)
    print("  %s: ventana en %s s %s" % ("OK" if res["ok"] else "FALLA", res.get("abrir_s"), res["fallas"]))
    RESULTADOS.append(res)

texto = informe(INFO, time.time() - T_INICIO)
print("\n" + texto)
sys.stdout.flush()
CODIGO = 0 if all(r["ok"] for r in RESULTADOS) else 1
# Salida normal (como la app): os._exit con Qt abierto se caía en Windows al descargar Qt (0xC0000005). El vigía corta
# solo si algún hilo del motor no dejara terminar.
import threading  # noqa: E402
_vigia = threading.Timer(60, os._exit, args=(CODIGO,))
_vigia.daemon = True
_vigia.start()
sys.exit(CODIGO)
