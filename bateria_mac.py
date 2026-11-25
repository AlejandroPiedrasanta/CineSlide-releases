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
N_MUCHAS = int(OPC.get("muchas", "60"))
SOLO = set(x for x in OPC.get("solo", "").split(",") if x)
os.makedirs(SALIDA, exist_ok=True)
sys.path.insert(0, CARPETA)
os.chdir(CARPETA)
import CineSlide as c  # noqa: E402

CREAR_EXPRESS = c.crear_presentacion_express          # el original (algún escenario lo envuelve un rato)
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
ESTADO = {"escenario": None, "desde": 0.0}
LIMITE_MIN = float(OPC.get("limite", "25"))          # un escenario que pase de esto se da por colgado (y se corta la batería)


def empezar(nombre):
    ESTADO.update(escenario=nombre, desde=time.time())


def anotar(res):
    """Guarda el resultado y reescribe el informe YA: si algo se cuelga después, lo hecho no se pierde."""
    ESTADO.update(escenario=None)
    RESULTADOS.append(res)
    try:
        informe(INFO, time.time() - T_INICIO)
    except Exception as e:
        print("  (no se pudo escribir el informe: %s)" % e)


def _vigia_escenarios():
    import threading
    def mirar():
        while True:
            time.sleep(10)
            nombre, desde = ESTADO["escenario"], ESTADO["desde"]
            if nombre and time.time() - desde > LIMITE_MIN * 60:
                anotar({"escenario": nombre, "archivos": 0, "formato": "-", "ok": False, "segundos": round(time.time() - desde, 1),
                        "fallas": ["se colgó: más de %.0f min sin terminar" % LIMITE_MIN]})
                print("\nFALLA: '%s' se colgó (más de %.0f min); se corta la batería." % (nombre, LIMITE_MIN))
                sys.stdout.flush()
                os._exit(1)
    threading.Thread(target=mirar, daemon=True).start()


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


def audio_m4a(destino, segundos, hz=550):
    """Canción corta en M4A (AAC), como las que se compran o bajan del teléfono."""
    correr([FF, "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=%d:duration=%d,volume=0.4" % (hz, segundos), "-ac", "2",
            "-c:a", "aac", destino], check=True)
    return destino


def jpeg_progresivo(origen, destino):
    """JPEG progresivo (así guardan muchas webs y algunos programas): lo escribe Qt, que sí sabe hacerlo."""
    try:
        from PySide6.QtGui import QImage, QImageWriter
        img = QImage(origen)
        w = QImageWriter(destino, b"jpg")
        w.setProgressiveScanWrite(True)
        w.setQuality(88)
        return destino if (not img.isNull() and w.write(img)) else None
    except Exception as e:
        print("  (no se pudo crear el JPEG progresivo: %s)" % e)
        return None


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
    # se decodifica TODO (video y audio): cualquier error de flujo sale aquí, en todos los sistemas
    errores = correr([FF, "-v", "error", "-i", ruta, "-map", "0", "-f", "null", "-"]).stderr.decode("utf-8", "replace").strip()
    r.append((not errores, "ffmpeg lo decodifica completo sin errores%s" % ((": " + errores.splitlines()[0][:160]) if errores else ""), False))
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
    empezar(nombre)
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
        anotar(res)
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
    anotar(res)
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
_vigia_escenarios()
print("CineSlide %s | %s | %s" % (c.VERSION_MOTOR, INFO["so"], INFO.get("cpu")))
MAT = carpeta("material")
POZO = fotos_camara(MAT, 1, 8)
MP3 = cancion(os.path.join(MAT, "cancion.mp3"), 40)
CORTOS = {"t_segundos_por_foto": 2.0, "t1_segundos_por_foto": 2.0}

if "precalentar" in OPC:      # como recién instalado: caché de plantillas vacía + lo que prepara el instalador (y cuánto tarda)
    print("\n" + "=" * 100 + "\n## precalentar (paso 7/7 del instalador, con la caché de plantillas vacía)")
    _plantillas = carpeta("plantillas_nuevas")
    c._ex_carpeta_plantillas = lambda: _plantillas
    empezar("precalentar")
    t0 = time.time()
    res = {"escenario": "precalentar", "archivos": 0, "formato": str(getattr(c, "PRECALENTAR_FORMATOS", "5 formatos")), "ok": False,
           "fallas": []}
    try:
        res["archivos"] = c.precalentar_express(imprimir=lambda *a: None)
        res["ok"] = True
    except Exception as e:
        traceback.print_exc()
        res["fallas"].append("%s: %s" % (type(e).__name__, str(e)[:300]))
    res["segundos"] = round(time.time() - t0, 1)
    print("  %s: %d plantillas en %.1f s %s" % ("OK" if res["ok"] else "FALLA", res["archivos"], res["segundos"], res["fallas"]))
    anotar(res)

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

if not SOLO or "fps" in SOLO:                         # (9.55) 24 y 60 fps ya no se preparan al instalar: se arman al usarlas
    for txt_fps in ("60", "24"):
        escenario("fps_" + txt_fps, [(f, False) for f in POZO[:4]], dict(CORTOS, express_fps=txt_fps), 1280, 720)

if not SOLO or "los_dos" in SOLO:                     # "Los dos (horizontal y vertical)": dos MP4 seguidos, como CREAR VIDEO
    v_dos = dict(CORTOS, formato_video=c.FORMATOS_VIDEO[2])
    for W_, H_, suf in c.formatos_de_video(v_dos):
        escenario("los_dos" + (suf or "_horizontal"), [(f, False) for f in POZO[:3]], dict(v_dos), W_, H_,
                  nombre_video="Presentacion" + suf)

if not SOLO or "h264" in SOLO:
    escenario("h264", [(f, False) for f in POZO[:3]], dict(CORTOS, codec_exportacion="H.264"))

