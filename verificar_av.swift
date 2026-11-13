// verificar_av.swift - abre un MP4 con AVFoundation (lo que usan QuickTime, Fotos y Safari en la Mac) y dice lo que ve.
// La compila y usa probar-mac.yml (probar_video_mac.py):
//
//     xcrun swiftc -swift-version 5 -O verificar_av.swift -o verificar_av
//     verificar_av <video.mp4> <carpeta para los cuadros> <segundo> [<segundo> ...]
//
// Decodifica TODOS los cuadros (en BGRA, como para mostrarlos en pantalla) y todo el audio; guarda en BGRA el primer cuadro
// en o después de cada segundo pedido (cuadro_<i>.bgra) y escribe en la salida UNA línea JSON con lo que leyó.
// Código 0 si pudo leerlo todo.
import AVFoundation
import CoreMedia
import CoreVideo
import Foundation

func codigo4(_ c: FourCharCode) -> String {
    let b = [UInt8((c >> 24) & 0xFF), UInt8((c >> 16) & 0xFF), UInt8((c >> 8) & 0xFF), UInt8(c & 0xFF)]
    return String(decoding: b, as: UTF8.self)
}

func segundos(_ t: CMTime) -> Double {
    return t.isNumeric ? t.seconds : -1.0
}

func escribirJSON(_ r: [String: Any]) {
    if let d = try? JSONSerialization.data(withJSONObject: r, options: [.sortedKeys]), let s = String(data: d, encoding: .utf8) {
        print(s)
    }
}

