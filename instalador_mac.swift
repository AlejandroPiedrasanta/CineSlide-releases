// =============================================================================================================================
// (9.62) Contents/MacOS/instalar de "Instalar CineSlide.app" (la app del DMG): la ventana del instalador, NATIVA (AppKit +
// SwiftUI), para que se vea AL INSTANTE al hacer doble clic (pedido del usuario: "todo debe ser inmediato, sin tiempo de espera";
// antes la ventana era de Python y salía después de sacar Python y PySide6, unos segundos sin nada en pantalla).
// - Si CineSlide ya está instalado con la misma versión o una más nueva (VERSION_MOTOR de su CineSlide.py), solo lo abre.
// - Si no: muestra la ventana (estilo de "Activa tu licencia": panel con el icono y un anillo de luz, barra con degradado y los 7
//   pasos), ejecuta Resources/instalar_mac.sh (CINESLIDE_VENTANA=1) y sigue el avance que escribe en CINESLIDE_AVANCE (una línea
//   por evento: PASO / OK / AVISO / DETALLE / FALLO / FIN, tabulador, texto). Al terminar abre CineSlide (la app de app.txt) de
//   inmediato, se cierra y expulsa el DMG. Si falla: el motivo, "Ver registro" y "Cerrar".
//   instalar --demo | --demo-error      simula una instalación (para ver el diseño: probar-instalador.yml saca capturas)
// Lo compila construir-dmg.yml en una Mac de GitHub (swiftc, arm64 + x86_64 con lipo); Windows no puede.
// =============================================================================================================================
import AppKit
import SwiftUI

// ---------------------------------------------------------------------------------------------------------------- colores
extension Color {
    init(hex: UInt32, a: Double = 1) {
        self.init(.sRGB, red: Double((hex >> 16) & 0xff) / 255, green: Double((hex >> 8) & 0xff) / 255,
                  blue: Double(hex & 0xff) / 255, opacity: a)
    }
}

let ROSA = Color(hex: 0xff4fa8), VIOLETA = Color(hex: 0x9b6cff), CIAN = Color(hex: 0x2fd3f0)
let TEXTO = Color(hex: 0xf4eff9), SUAVE = Color(hex: 0xb4aac6), TENUE = Color(hex: 0x6c6382)
let VERDE = Color(hex: 0x3ed392), ROJO = Color(hex: 0xff6b6b), AMBAR = Color(hex: 0xffc46b)
let BENEFICIOS = ["Todo incluido", "No necesita internet", "No pide contraseña"]
let PASOS = ["Carpetas de CineSlide", "Python y la interfaz", "Programa CineSlide", "Motor de video (ffmpeg)", "Configuración",
             "App en Aplicaciones y en el Dock", "Plantillas de video"]
// porcentaje al empezar y al terminar cada paso (0 = sacar el paquete) y segundos típicos: dentro de un paso la barra avanza sola
// hacia su final sin llegar, así nunca se ve detenida
let TRAMOS: [(Double, Double)] = [(0, 3), (3, 5), (5, 45), (45, 58), (58, 80), (80, 84), (84, 95), (95, 99)]
let DURACION: [Double] = [2, 1, 10, 4, 6, 1, 4, 2]

let HOME = NSHomeDirectory()
let DIR = HOME + "/Library/Application Support/CineSlide"

func quitarANSI(_ s: String) -> String {
    let rx = try! NSRegularExpression(pattern: "\u{1B}\\[[0-9;?]*[A-Za-z]")
    return rx.stringByReplacingMatches(in: s, range: NSRange(s.startIndex..., in: s), withTemplate: "")
}

func numeroVersion(_ v: String) -> Int {
    let p = v.split(separator: ".").map { Int($0) ?? 0 }
    return (p.count > 0 ? p[0] : 0) * 1_000_000 + (p.count > 1 ? p[1] : 0) * 1_000 + (p.count > 2 ? p[2] : 0)
}

func versionInstalada() -> String? {
    guard let texto = try? String(contentsOfFile: DIR + "/CineSlide.py", encoding: .utf8) else { return nil }
    let rx = try! NSRegularExpression(pattern: "^VERSION_MOTOR = \"([0-9.]+)\"", options: [.anchorsMatchLines])
    guard let m = rx.firstMatch(in: texto, range: NSRange(texto.startIndex..., in: texto)),
          let r = Range(m.range(at: 1), in: texto) else { return nil }
    return String(texto[r])
}