if not SOLO or "danadas" in SOLO:                     # una cortada, una que no es foto y una vacía: se saltan, el video sale
    d = carpeta("material_danadas")
    cortada, falsa, vacia = (os.path.join(d, n) for n in ("cortada.jpg", "no_es_una_foto.jpg", "vacia.jpg"))
    with open(POZO[1], "rb") as fo, open(cortada, "wb") as fd:
        fd.write(fo.read()[:30000])
    with open(falsa, "w", encoding="utf-8") as fd:
        fd.write("esto no es una foto")
    open(vacia, "wb").close()
    res = escenario("danadas", [(POZO[0], False), (cortada, False), (falsa, False), (vacia, False), (POZO[2], False)], CORTOS,
                    esperar_todo=False)
    if res and res.get("ok") and not {"no_es_una_foto.jpg", "vacia.jpg"} <= set(res.get("omitidos") or []):
        print("  AVISO el motor no listó como omitidas la foto falsa y la vacía: %s" % res.get("omitidos"))

if not SOLO or "musica" in SOLO:                      # dos canciones más cortas que el video: se encadenan y se repiten
    a1 = audio_m4a(os.path.join(MAT, "cancion_a.m4a"), 6, 440)
    a2 = cancion(os.path.join(MAT, "cancion_b.mp3"), 5)
    escenario("musica_lista", [(f, False) for f in POZO[:8]], CORTOS,
              musica={"ruta": a1, "lista": [a1, a2], "repetir": True, "fundido_entrada": 1.0, "fundido_salida": 2.0})

if not SOLO or "formatos2" in SOLO:                   # PNG de 16 bits y JPEG progresivo
    d = carpeta("material_formatos2")
    extra = [imagen(os.path.join(d, "foto_16bits.png"), "testsrc2=s=1600x1200,format=rgb48be", "-pix_fmt", "rgb48be"),
             jpeg_progresivo(POZO[3], os.path.join(d, "progresiva.jpg")), POZO[4]]
    escenario("formatos2", [(x, False) for x in extra if x], CORTOS)

if not SOLO or "ruta_larga" in SOLO:                  # más de 260 caracteres (el límite clásico de Windows)
    d = carpeta("ruta_larga")
    while len(d) < 300:
        d = os.path.join(d, "Fotos del evento de la familia")
    try:
        os.makedirs(d, exist_ok=True)
        largas = []
        for i in range(3):
            destino = os.path.join(d, "foto de la ceremonia y la fiesta número %d.jpg" % (i + 1))
            with open(POZO[i], "rb") as fo, open(destino, "wb") as fd:
                fd.write(fo.read())
            largas.append((destino, False))
        print("  (ruta de %d caracteres)" % len(largas[0][0]))
        escenario("ruta_larga", largas, CORTOS)
    except OSError as e:
        print("  (este sistema no permite rutas tan largas: %s; no cuenta como falla de CineSlide)" % e)

if not SOLO or "4k" in SOLO:
    escenario("4k", [(f, False) for f in POZO[:2]], CORTOS, 3840, 2160)

if not SOLO or "muchas" in SOLO:                      # muchas fotos (estabilidad y memoria)
    d = carpeta("material_muchas")
    muchas = [imagen(os.path.join(d, "m_%03d.jpg" % i), "gradients=s=1600x1200:seed=%d" % (3000 + i), "-q:v", "4")
              for i in range(N_MUCHAS)]
    escenario("muchas", [(f, False) for f in muchas if f], CORTOS, 1280, 720)

if not SOLO or "vista" in SOLO:
    print("\n" + "=" * 100 + "\n## vista (vista previa de un tema, la usa la interfaz)")
    empezar("vista_previa")
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
    anotar(res)

if not SOLO or "interfaz" in SOLO:
    print("\n" + "=" * 100 + "\n## interfaz (ventana principal sin pantalla)")
    empezar("interfaz")
    t0 = time.time()
    res = {"escenario": "interfaz", "archivos": 0, "formato": "-", "ok": False, "fallas": []}
    try:                                   # como la app real: QEventLoop hasta 'cerrada'; se cierra como con el botón
        from PySide6 import QtCore, QtWidgets
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["CineSlide"])
        c.licencia_vigente = lambda: True                 # la máquina de prueba no tiene licencia: se prueba la interfaz, no la licencia
        Ventana = c._crear_clases_qt()
        Ventana._licencia_revisar = lambda self, *a, **k: None
        ventana = Ventana(c._ProxyPrincipal())
        ventana.resize(1400, 900)
        bucle = QtCore.QEventLoop()
        ventana.cerrada.connect(bucle.quit)
        ventana.show()
        app.processEvents()
        res["abrir_s"] = round(time.time() - t0, 2)

        def capturar_y_cerrar():
            modal = QtWidgets.QApplication.activeModalWidget()
            if modal is not None and modal is not ventana:      # la primera vez se abre el asistente de bienvenida (modal)
                res.setdefault("ventanas_modales", []).append(modal.windowTitle() or type(modal).__name__)
                modal.grab().save(os.path.join(SALIDA, "interfaz_modal_%d.png" % len(res["ventanas_modales"])))
                modal.reject() if hasattr(modal, "reject") else modal.close()
                QtCore.QTimer.singleShot(1000, capturar_y_cerrar)
                return
            ventana.grab().save(os.path.join(SALIDA, "interfaz.png"))
            ventana.close()
        QtCore.QTimer.singleShot(4000, capturar_y_cerrar)              # el asistente aparece a los 0,9-2,7 s
        QtCore.QTimer.singleShot(30000, bucle.quit)                     # por si no se cerrara
        bucle.exec()
        res["ok"] = os.path.isfile(os.path.join(SALIDA, "interfaz.png"))
        if not res["ok"]:
            res["fallas"].append("la ventana no se pudo dibujar ni cerrar")
    except Exception as e:
        traceback.print_exc()
        res["fallas"].append("%s: %s" % (type(e).__name__, str(e)[:300]))
    res["segundos"] = round(time.time() - t0, 1)
    print("  %s: ventana en %s s; ventanas que abrió solas: %s %s" % ("OK" if res["ok"] else "FALLA", res.get("abrir_s"),
                                                                  res.get("ventanas_modales") or "ninguna", res["fallas"]))
    anotar(res)