func principal() async -> Int32 {
    let args = CommandLine.arguments
    if args.count < 4 {
        escribirJSON(["error": "uso: verificar_av <video.mp4> <carpeta> <segundo> [<segundo> ...]"])
        return 2
    }
    let url = URL(fileURLWithPath: args[1])
    let carpeta = URL(fileURLWithPath: args[2], isDirectory: true)
    let pedidos = args[3...].map { CMTime(seconds: Double($0) ?? 0.0, preferredTimescale: 90000) }
    var r: [String: Any] = [:]
    do {
        let asset = AVURLAsset(url: url)
        let reproducible = try await asset.load(.isPlayable)
        let duracion = try await asset.load(.duration)
        let pistasV = try await asset.loadTracks(withMediaType: .video)
        let pistasA = try await asset.loadTracks(withMediaType: .audio)
        r["reproducible"] = reproducible
        r["duracion"] = segundos(duracion)
        r["pistas_video"] = pistasV.count
        r["pistas_audio"] = pistasA.count
        guard let pv = pistasV.first else {
            r["error"] = "sin pista de video"
            escribirJSON(r)
            return 1
        }
        let decodificable = try await pv.load(.isDecodable)
        let fps = try await pv.load(.nominalFrameRate)
        let formatosV = try await pv.load(.formatDescriptions)
        r["decodificable"] = decodificable
        r["cuadros_por_segundo"] = Double(fps)
        if let fd = formatosV.first {
            r["codec"] = codigo4(CMFormatDescriptionGetMediaSubType(fd))
            let dim = CMVideoFormatDescriptionGetDimensions(fd)
            r["ancho"] = Int(dim.width)
            r["alto"] = Int(dim.height)
            // El color tal como lo entiende la Mac (del átomo 'colr' del MP4 o del propio video).
            let ext = (CMFormatDescriptionGetExtensions(fd) as? [String: Any]) ?? [:]
            let primarias = ext[kCMFormatDescriptionExtension_ColorPrimaries as String] as? String ?? ""
            let transferencia = ext[kCMFormatDescriptionExtension_TransferFunction as String] as? String ?? ""
            let matriz = ext[kCMFormatDescriptionExtension_YCbCrMatrix as String] as? String ?? ""
            r["primarias"] = primarias
            r["transferencia"] = transferencia
            r["matriz"] = matriz
            r["rango_completo"] = ext[kCMFormatDescriptionExtension_FullRangeVideo as String] as? Bool ?? false
            r["color_709"] = primarias == (kCMFormatDescriptionColorPrimaries_ITU_R_709_2 as String)
                && transferencia == (kCMFormatDescriptionTransferFunction_ITU_R_709_2 as String)
                && matriz == (kCMFormatDescriptionYCbCrMatrix_ITU_R_709_2 as String)
        }

        // Video: todos los cuadros, convertidos a BGRA como para la pantalla.
        let lectorV = try AVAssetReader(asset: asset)
        let salidaV = AVAssetReaderTrackOutput(track: pv, outputSettings: [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA])
        salidaV.alwaysCopiesSampleData = false
        lectorV.add(salidaV)
        guard lectorV.startReading() else {
            throw lectorV.error ?? NSError(domain: "verificar_av", code: 1)
        }
        var cuadros = 0
        var mejores = [CMTime](repeating: .invalid, count: pedidos.count)
        var datos = [Data?](repeating: nil, count: pedidos.count)
        var tamanos = [(Int, Int)](repeating: (0, 0), count: pedidos.count)
        while let sb = salidaV.copyNextSampleBuffer() {
            guard let pb = CMSampleBufferGetImageBuffer(sb) else { continue }
            cuadros += 1
            let pts = CMSampleBufferGetPresentationTimeStamp(sb)
            for i in 0..<pedidos.count where CMTimeCompare(pts, pedidos[i]) >= 0
                && (!mejores[i].isValid || CMTimeCompare(pts, mejores[i]) < 0) {
                mejores[i] = pts
                CVPixelBufferLockBaseAddress(pb, .readOnly)
                let w = CVPixelBufferGetWidth(pb)
                let h = CVPixelBufferGetHeight(pb)
                let fila = CVPixelBufferGetBytesPerRow(pb)
                var d = Data(capacity: w * h * 4)
                if let base = CVPixelBufferGetBaseAddress(pb) {
                    for y in 0..<h {
                        d.append(base.advanced(by: y * fila).assumingMemoryBound(to: UInt8.self), count: w * 4)
                    }
                }
                CVPixelBufferUnlockBaseAddress(pb, .readOnly)
                datos[i] = d
                tamanos[i] = (w, h)
            }
        }
        r["cuadros_decodificados"] = cuadros
        r["lectura_video"] = lectorV.status == .completed ? "completa" : "falló: \(lectorV.error?.localizedDescription ?? "?")"
        var guardados: [[String: Any]] = []
        for i in 0..<pedidos.count {
            guard let d = datos[i] else { continue }
            let archivo = carpeta.appendingPathComponent("cuadro_\(i).bgra")
            try d.write(to: archivo)
            guardados.append(["pedido": segundos(pedidos[i]), "pts": segundos(mejores[i]), "archivo": archivo.path,
                              "ancho": tamanos[i].0, "alto": tamanos[i].1])
        }
        r["cuadros"] = guardados

        // Audio: todo, a PCM.
        if let pa = pistasA.first {
            let formatosA = try await pa.load(.formatDescriptions)
            if let fa = formatosA.first, let asbd = CMAudioFormatDescriptionGetStreamBasicDescription(fa) {
                r["audio_codec"] = codigo4(asbd.pointee.mFormatID)
                r["audio_hz"] = asbd.pointee.mSampleRate
                r["audio_canales"] = Int(asbd.pointee.mChannelsPerFrame)
            }
            let lectorA = try AVAssetReader(asset: asset)
            let salidaA = AVAssetReaderTrackOutput(track: pa, outputSettings: [AVFormatIDKey: kAudioFormatLinearPCM])
            lectorA.add(salidaA)
            guard lectorA.startReading() else {
                throw lectorA.error ?? NSError(domain: "verificar_av", code: 2)
            }
            var muestras = 0
            while let sb = salidaA.copyNextSampleBuffer() {
                muestras += CMSampleBufferGetNumSamples(sb)
            }
            r["audio_muestras"] = muestras
            r["lectura_audio"] = lectorA.status == .completed ? "completa" : "falló: \(lectorA.error?.localizedDescription ?? "?")"
        }
    } catch {
        r["error"] = "\(error)"
        escribirJSON(r)
        return 1
    }
    escribirJSON(r)
    return 0
}

let codigo = await principal()
exit(codigo)