func appInstalada() -> String? {
    if let s = try? String(contentsOfFile: DIR + "/app.txt", encoding: .utf8) {
        let ruta = s.trimmingCharacters(in: .whitespacesAndNewlines)
        if !ruta.isEmpty && FileManager.default.fileExists(atPath: ruta) { return ruta }
    }
    for ruta in ["/Applications/CineSlide.app", HOME + "/Applications/CineSlide.app"] where FileManager.default.fileExists(atPath: ruta) {
        return ruta
    }
    return nil
}

// ---------------------------------------------------------------------------------------------------------------- avance
final class Avance: ObservableObject {
    @Published var paso = 0
    @Published var detalles = Array(repeating: [String](), count: 8)
    @Published var avisos = Array(repeating: "", count: 8)
    @Published var vivo = ""
    @Published var estado = "instalando"           // instalando | listo | error
    @Published var mensaje = ""
    @Published var valor: Double = 0
    var tPaso = Date()
    var tEstado = Date()
    private let rxPaso = try! NSRegularExpression(pattern: "([0-9])\\s*/\\s*7")

    func evento(_ bruto: String) {
        guard estado == "instalando" else { return }
        let limpio = quitarANSI(bruto).trimmingCharacters(in: CharacterSet(charactersIn: "\r\n"))
        let partes = limpio.split(separator: "\t", maxSplits: 1, omittingEmptySubsequences: false)
        let tipo = partes.first.map { String($0) } ?? ""
        let texto = partes.count > 1 ? String(partes[1]).trimmingCharacters(in: .whitespaces) : ""
        switch tipo {
        case "PASO":
            var n = 0
            if let m = rxPaso.firstMatch(in: texto, range: NSRange(texto.startIndex..., in: texto)),
               let r = Range(m.range(at: 1), in: texto) { n = Int(texto[r]) ?? 0 }
            if n > paso { paso = n; tPaso = Date(); vivo = "" }
        case "OK":
            if !texto.isEmpty { detalles[paso].append(texto.replacingOccurrences(of: HOME, with: "~")) }
        case "AVISO":
            if !texto.isEmpty { avisos[paso] = texto }
        case "DETALLE":
            if !texto.isEmpty { vivo = texto }
        case "FALLO":
            estado = "error"; mensaje = texto.isEmpty ? "Algo salió mal." : texto; tEstado = Date()
        case "FIN":
            estado = "listo"; tEstado = Date()
        default:
            break
        }
    }

    func objetivo() -> Double {
        if estado == "listo" { return 100 }
        let i = min(max(paso, 0), 7)
        let (a, b) = TRAMOS[i]
        let k = Date().timeIntervalSince(tPaso)
        return a + (b - a) * min(1, 0.9 * (1 - exp(-k / DURACION[i])))
    }

    func avanzar(_ dt: Double) {
        let obj = objetivo()
        valor += (obj - valor) * min(1, dt * (estado == "listo" ? 5 : 2.4))
    }
}

// ---------------------------------------------------------------------------------------------------------------- vista
struct BotonPildora: ButtonStyle {
    var principal = true
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 14, weight: principal ? .bold : .semibold))
            .foregroundColor(.white)
            .padding(.horizontal, 26).frame(height: 44)
            .background(
                Group {
                    if principal {
                        Capsule().fill(LinearGradient(colors: [ROSA, VIOLETA, CIAN], startPoint: .leading, endPoint: .trailing))
                    } else {
                        Capsule().fill(Color.white.opacity(0.06)).overlay(Capsule().stroke(Color(hex: 0x4a3a62), lineWidth: 1))
                    }
                }
            )
            .opacity(configuration.isPressed ? 0.8 : 1)
    }
}