# ------------------------------------------------------------------------------------------------ (9.71) lo nuevo de la 9.71
def _resultado(nombre):
    print("\n" + "=" * 100 + "\n## " + nombre)
    empezar(nombre)
    return {"escenario": nombre, "archivos": 0, "formato": "-", "ok": False, "fallas": []}, time.time()


def _cerrar(res, t0, detalle=""):
    res["ok"] = not res["fallas"]
    res["segundos"] = round(time.time() - t0, 1)
    print("  %s en %.1f s %s %s" % ("OK" if res["ok"] else "FALLA", res["segundos"], detalle, res["fallas"] or ""))
    anotar(res)


def _diferencia(a, b):
    """(diferencia máxima de color, canales con más de 3 niveles) entre dos QImage del mismo tamaño (sin numpy)."""
    from PySide6 import QtCore, QtGui

    def opaca(img):                                  # sobre negro: los bordes semitransparentes (esquinas) comparan bien
        o = QtGui.QImage(img.width(), img.height(), QtGui.QImage.Format.Format_RGB32)
        o.fill(QtGui.QColor(0, 0, 0))
        q = QtGui.QPainter(o)
        q.drawImage(QtCore.QRect(0, 0, img.width(), img.height()), img)
        q.end()
        return o
    d = opaca(a)
    p = QtGui.QPainter(d)
    p.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_Difference)
    p.drawImage(0, 0, opaca(b))
    p.end()
    rgb = d.convertToFormat(QtGui.QImage.Format.Format_RGB888)
    datos = bytes(rgb.constBits())[:rgb.bytesPerLine() * rgb.height()]
    return (max(datos) if datos else 0), datos.translate(bytes(0 if i <= 3 else 1 for i in range(256))).count(1)


def _ventana_prueba():
    """La ventana principal real (sin pantalla), sin licencia ni diálogos que esperen a alguien."""
    from PySide6 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["CineSlide"])
    app.setQuitOnLastWindowClosed(False)              # se abren y cierran varias ventanas en la misma batería
    c.licencia_vigente = lambda: True
    Ventana = c._crear_clases_qt()
    Ventana._licencia_revisar = lambda self, *a, **k: None
    v = Ventana(c._ProxyPrincipal())
    v._licencia_pedir = lambda *a, **k: True
    v._licencia_lista = lambda *a, **k: True
    v._sin_intro = True
    v.resize(1400, 900)
    v.show()
    app.processEvents()
    return app, v


def _esperar(app, seg):
    from PySide6 import QtCore
    bucle = QtCore.QEventLoop()
    QtCore.QTimer.singleShot(int(seg * 1000), bucle.quit)
    bucle.exec()


_PRUEBA_C = r"""
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
int main(int argc, char **argv) {
    volatile unsigned long x = 0;
    if (argc > 1 && strcmp(argv[1], "quieta") == 0) { sleep(900); return 0; }
    if (argc > 1 && strcmp(argv[1], "con_hijo") == 0) { if (fork() == 0) { for (;;) x++; } }
    for (;;) x++;
}
"""


def _apps_de_prueba(d):
    """Procesos de prueba que parecen aplicaciones: en Mac una app .app compilada (ocupada, ocupada con un hijo, quieta); en
    Windows el Python de CineSlide. Se lanzan SUELTAS (a través de un shell que termina enseguida): los hijos de CineSlide nunca
    se pausan. Devuelve {tipo: pid}, los pid ocupados (con el del hijo) y el pid quieto."""
    if MAC:
        exe = os.path.join(d, "Prueba Ocupada.app", "Contents", "MacOS", "Prueba Ocupada")
        os.makedirs(os.path.dirname(exe), exist_ok=True)
        fuente = os.path.join(d, "prueba.c")
        with open(fuente, "w") as f:
            f.write(_PRUEBA_C)
        p = correr(["cc", "-O0", "-o", exe, fuente])
        if p.returncode:
            raise RuntimeError("no se pudo compilar la app de prueba: %s" % p.stderr.decode("utf-8", "replace")[-300:])
        ordenes = {"ocupada": [exe], "con_hijo": [exe, "con_hijo"], "quieta": [exe, "quieta"]}
    else:
        exe = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        exe = exe if os.path.isfile(exe) else sys.executable
        ordenes = {"ocupada": [exe, "-c", "while True: pass"],
                   "con_hijo": [exe, "-c", "import subprocess, sys; subprocess.Popen([sys.executable, '-c', 'while True: pass']); "
                                           "exec('while True: pass')"],
                   "quieta": [exe, "-c", "import time; time.sleep(900)"]}
    lanzar = ("import subprocess, sys; print(subprocess.Popen(sys.argv[1:], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, "
              "stderr=subprocess.DEVNULL, **({'start_new_session': True} if sys.platform == 'darwin' else {'creationflags': 8})).pid)")
    pids = dict((tipo, int(correr([sys.executable, "-c", lanzar] + o).stdout.decode().strip())) for tipo, o in ordenes.items())
    time.sleep(1.5)
    m, padres = c._pausa_muestra()
    rutas = dict((k[0], v[3]) for k, v in m.items())
    hijo = [pid for pid, pp in padres.items() if pp == pids["con_hijo"] and "conhost" not in rutas.get(pid, "").lower()]
    return pids, [pids["ocupada"], pids["con_hijo"]] + hijo[:1], pids["quieta"]


def _uso(pids, seg=1.0):
    """Núcleos que usó cada pid en 'seg' segundos (None si ya no está)."""
    a = dict((k[0], v[0]) for k, v in c._pausa_muestra()[0].items() if k[0] in pids)
    time.sleep(seg)
    b = dict((k[0], v[0]) for k, v in c._pausa_muestra()[0].items() if k[0] in pids)
    return dict((p, round((b[p] - a[p]) / seg, 2) if p in a and p in b else None) for p in pids)


def _detenidos(pids):
    """Mac: pid que ps muestra detenidos (estado T)."""
    if not MAC:
        return set()
    txt = correr(["ps", "-o", "pid=,stat=", "-p", ",".join(str(p) for p in pids)]).stdout.decode()
    return set(int(x.split()[0]) for x in txt.splitlines() if len(x.split()) > 1 and "T" in x.split()[1])


if not SOLO or "fondo_zonas" in SOLO:        # (9.71) el fondo por zonas da lo mismo que rehacerlo entero, en los 4 diseños
    res, t0 = _resultado("fondo_zonas")
    try:
        app, v = _ventana_prueba()
        if v.__dict__.get("_reloj_fondo"):
            v._reloj_fondo.stop()
        D = c.diseno_ui()
        fondo_orig = D["fondo"]
        res["fondos"] = {}
        for fondo in ("aurora", "grano", "petalos", "rejilla"):
            D["fondo"] = fondo
            v._cuadro_clave = None
            v._fondo_componer(0.0)
            ms, peor, area = [], 0, 0.0
            for paso in range(1, 421):                     # 14 s a 30 cuadros/s: barrido, estrella fugaz, hilo de luz, parpadeo
                t = paso / 30.0
                v._t_fondo = t
                t1 = time.time()
                reg = v._fondo_componer(t)
                ms.append(1000.0 * (time.time() - t1))
                if reg is not None and not reg.isEmpty():
                    area += sum(r.width() * r.height() for r in reg) / float(v.width() * v.height())
                if paso % 70 == 0:
                    inc = v._cuadro_img.copy()
                    v._cuadro_clave = None                 # el mismo instante, rehecho entero
                    v._fondo_componer(t)
                    dmax, ncan = _diferencia(inc, v._cuadro_img)
                    peor = max(peor, dmax)
                    if dmax > 3:
                        res["fallas"].append("%s t=%.1f s: el cuadro por zonas difiere del entero (%d niveles, %d canales)" % (
                            fondo, t, dmax, ncan))
            ms.sort()
            res["fondos"][fondo] = {"ms_media": round(sum(ms) / len(ms), 2), "ms_p95": round(ms[int(len(ms) * 0.95)], 2),
                                    "area_media_pct": round(100.0 * area / 420, 1), "dif_max": peor}
            print("  %-8s %5.2f ms por cuadro (p95 %5.2f) · repinta %4.1f %% · diferencia máx. %d" % (
                fondo, res["fondos"][fondo]["ms_media"], res["fondos"][fondo]["ms_p95"], res["fondos"][fondo]["area_media_pct"], peor))
        D["fondo"] = fondo_orig
        v._cuadro_clave = None
        v.close()
    except Exception as e:
        traceback.print_exc()
        res["fallas"].append("%s: %s" % (type(e).__name__, str(e)[:300]))
    _cerrar(res, t0)