struct VistaInstalador: View {
    @ObservedObject var av: Avance
    let version: String
    let mac: String
    let icono: NSImage?
    let verRegistro: () -> Void
    let cerrar: () -> Void

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30.0)) { ctx in
            let t = ctx.date.timeIntervalSinceReferenceDate
            HStack(spacing: 0) {
                heroe(t)
                columna(t)
                    .padding(.leading, 46).padding(.trailing, 44).padding(.top, 46).padding(.bottom, 34)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            }
            .frame(width: 900, height: 560)
            .background(LinearGradient(colors: [Color(hex: 0x191326), Color(hex: 0x0d0a16)], startPoint: .topLeading,
                                       endPoint: .bottomTrailing))
            .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 24, style: .continuous).stroke(colorBorde, lineWidth: 1.2))
        }
    }

    var colorEstado: Color { av.estado == "listo" ? VERDE : (av.estado == "error" ? ROJO : ROSA) }
    var colorBorde: Color {
        av.estado == "listo" ? VERDE.opacity(0.6) : (av.estado == "error" ? ROJO.opacity(0.6) : Color(hex: 0x3b2b52))
    }

    // ---- panel de la izquierda
    func heroe(_ t: Double) -> some View {
        ZStack {
            LinearGradient(colors: [Color(hex: 0x3b1250), Color(hex: 0x1f1238), Color(hex: 0x120d26)], startPoint: .topLeading,
                           endPoint: .bottomTrailing)
            luz(ROSA, 0.25, 0.20, 264, 0.21, 0, t)
            luz(VIOLETA, 0.85, 0.80, 280, 0.17, 1, t)
            luz(CIAN, 0.55, 0.50, 182, 0.13, 2, t)
            VStack(spacing: 0) {
                Spacer().frame(height: 80)
                emblema(t)
                Text("CineSlide").font(.system(size: 30, weight: .bold)).foregroundColor(TEXTO).padding(.top, 8)
                Text("INSTALADOR  ·  v\(version)").font(.system(size: 11, weight: .bold)).tracking(3)
                    .foregroundColor(ROSA.opacity(0.9)).padding(.top, 8)
                Spacer()
                VStack(alignment: .leading, spacing: 14) {
                    ForEach(BENEFICIOS, id: \.self) { b in
                        HStack(spacing: 10) {
                            Circle().fill(ROSA.opacity(0.2)).frame(width: 20, height: 20)
                                .overlay(Image(systemName: "checkmark").font(.system(size: 9, weight: .heavy)).foregroundColor(ROSA))
                            Text(b).font(.system(size: 13, weight: .semibold)).foregroundColor(TEXTO.opacity(0.88))
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading).padding(.leading, 40).padding(.bottom, 34)
            }
        }
        .frame(width: 330, height: 560)
        .clipped()
        .overlay(Rectangle().fill(LinearGradient(colors: [ROSA.opacity(0), ROSA.opacity(0.35), ROSA.opacity(0)], startPoint: .top,
                                                 endPoint: .bottom)).frame(width: 1).padding(.vertical, 24),
                 alignment: .trailing)
    }

    func luz(_ c: Color, _ fx: Double, _ fy: Double, _ r: Double, _ vel: Double, _ i: Double, _ t: Double) -> some View {
        Circle()
            .fill(RadialGradient(colors: [c.opacity(0.28), c.opacity(0)], center: .center, startRadius: 0, endRadius: r))
            .frame(width: r * 2, height: r * 2)
            .position(x: 330 * (fx + 0.12 * sin(t * vel * 2 + i)), y: 560 * (fy + 0.08 * cos(t * vel * 1.6 + i * 2)))
    }

    func emblema(_ t: Double) -> some View {
        let instalando = av.estado == "instalando"
        let ang = (t * (instalando ? 300 : 60)).truncatingRemainder(dividingBy: 360)
        let k = Date().timeIntervalSince(av.tEstado)
        let pulso = instalando ? 0.75 + 0.25 * sin(t * 2.2) : 1 + 0.8 * exp(-k * 2.2)
        let paradas: [Gradient.Stop]
        if instalando {
            paradas = [Gradient.Stop(color: ROSA, location: 0), Gradient.Stop(color: VIOLETA.opacity(0.7), location: 0.18),
                       Gradient.Stop(color: CIAN.opacity(0), location: 0.38), Gradient.Stop(color: CIAN.opacity(0), location: 0.7),
                       Gradient.Stop(color: CIAN.opacity(0.9), location: 1)]
        } else {
            paradas = [Gradient.Stop(color: colorEstado, location: 0), Gradient.Stop(color: colorEstado.opacity(0.55), location: 0.5),
                       Gradient.Stop(color: colorEstado, location: 1)]
        }
        return ZStack {
            Circle().fill(RadialGradient(colors: [colorEstado.opacity(min(1, 0.34 * pulso)), colorEstado.opacity(0)],
                                         center: .center, startRadius: 0, endRadius: 138))
                .frame(width: 276, height: 276)
            Circle().fill(Color(hex: 0x120b1e, a: 0.94)).frame(width: 120, height: 120)
                .overlay(Circle().stroke(Color.white.opacity(0.1), lineWidth: 1))
            Circle()
                .stroke(AngularGradient(gradient: Gradient(stops: paradas), center: .center),
                        style: StrokeStyle(lineWidth: 4, lineCap: .round))
                .frame(width: 138, height: 138)
                .rotationEffect(.degrees(ang))
            ForEach(0..<3, id: \.self) { i in
                let a = (-ang * 0.55 + Double(i) * 120) * .pi / 180
                Circle().fill((instalando ? [CIAN, ROSA, VIOLETA][i] : colorEstado).opacity(0.8)).frame(width: 6, height: 6)
                    .offset(x: cos(a) * 84, y: sin(a) * 84)
            }
            Group {
                if let icono = icono {
                    Image(nsImage: icono).resizable().interpolation(.high).frame(width: 86, height: 86)
                        .clipShape(RoundedRectangle(cornerRadius: 19, style: .continuous))
                }
            }
            .offset(y: sin(t * 1.7) * 2.5)
            if !instalando {
                Circle().fill(colorEstado).frame(width: 34, height: 34)
                    .overlay(Circle().stroke(Color(hex: 0x120b1e), lineWidth: 3))
                    .overlay(av.estado == "listo"
                             ? AnyView(Image(systemName: "checkmark").font(.system(size: 15, weight: .heavy)).foregroundColor(.white))
                             : AnyView(Text("!").font(.system(size: 20, weight: .black)).foregroundColor(.white)))
                    .offset(x: 41, y: 41)
            }
        }
        .frame(width: 180, height: 180)
    }

    // ---- columna de la derecha
    var titulo: String {
        av.estado == "listo" ? "¡CineSlide está listo!" : (av.estado == "error" ? "No se pudo instalar" : "Instalando CineSlide")
    }
    var subtitulo: String {
        av.estado == "listo" ? "Se instaló la versión \(version). Lo encuentras en Aplicaciones, en el Dock y en Launchpad."
            : (av.estado == "error" ? av.mensaje : "Versión \(version) para \(mac)")
    }
    var accion: String {
        if av.estado == "listo" { return "Instalación completa" }
        if av.estado == "error" { return "Se detuvo en: \(PASOS[max(0, av.paso - 1)])" }
        if av.paso == 0 { return "Preparando el instalador…" }
        return "Paso \(av.paso) de 7 · \(PASOS[av.paso - 1])"
    }

    func columna(_ t: Double) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(titulo).font(.system(size: 30, weight: .bold)).foregroundColor(TEXTO).lineLimit(1)
            Text(subtitulo).font(.system(size: 14)).foregroundColor(av.estado == "error" ? ROJO : SUAVE)
                .lineLimit(2).frame(height: 40, alignment: .topLeading).padding(.top, 6)
            HStack {
                Text(accion).font(.system(size: 13, weight: .semibold)).foregroundColor(SUAVE).lineLimit(1)
                Spacer()
                Text("\(Int(av.valor.rounded())) %").font(.system(size: 15, weight: .bold)).monospacedDigit().foregroundColor(TEXTO)
            }
            .padding(.top, 14)
            barra(t).padding(.top, 10)
            VStack(spacing: 0) {
                ForEach(1...7, id: \.self) { i in fila(i, t) }
            }
            .padding(.top, 22)
            Spacer(minLength: 0)
            pie()
        }
    }

    var rellenoBarra: LinearGradient {
        let colores: [Color]
        if av.estado == "listo" {
            colores = [Color(hex: 0x23a86e), Color(hex: 0x5fd6a0)]
        } else if av.estado == "error" {
            colores = [Color(hex: 0xc2444a), ROJO]
        } else {
            colores = [ROSA, VIOLETA, CIAN]
        }
        return LinearGradient(colors: colores, startPoint: .leading, endPoint: .trailing)
    }

    func barra(_ t: Double) -> some View {
        GeometryReader { g in
            let w: CGFloat = max(10, g.size.width * CGFloat(min(100, av.valor)) / 100)
            ZStack(alignment: .leading) {
                Capsule().fill(Color.white.opacity(0.07))
                Capsule().fill(rellenoBarra).frame(width: w)
                if av.estado == "instalando" {
                    Circle().fill(RadialGradient(colors: [CIAN.opacity(0.55), CIAN.opacity(0)], center: .center, startRadius: 0,
                                                 endRadius: 16))
                        .frame(width: 32, height: 32).offset(x: w - 19)
                }
            }
        }
        .frame(height: 10)
    }

    func fila(_ i: Int, _ t: Double) -> some View {
        let hecho = av.estado == "listo" || i < av.paso
        let actual = av.estado != "listo" && i == av.paso
        var detalle = "", colorDetalle = TENUE
        if !av.avisos[i].isEmpty {
            detalle = av.avisos[i]; colorDetalle = AMBAR.opacity(0.9)
        } else if actual && !av.vivo.isEmpty {
            detalle = av.vivo
        } else if hecho && !av.detalles[i].isEmpty {
            detalle = av.detalles[i].suffix(2).map { $0.hasSuffix(".") ? String($0.dropLast()) : $0 }.joined(separator: " · ")
        }
        let nombre = i == 3 ? "Programa CineSlide \(version)" : PASOS[i - 1]
        return HStack(spacing: 12) {
            ZStack {
                if hecho {
                    Circle().fill(LinearGradient(colors: [ROSA, VIOLETA], startPoint: .topLeading, endPoint: .bottomTrailing))
                    Image(systemName: "checkmark").font(.system(size: 10, weight: .heavy)).foregroundColor(.white)
                } else if actual && av.estado == "error" {
                    Circle().fill(ROJO)
                    Text("!").font(.system(size: 13, weight: .black)).foregroundColor(.white)
                } else if actual {
                    Circle().stroke(ROSA.opacity(0.22), lineWidth: 2.4).frame(width: 19, height: 19)
                    Circle().trim(from: 0, to: 0.28).stroke(ROSA, style: StrokeStyle(lineWidth: 2.6, lineCap: .round))
                        .frame(width: 19, height: 19).rotationEffect(.degrees((t * 420).truncatingRemainder(dividingBy: 360)))
                } else {
                    Circle().stroke(TENUE.opacity(0.7), lineWidth: 1.6).frame(width: 18, height: 18)
                }
            }
            .frame(width: 22, height: 22)
            Text(nombre).font(.system(size: 14, weight: actual ? .semibold : .regular))
                .foregroundColor(hecho || actual ? TEXTO : TENUE).lineLimit(1).layoutPriority(1)
            Spacer(minLength: 12)
            Text(detalle).font(.system(size: 12)).foregroundColor(colorDetalle).lineLimit(1).truncationMode(.tail)
        }
        .frame(height: 34)
    }

    @ViewBuilder func pie() -> some View {
        if av.estado == "error" {
            HStack(spacing: 12) {
                Button("Ver registro", action: verRegistro).buttonStyle(BotonPildora(principal: false))
                Button("Cerrar", action: cerrar).buttonStyle(BotonPildora(principal: true))
                Text("Envíanos el registro si se repite.").font(.system(size: 12)).foregroundColor(TENUE).padding(.leading, 6)
            }
        } else if av.estado == "listo" {
            Text("Abriendo CineSlide…").font(.system(size: 14, weight: .semibold)).foregroundColor(VERDE)
        } else {
            Text("Puedes seguir usando tu Mac. Al terminar, CineSlide se abre solo.").font(.system(size: 13)).foregroundColor(TENUE)
        }
    }
}