if not SOLO or "pausa_apps" in SOLO:         # (9.71) pausar las demás apps mientras se crea el video (solo las de prueba)
    res, t0 = _resultado("pausa_apps")
    procs, ocupados, quieto = {}, [], None
    try:
        d = carpeta("pausa_apps")
        a, b_ = c._pausa_muestra()
        time.sleep(2.0)
        b, padres = c._pausa_muestra()
        propios = c._pausa_propios(padres)
        seco = sorted(set(c._pausa_app_entera(k, b, padres, propios)[1] for k, x in b.items()
                          if k in a and k[0] not in propios and (x[0] - a[k][0]) / 2.0 >= c._PAUSA_UMBRAL
                          and not c._pausa_protegida(x[2], x[3])))
        res["se_pausarian_en_esta_maquina"] = seco
        print("  en esta máquina se pausarían ahora: %s" % (", ".join(seco) or "ninguna app"))
        procs, ocupados, quieto = _apps_de_prueba(d)
        todos = ocupados + [quieto]
        c._PAUSA["solo"] = set(todos)                 # SOLO las de prueba
        antes = _uso(todos)
        print("  apps de prueba (núcleos): %s" % antes)
        if any((antes.get(p) or 0) < 0.3 for p in ocupados):
            res["fallas"].append("las apps de prueba no estaban ocupadas: %s" % antes)
        avisos = []
        c.pausa_empezar(aviso=lambda lista: avisos.append(list(lista)))
        t1 = time.time()
        while time.time() - t1 < 8 and not set(ocupados) <= set(k[0] for k in c._PAUSA["pausadas"]):
            time.sleep(0.1)
        res["pausa_en_s"] = round(time.time() - t1, 1)
        pausado = _uso(todos)
        det = _detenidos(todos)
        print("  pausadas en %.1f s · núcleos: %s · detenidas según ps: %s · aviso: %s" % (res["pausa_en_s"], pausado, sorted(det),
                                                                                           avisos[-1:] or "-"))
        if any((pausado.get(p) or 0) > 0.05 for p in ocupados) or (MAC and not set(ocupados) <= det):
            res["fallas"].append("no quedaron pausadas: %s" % pausado)
        if quieto in set(k[0] for k in c._PAUSA["pausadas"]):
            res["fallas"].append("pausó la app quieta (no hacía falta)")
        if not os.path.isfile(c._pausa_archivo()):
            res["fallas"].append("no guardó la lista de apps pausadas")
        vig = c._PAUSA.get("vigilante")
        if vig is None or vig.poll() is not None:
            res["fallas"].append("no quedó corriendo el vigilante")
        nombres = c.pausa_terminar()
        despues = _uso(todos)
        print("  reanudadas: %s · núcleos: %s" % (nombres, despues))
        if any((despues.get(p) or 0) < 0.3 for p in ocupados) or _detenidos(todos):
            res["fallas"].append("no se reanudaron: %s" % despues)
        time.sleep(2.0)
        if os.path.isfile(c._pausa_archivo()) or (vig is not None and vig.poll() is None):
            res["fallas"].append("quedó el archivo de pausa o el vigilante después de reanudar")
        # CineSlide se cae de golpe con apps pausadas: el vigilante las reanuda (y, si también cae el vigilante, al abrir CineSlide)
        guion = ("import os, sys, time, signal, subprocess\nsys.path.insert(0, %r)\nimport CineSlide as c\nc._PAUSA['solo'] = set(%r)\n"
                 "c.pausa_empezar()\nt = time.time()\nwhile time.time() - t < 8 and not set(%r) <= set(k[0] for k in c._PAUSA['pausadas']):\n"
                 "    time.sleep(0.1)\nif sys.argv[1] == 'sin_vigilante':\n    v = c._PAUSA['vigilante']\n"
                 "    os.kill(v.pid, signal.SIGKILL) if hasattr(signal, 'SIGKILL') else subprocess.run(['taskkill', '/F', '/PID', str(v.pid)])\n"
                 "os._exit(3)\n") % (CARPETA, todos, ocupados)
        for modo in ("con_vigilante", "sin_vigilante"):
            p = correr([sys.executable, "-c", guion, modo], timeout=60)
            time.sleep(2.5)
            u = _uso(ocupados)
            vivas = all((u.get(x) or 0) > 0.3 for x in ocupados)
            if modo == "con_vigilante":
                print("  CineSlide se cae: el vigilante las reanudó: %s (%s)" % (vivas, u))
                if not vivas:
                    res["fallas"].append("tras caerse CineSlide el vigilante no reanudó las apps: %s" % u)
            else:
                print("  cae también el vigilante: siguen pausadas: %s (%s)" % (not vivas, u))
                n = c.pausa_rescatar()                  # lo que hace CineSlide al abrir
                u2 = _uso(ocupados)
                print("  al abrir CineSlide se reanudaron %d: %s" % (n, u2))
                if not all((u2.get(x) or 0) > 0.3 for x in ocupados):
                    res["fallas"].append("al abrir CineSlide no se reanudaron las apps: %s" % u2)
        # CREAR VIDEO de verdad (la ventana): pausa durante el video y siguen al terminar
        from PySide6 import QtWidgets
        exec_orig = QtWidgets.QDialog.exec
        QtWidgets.QDialog.exec = lambda self, *a, **k: 0
        c.abrir_en_explorador = lambda *a, **k: None
        app, v = _ventana_prueba()
        v._avisar_fin = lambda *a, **k: None
        crear = v.principal.crear_presentacion_express
        # OJO: _ProxyPrincipal escribe en las globales del módulo: se deshace al final (si no, los escenarios de después
        # reciben carpeta_salida dos veces)
        v.principal.crear_presentacion_express = lambda *a, **k: crear(*a, carpeta_salida=carpeta("pausa_video"), **k)
        t_reanuda = []                                       # cuándo se reanudan de verdad (en máquinas lentas, antes del fin)
        _terminar = c.pausa_terminar
        c.pausa_terminar = lambda *a, **k: (t_reanuda.append(time.time()), _terminar(*a, **k))[1]
        dv = carpeta("material_pausa_video")
        # (9.77) 12 fotos: con 3 el video ya tardaba 2,3 s y no quedaba ninguna muestra después de los 3 s de margen
        for i, f in enumerate((POZO * 4)[:12]):
            with open(f, "rb") as fo, open(os.path.join(dv, "foto_%d.jpg" % i), "wb") as fd:
                fd.write(fo.read())
        v.ruta, v.archivos_manual, v.seleccion = dv, None, None
        v._aplicar_origen()
        _esperar(app, 3.0)
        linea, fin_m = [], [False]

        def mirar():
            while not fin_m[0]:
                linea.append((time.time(), _uso(ocupados, 0.5)))
        import threading
        hilo = threading.Thread(target=mirar, daemon=True)
        hilo.start()
        t_v = time.time()
        try:
            v.ejecutar()
        finally:
            v.principal.crear_presentacion_express = crear
            c.pausa_terminar = _terminar
        t_f = time.time()
        time.sleep(1.5)
        fin_m[0] = True
        hilo.join(5)
        t_r = min(t_reanuda + [t_f])
        # cada muestra mide [t, t + 0,5 s]: solo las que terminan antes de reanudarlas
        durante = [u for t, u in linea if t_v + 3.0 < t and t + 0.6 < t_r]
        final = [u for t, u in linea if t > t_f + 0.6]
        quieto_ok = all(all((x.get(p) or 0) < 0.05 for p in ocupados) for x in durante)
        siguen = bool(final) and all((final[-1].get(p) or 0) > 0.3 for p in ocupados)
        estado = (v.__dict__.get("_estado_ult") or ("", ""))[0]
        res["video_s"] = round(t_f - t_v, 1)
        print("  CREAR VIDEO: %.1f s · pausadas durante el video: %s (%d muestras) · siguieron: %s · aviso: %s" % (
            t_f - t_v, quieto_ok, len(durante), siguen, estado[-140:]))
        if not durante or not quieto_ok:
            res["fallas"].append("durante CREAR VIDEO las apps no quedaron pausadas: %s" % durante[:3])
        if not siguen:
            res["fallas"].append("después de CREAR VIDEO las apps no siguieron: %s" % final[-1:])
        if "siguieron" not in estado and "siguió" not in estado:
            res["fallas"].append("el aviso final no dice que las apps siguieron: %s" % estado[-200:])
        if not os.listdir(carpeta("pausa_video")):
            res["fallas"].append("CREAR VIDEO no dejó el video")
        v.close()
        QtWidgets.QDialog.exec = exec_orig
    except Exception as e:
        traceback.print_exc()
        res["fallas"].append("%s: %s" % (type(e).__name__, str(e)[:300]))
    finally:
        c._PAUSA["solo"] = None
        try:
            c.pausa_terminar()
        except Exception:
            pass
        for pid in ocupados + ([quieto] if quieto else []):
            try:
                if MAC:
                    import signal
                    os.kill(pid, signal.SIGCONT)
                    os.kill(pid, signal.SIGKILL)
                else:
                    correr(["taskkill", "/F", "/T", "/PID", str(pid)])
            except Exception:
                pass
    _cerrar(res, t0)

if not SOLO or "ocasion" in SOLO:            # (9.71) detector boda / XV: por el nombre y por el color, en tandas de 8 fotos
    res, t0 = _resultado("ocasion")
    try:
        for ruta, esperado in (("/x/Boda Ana y Luis", "Boda"), ("/x/XV Sofía", "XV años"), ("/x/Mis 15 años", "XV años"),
                               ("/x/Fiesta", None), ("/x/BODAS & XV RECURSOS", None)):
            r = c.ocasion_por_nombre(ruta, [])
            if (r[0] if r else None) != esperado:
                res["fallas"].append("por el nombre «%s»: %s (se esperaba %s)" % (ruta, r, esperado))
        d = carpeta("material_ocasion")
        # 'vestido' que llena casi toda la foto: blanco (boda) o lila (XV), con grano para que no sea un color plano
        juegos = {"Boda": "color=c=0xF4F2F0:s=1200x800,noise=alls=6:allf=t",
                  "XV años": "color=c=0xB98AD8:s=1200x800,noise=alls=6:allf=t"}
        for esperado, fuente in juegos.items():
            fotos = [imagen(os.path.join(d, "%s_%02d.jpg" % (esperado[:2], i)),
                            fuente + ",drawbox=x=%d:y=40:w=260:h=720:color=0x5a3a28@1:t=fill" % (60 + 80 * i), "-q:v", "3")
                     for i in range(12)]
            fotos = [f for f in fotos if f]
            t1 = time.time()
            oc, motivo, n = c.ocasion_por_fotos(fotos)
            seg = time.time() - t1
            print("  fotos de %-8s -> %-8s en %.2f s mirando %d fotos (%s)" % (esperado, oc, seg, n, motivo))
            if oc != esperado:
                res["fallas"].append("fotos de %s: detectó %s (%s)" % (esperado, oc, motivo))
            if n > 8:
                res["fallas"].append("fotos de %s: no decidió con la primera tanda de 8 (miró %d)" % (esperado, n))
            if seg > 3.0:
                res["fallas"].append("fotos de %s: tardó %.1f s" % (esperado, seg))
        oc, motivo, n = c.ocasion_por_fotos(POZO)
        print("  fotos sin vestido (degradados) -> %s (%s, %d fotos)" % (oc, motivo, n))
    except Exception as e:
        traceback.print_exc()
        res["fallas"].append("%s: %s" % (type(e).__name__, str(e)[:300]))
    _cerrar(res, t0)

if not SOLO or "musica_971" in SOLO:         # (9.71) canciones propias en Boda / XV y escuchar con doble clic (afplay en Mac)
    res, t0 = _resultado("musica_971")
    try:
        d = carpeta("material_musica_971")
        propia = cancion(os.path.join(d, "Mi canción de quince.mp3"), 8)
        if not c.musica_propia_poner(propia, "Quince años", True):
            res["fallas"].append("no se pudo poner la canción propia en XV años")
        cats = c.musica_categorias_de(propia)
        en_bib = any(os.path.normcase(os.path.abspath(r)) == os.path.normcase(os.path.abspath(propia))
                     for cat, rs in c.musica_biblioteca() if cat == "Quince años" for r in rs)
        print("  categorías de la propia: %s · está en la biblioteca de XV años: %s" % (cats, en_bib))
        if "Quince años" not in cats or not en_bib:
            res["fallas"].append("la canción propia no quedó en XV años: %s" % cats)
        c.musica_propia_poner(propia, "Quince años", False)
        if "Quince años" in c.musica_categorias_de(propia):
            res["fallas"].append("no se pudo quitar la canción propia de XV años")
        ok = c.audio_reproducir(propia)
        time.sleep(0.8)
        sonando = c.audio_sonando()
        c.audio_detener()
        time.sleep(0.3)
        res["sonido"] = "sonó" if sonando else ("el reproductor no siguió (¿sin salida de audio en la máquina?)" if ok else "no arrancó")
        print("  doble clic (reproducir): %s · sonando: %s · después de detener: %s" % (ok, sonando, c.audio_sonando()))
        if MAC and not ok:
            res["fallas"].append("en Mac no se pudo lanzar afplay")
        if c.audio_sonando():
            res["fallas"].append("la canción siguió sonando después de detenerla")
    except Exception as e:
        traceback.print_exc()
        res["fallas"].append("%s: %s" % (type(e).__name__, str(e)[:300]))
    _cerrar(res, t0)

def _descendientes(pid):
    """pid de los hijos, nietos... de pid (como los ve la pausa de apps: Windows y Mac)."""
    _m, padres = c._pausa_muestra()
    hijos, pend = set(), [pid]
    while pend:
        p = pend.pop()
        for h, pp in padres.items():
            if pp == p and h not in hijos:
                hijos.add(h)
                pend.append(h)
    return hijos