// ---------------------------------------------------------------------------------------------------------------- app
final class VentanaSinMarco: NSWindow {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { true }
}

final class Instalador: NSObject, NSApplicationDelegate {
    let av = Avance()
    var ventana: NSWindow?
    var reloj: Timer?
    var proceso: Process?
    var rutaAvance = ""
    var rutaRegistro = ""
    var pos: UInt64 = 0
    var resto = Data()
    var antes = Date()
    var terminado = false
    var demo: [(Double, String)] = []
    var tDemo = Date()
    let args = CommandLine.arguments
    var esDemo: Bool { args.contains("--demo") || args.contains("--demo-error") }
    lazy var recursos = Bundle.main.resourcePath ?? "."
    lazy var version = (Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String) ?? "?"

    func applicationDidFinishLaunching(_ n: Notification) {
        // ya instalado (igual o más nuevo): solo se abre CineSlide
        if !esDemo, let inst = versionInstalada(), let app = appInstalada(),
           FileManager.default.isExecutableFile(atPath: DIR + "/python/bin/python3"),
           FileManager.default.fileExists(atPath: DIR + "/datos/config.json"),
           numeroVersion(inst) >= numeroVersion(version) {
            NSWorkspace.shared.openApplication(at: URL(fileURLWithPath: app), configuration: NSWorkspace.OpenConfiguration()) { _, _ in
                DispatchQueue.main.async { NSApp.terminate(nil) }
            }
            return
        }
        #if arch(arm64)
        let mac = "Mac con Apple Silicon"
        #else
        let mac = "Mac con procesador Intel"
        #endif
        let icono = NSImage(contentsOfFile: recursos + "/paquete/CineSlide.png") ?? NSApp.applicationIconImage
        let vista = VistaInstalador(av: av, version: version, mac: mac, icono: icono,
                                    verRegistro: { [weak self] in self?.verRegistro() },
                                    cerrar: { NSApp.terminate(nil) })
        let w = VentanaSinMarco(contentRect: NSRect(x: 0, y: 0, width: 900, height: 560), styleMask: [.borderless],
                                backing: .buffered, defer: false)
        w.isOpaque = false
        w.backgroundColor = .clear
        w.hasShadow = true
        w.isMovableByWindowBackground = true
        w.title = "Instalar CineSlide"
        w.contentView = NSHostingView(rootView: vista)
        w.center()
        w.makeKeyAndOrderFront(nil)
        ventana = w
        NSApp.activate(ignoringOtherApps: true)
        if esDemo { empezarDemo() } else { empezar() }
        antes = Date()
        reloj = Timer.scheduledTimer(withTimeInterval: 1.0 / 30.0, repeats: true) { [weak self] _ in self?.tic() }
    }

    func applicationShouldTerminate(_ s: NSApplication) -> NSApplication.TerminateReply {
        (av.estado == "instalando" && !esDemo) ? .terminateCancel : .terminateNow     // no se cierra a media instalación
    }

    // ---- la instalación de verdad: instalar_mac.sh
    func empezar() {
        let fm = FileManager.default
        try? fm.createDirectory(atPath: DIR + "/datos/logs", withIntermediateDirectories: true)
        let f = DateFormatter()
        f.dateFormat = "yyyyMMdd_HHmmss"
        rutaRegistro = DIR + "/datos/logs/instalador_mac_\(f.string(from: Date())).log"
        rutaAvance = NSTemporaryDirectory() + "cineslide_avance_\(ProcessInfo.processInfo.processIdentifier).txt"
        fm.createFile(atPath: rutaAvance, contents: Data())
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/bash")
        p.arguments = [recursos + "/instalar_mac.sh"]
        var env = ProcessInfo.processInfo.environment
        env["CINESLIDE_PAQUETE"] = recursos + "/paquete"
        env["CINESLIDE_VENTANA"] = "1"
        env["CINESLIDE_AVANCE"] = rutaAvance
        env["CINESLIDE_LOG"] = rutaRegistro
        p.environment = env
        p.standardInput = FileHandle.nullDevice
        p.standardOutput = FileHandle.nullDevice
        p.standardError = FileHandle.nullDevice
        p.terminationHandler = { [weak self] proc in
            let st = proc.terminationStatus
            DispatchQueue.main.async { self?.termino(st) }
        }
        do {
            try p.run()
            proceso = p
        } catch {
            av.evento("FALLO\tNo se pudo empezar la instalación: \(error.localizedDescription)")
        }
    }