if (not SOLO or "prep_previa" in SOLO) and hasattr(c, "_ex_preparar_por_tandas"):   # (9.72) preparación previa
    res, t0 = _resultado("prep_previa")
    try:
        d = carpeta("material_prep_previa")
        fotos = fotos_camara(d, 700, 8)
        items = [(f, False) for f in fotos]
        v = dict(BASE)
        v.update({"formato_video": HORIZONTAL, "express_resolucion": "720p", "t_segundos_por_foto": 2.0, "t1_segundos_por_foto": 2.0,
                  "carpeta_exportacion": carpeta("prep_previa"), "incluir_videos": True})
        script = os.path.join(CARPETA, "CineSlide.py")
        lanzar = dict(stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                      env=dict(os.environ, PYTHONIOENCODING="utf-8"), **({"start_new_session": True} if MAC else {}))

        def json_prep(variables, nombre):
            ruta = os.path.join(d, nombre)
            with open(ruta, "w", encoding="utf-8") as f:
                json.dump({"items": [list(x) for x in items], "variables": variables, "W": 1280, "H": 720, "fps": FPS}, f, default=str)
            return ruta
        # 1) cortarla a medias (como CREAR VIDEO o un cambio de ajustes): no deben quedar sus ffmpeg sueltos
        otro = dict(v, estilo_diseno=TEMAS[1] if len(TEMAS) > 1 else v.get("estilo_diseno"))
        p = subprocess.Popen([sys.executable, script, "--preparar", json_prep(otro, "cortar.json")], **lanzar)
        time.sleep(4.0)
        hijos = _descendientes(p.pid)
        if MAC:
            import signal
            os.killpg(p.pid, signal.SIGKILL)
        else:
            correr(["taskkill", "/T", "/F", "/PID", str(p.pid)])
        p.wait()
        time.sleep(1.0)
        vivos = hijos & set(k[0] for k in c._pausa_muestra()[0])
        print("  cortada a los 4 s: %d procesos suyos; quedaron vivos: %d" % (len(hijos), len(vivos)))
        if vivos:
            res["fallas"].append("al cortar la preparación previa quedaron %d procesos sueltos" % len(vivos))
        # 2) completa, en otro proceso con prioridad baja (como la lanza la ventana)
        t1 = time.time()
        p = subprocess.run([sys.executable, script, "--preparar", json_prep(v, "preparar.json")], timeout=900,
                           **dict((k, x) for k, x in lanzar.items() if k != "start_new_session"))
        salida_p = p.stdout.decode("utf-8", "replace")
        linea = [x for x in salida_p.splitlines() if x.startswith("PREPARADO ")]
        info = json.loads(linea[-1][10:]) if linea else {}
        res["previa_s"] = round(time.time() - t1, 1)
        print("  preparación previa: código %s en %.1f s -> %s" % (p.returncode, res["previa_s"], info or salida_p[-400:]))
        if p.returncode or (info.get("preparadas") or 0) + (info.get("de_cache") or 0) != len(items) or info.get("fallidas"):
            res["fallas"].append("la preparación previa no preparó las %d fotos: %s" % (len(items), info or salida_p[-300:]))
        # 3) el video (CREAR VIDEO) debe encontrar TODAS las fotos ya preparadas y salir bien
        del REGISTRO[:]
        t1 = time.time()
        r = CREAR_EXPRESS(list(items), dict(v), 1280, 720, FPS, carpeta_salida=carpeta("prep_previa"), nombre="prep_previa")
        res["video_s"] = round(time.time() - t1, 1)
        de_cache = [m for _n, m in REGISTRO if "salieron de la caché" in m]
        print("  video en %.1f s · %s" % (res["video_s"], de_cache[0][:140] if de_cache else "NINGUNA foto salió de la caché"))
        if not de_cache or not de_cache[0].strip().split()[1].isdigit() or int(de_cache[0].split()[1]) != len(items):
            res["fallas"].append("el video no usó lo preparado: %s" % (de_cache[:1] or "nada de la caché"))
        comprobaciones, _dv = revisar_mp4(r["ruta"], False, False, (1280, 720))
        res["fallas"] += [texto for ok, texto, _n in comprobaciones if not ok]
    except Exception as e:
        traceback.print_exc()
        res["fallas"].append("%s: %s" % (type(e).__name__, str(e)[:300]))
    _cerrar(res, t0)

if (not SOLO or "soltar" in SOLO) and hasattr(c, "_crear_clases_qt"):   # (9.72) soltar una carpeta en cualquier parte
    res, t0 = _resultado("soltar")
    from PySide6 import QtCore, QtGui, QtWidgets
    from PySide6.QtCore import Qt
    exec_dlg, exec_msg = QtWidgets.QDialog.exec, QtWidgets.QMessageBox.exec
    QtWidgets.QDialog.exec = lambda self, *a, **k: 0         # con datos nuevos se abre solo el asistente (modal): nadie lo cierra
    QtWidgets.QMessageBox.exec = lambda self, *a, **k: 0
    try:
        app, v = _ventana_prueba()
        if not hasattr(v, "_soltar_ventana"):
            raise RuntimeError("esta versión no tiene _SoltarEnVentana")
        d = carpeta("material_soltar")
        fotos_camara(d, 900, 3, 800, 600)
        RECIB = []
        _recibir = v._recibir_archivos
        v._recibir_archivos = lambda rutas: RECIB.append(list(rutas))

        def mime(rutas=None):
            rutas = rutas or [d]
            m = QtCore.QMimeData()
            m.setUrls([QtCore.QUrl.fromLocalFile(r) for r in rutas])
            m.setText(rutas[0])                           # el Finder también manda el texto: los campos lo aceptan
            return m

        def soltar(qw, x, y, mod=Qt.KeyboardModifier.NoModifier, rutas=None):
            """Como lo manda la plataforma (Finder): por la QWindow, que lo reparte al control de abajo."""
            antes, acc = len(RECIB), Qt.DropAction.CopyAction | Qt.DropAction.MoveAction | Qt.DropAction.LinkAction
            p, m = QtCore.QPoint(x, y), mime(rutas)        # m vivo hasta el final: el evento no se queda con él
            en = QtGui.QDragEnterEvent(p, acc, m, Qt.MouseButton.LeftButton, mod)
            QtWidgets.QApplication.sendEvent(qw, en)
            mv = QtGui.QDragMoveEvent(p, acc, m, Qt.MouseButton.LeftButton, mod)
            if en.isAccepted():
                mv.setDropAction(en.dropAction())
                mv.accept()
            QtWidgets.QApplication.sendEvent(qw, mv)
            if not mv.isAccepted():
                QtWidgets.QApplication.sendEvent(qw, QtGui.QDragLeaveEvent())
                return None, False
            dr = QtGui.QDropEvent(QtCore.QPointF(p), acc, m, Qt.MouseButton.LeftButton, mod)
            QtWidgets.QApplication.sendEvent(qw, dr)
            app.processEvents()
            return dr.dropAction(), len(RECIB) > antes

        for modo in ("simple", "avanzado"):
            v._mostrar_modo(modo)
            _esperar(app, 0.6)
            textos = dict((id(w), w.text()) for w in v.findChildren(QtWidgets.QLineEdit))
            malos, total = {}, 0
            for y in range(14, v.height() - 6, 50):
                for x in range(14, v.width() - 6, 50):
                    total += 1
                    if not soltar(v.windowHandle(), x, y)[1]:
                        w = v.childAt(x, y)
                        n = type(w).__name__ if w is not None else "(ventana)"
                        malos[n] = malos.get(n, 0) + 1
            # un campo cambiado solo cuenta si quedó la RUTA soltada en él (otros pueden cambiar solos mientras tanto: la
            # ventana termina de abrir, se calcula la música...)
            dif = [(type(w.parent()).__name__, textos.get(id(w)), w.text()) for w in v.findChildren(QtWidgets.QLineEdit)
                   if textos.get(id(w)) != w.text()]
            cambiados = [x for x in dif if os.path.normcase(d) in os.path.normcase(x[2] or "")]
            print("  modo %-8s %d de %d puntos cargan la carpeta%s · campos con la ruta pegada: %d%s" % (
                modo, total - sum(malos.values()), total, (" (fallan: %s)" % malos) if malos else "", len(cambiados),
                (" · otros campos que cambiaron: %s" % [(p, a[:40] if a else a, n[:40]) for p, a, n in dif]) if dif else ""))
            if malos or cambiados:
                res["fallas"].append("modo %s: %d puntos no cargan la carpeta %s, %d campos con la ruta pegada" % (
                    modo, sum(malos.values()), malos, len(cambiados)))
        accion, ok = soltar(v.windowHandle(), 300, 300, Qt.KeyboardModifier.ShiftModifier)
        if not ok or accion != Qt.DropAction.CopyAction:
            res["fallas"].append("con Mayús no quedó como copia: %s" % accion)

        def local(nombre, metodo):
            f = metodo.__func__
            return f.__closure__[f.__code__.co_freevars.index(nombre)].cell_contents
        asis = local("DialogoAsistente", v.abrir_asistente)(v)
        asis.d.show()
        _esperar(app, 0.5)
        a_ok = sum(1 for y in range(20, asis.d.height() - 10, 90) for x in range(20, asis.d.width() - 10, 90)
                   if soltar(asis.d.windowHandle(), x, y)[1])
        a_tot = len(range(20, asis.d.height() - 10, 90)) * len(range(20, asis.d.width() - 10, 90))
        asis.d.close()
        listo = local("DialogoListo", v._avisar_fin)(v, "Video listo", "Prueba", None, d, [])
        listo.mostrar()
        _esperar(app, 0.8)
        _acc, l_ok = soltar(listo.d.windowHandle(), listo.d.width() // 2, listo.d.height() // 2)
        _esperar(app, 0.5)
        print("  asistente: %d de %d puntos · «Video listo»: %s" % (a_ok, a_tot, "carga la carpeta" if l_ok else "NO la carga"))
        if a_ok != a_tot:
            res["fallas"].append("asistente: %d de %d puntos" % (a_ok, a_tot))
        if not l_ok:
            res["fallas"].append("«Video listo» no recibe la carpeta")
        v._recibir_archivos = _recibir
        soltar(v.windowHandle(), 400, 400)
        _esperar(app, 2.5)
        print("  carga real: %s · %s" % (os.path.basename(v.ruta or ""), v.conteo))
        if os.path.normcase(os.path.abspath(v.ruta or "")) != os.path.normcase(os.path.abspath(d)) or v.conteo[0] != 3:
            res["fallas"].append("la carpeta soltada no se cargó: %s %s" % (v.ruta, v.conteo))
        if hasattr(c, "musica_agregar_soltadas"):          # (9.73) la música soltada se AGREGA, encendida y antes de las incluidas
            nrm = lambda x: os.path.normcase(os.path.abspath(x))
            incl = set(nrm(r) for _c, rs in c.musica_biblioteca(propias=False) for r in rs)

            def antes_de_incluidas(lista, omit, r):
                apag = set(nrm(x) for x in omit)
                prim = next((i for i, x in enumerate(lista) if nrm(x) in incl and nrm(x) not in apag), len(lista))
                pos = [i for i, x in enumerate(lista) if nrm(x) == nrm(r)]
                return len(pos) == 1 and pos[0] < prim and nrm(r) not in apag
            s1, s2 = cancion(os.path.join(d, "Mi cancion.mp3"), 4), cancion(os.path.join(d, "Otra cancion.mp3"), 4)
            n_ant = len(v.musica.get("lista") or [])
            soltar(v.windowHandle(), 500, 400, rutas=[s1])
            _esperar(app, 0.3)
            ok1 = antes_de_incluidas(v.musica.get("lista") or [], v.musica.get("omitidas") or [], s1)
            print("  canción soltada en la ventana: %d -> %d canciones · suena antes de las incluidas: %s" % (
                n_ant, len(v.musica.get("lista") or []), ok1))
            if not ok1 or len(v.musica.get("lista") or []) != n_ant + 1:
                res["fallas"].append("la canción soltada en la ventana no se agregó bien")
            f = v.elegir_musica.__func__
            dm = f.__closure__[f.__code__.co_freevars.index("DialogoMusica")].cell_contents(
                v, v.musica, v._pedir_archivos_musica, v._datos_presentacion_musica)
            dm.d.show()
            _esperar(app, 0.6)
            pts = [(x, y) for y in range(20, dm.d.height() - 10, 120) for x in range(20, dm.d.width() - 10, 120)]
            acept = sum(1 for x, y in pts if soltar(dm.d.windowHandle(), x, y, rutas=[s2])[0] is not None)
            ok2 = antes_de_incluidas(dm._leer_lista(), [r for r in dm._leer_lista() if r in dm.omit], s2)
            print("  ventana Música: %d de %d puntos aceptan la canción · queda una vez, encendida y antes de las incluidas: %s" % (
                acept, len(pts), ok2))
            if acept != len(pts) or not ok2:
                res["fallas"].append("ventana Música: %d de %d puntos, bien ubicada: %s" % (acept, len(pts), ok2))
            dm.d.close()
        v.close()
    except Exception as e:
        traceback.print_exc()
        res["fallas"].append("%s: %s" % (type(e).__name__, str(e)[:300]))
    finally:
        QtWidgets.QDialog.exec, QtWidgets.QMessageBox.exec = exec_dlg, exec_msg
    _cerrar(res, t0)

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