    func leer() {
        guard !rutaAvance.isEmpty, let fh = FileHandle(forReadingAtPath: rutaAvance) else { return }
        defer { try? fh.close() }
        do { try fh.seek(toOffset: pos) } catch { return }
        let datos = fh.readDataToEndOfFile()
        if datos.isEmpty { return }
        pos += UInt64(datos.count)
        resto.append(datos)
        while let i = resto.firstIndex(of: 0x0A) {
            let linea = Data(resto[resto.startIndex..<i])
            resto = Data(resto[resto.index(after: i)...])
            av.evento(String(decoding: linea, as: UTF8.self))
        }
    }

    func termino(_ st: Int32) {
        leer()
        if av.estado == "instalando" {
            if st == 0 {
                av.evento("FIN\t")
            } else {
                av.evento("FALLO\tEl instalador se detuvo antes de terminar (código \(st)). Ábrelo otra vez; si se repite, envíanos el registro.")
            }
        }
    }

    func tic() {
        let ahora = Date()
        let dt = min(0.1, max(0, ahora.timeIntervalSince(antes)))
        antes = ahora
        if esDemo { alimentarDemo() } else { leer() }
        av.avanzar(dt)
        if av.estado == "listo" && !terminado && !esDemo {
            terminado = true
            abrirCineSlideYSalir()
        }
    }

    // ---- al terminar: CineSlide YA (sin cuenta atrás), el instalador se cierra y el DMG se expulsa
    func abrirCineSlideYSalir() {
        if let app = appInstalada() {
            NSWorkspace.shared.openApplication(at: URL(fileURLWithPath: app), configuration: NSWorkspace.OpenConfiguration()) { _, _ in }
        }
        let expulsar = Process()
        expulsar.executableURL = URL(fileURLWithPath: "/bin/sh")
        expulsar.arguments = ["-c", "sleep 3; for v in /Volumes/CineSlide*; do [ -d \"$v/Instalar CineSlide.app/Contents/Resources/paquete\" ] && /usr/bin/hdiutil detach \"$v\" -quiet; done; exit 0"]
        expulsar.standardInput = FileHandle.nullDevice
        expulsar.standardOutput = FileHandle.nullDevice
        expulsar.standardError = FileHandle.nullDevice
        try? expulsar.run()
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) { NSApp.terminate(nil) }
    }

    func verRegistro() {
        guard !rutaRegistro.isEmpty, let texto = try? String(contentsOfFile: rutaRegistro, encoding: .utf8) else { return }
        let limpio = (rutaRegistro as NSString).deletingPathExtension + "_para_leer.txt"
        try? quitarANSI(texto).write(toFile: limpio, atomically: true, encoding: .utf8)
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/open")
        p.arguments = ["-e", limpio]
        try? p.run()
    }

    // ---- simulación (--demo / --demo-error)
    func empezarDemo() {
        tDemo = Date()
        demo = [(0.0, "PASO\tPreparando el instalador"), (0.3, "OK\tPaquete listo."), (0.5, "PASO\t1/7  Carpetas"),
                (0.7, "OK\t\(DIR)"), (0.9, "PASO\t2/7  Python y PySide6 (interfaz)"), (4.5, "OK\tPython 3.15.2"),
                (4.7, "OK\tPySide6 / Qt 6.12.0"), (4.9, "PASO\t3/7  Programa CineSlide"),
                (5.8, "OK\tCineSlide \(version) con las vistas previas de los temas"), (6.0, "OK\tPrograma precompilado (abre más rápido)"),
                (6.2, "PASO\t4/7  ffmpeg (motor Express)"), (7.6, "OK\tffmpeg 9.0.2"),
                (7.9, "OK\tVideo por hardware de Apple (VideoToolbox): sí")]
        if args.contains("--demo-error") {
            demo.append((8.4, "FALLO\tNo se pudo escribir la configuración."))
        } else {
            demo += [(8.2, "PASO\t5/7  Configuración"), (8.5, "OK\tdatos/config.json"), (8.7, "PASO\t6/7  App CineSlide (Aplicaciones)"),
                     (9.6, "OK\t/Applications/CineSlide.app (también en Launchpad y Spotlight)"), (9.8, "OK\tFijado en el Dock"),
                     (10.0, "PASO\t7/7  Plantillas de video"), (10.3, "OK\tSe preparan solas en segundo plano"), (10.6, "FIN\t\(version)")]
        }
    }

    func alimentarDemo() {
        let k = Date().timeIntervalSince(tDemo)
        while let e = demo.first, e.0 <= k {
            demo.removeFirst()
            av.evento(e.1)
        }
    }
}

@main
struct Principal {
    static func main() {
        let app = NSApplication.shared
        let delegado = Instalador()
        app.delegate = delegado
        app.setActivationPolicy(.regular)
        app.run()
    }
}
