"""Spike de Fase 0: valida que el hardware sostiene el pipeline de detección.

Script DESCARTABLE (no es código de producción): lee un stream de video,
aplica el pre-filtro de movimiento (MOG2) y, cuando hay movimiento, corre
YOLO filtrando la clase `person`. Mide fps, latencia de inferencia y CPU.

Uso (desde la raíz del repo, con el entorno de backend/ activo):

    # Celular con IP Webcam (Android): usar la URL que muestra la app
    python spike/benchmark.py --source http://192.168.1.50:8080/video

    # Cámara RTSP
    python spike/benchmark.py --source "rtsp://usuario:clave@192.168.1.60:554/stream1"

    # Webcam USB local (índice 0)
    python spike/benchmark.py --source 0

    # Con ventana de visualización (validar detecciones a ojo)
    python spike/benchmark.py --source 0 --display

Al terminar (por --duration o Ctrl+C) imprime el resumen y lo guarda como
JSON en spike/results/. Con esos números se completa el ADR 0003
(docs/adr/0003-linea-base-de-hardware.md).
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
import psutil
from ultralytics import YOLO

PERSON_CLASS_ID = 0  # índice de "person" en COCO


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--source",
        required=True,
        help="URL del stream (http/rtsp), o índice numérico de webcam USB (ej. 0)",
    )
    parser.add_argument("--model", default="yolov8n.pt", help="Peso YOLO (default: yolov8n.pt)")
    parser.add_argument("--imgsz", type=int, default=640, help="Resolución de inferencia")
    parser.add_argument(
        "--analysis-fps",
        type=float,
        default=5.0,
        help="fps objetivo de análisis (los frames intermedios se descartan)",
    )
    parser.add_argument("--confidence", type=float, default=0.5, help="Umbral de confianza")
    parser.add_argument(
        "--min-motion-ratio",
        type=float,
        default=0.01,
        help="Fracción mínima de píxeles en movimiento para invocar YOLO",
    )
    parser.add_argument("--duration", type=float, default=60.0, help="Duración en segundos")
    parser.add_argument("--display", action="store_true", help="Mostrar ventana con detecciones")
    return parser.parse_args()


def open_capture(source: str) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(int(source) if source.isdigit() else source)
    if not cap.isOpened():
        raise SystemExit(f"No se pudo abrir la fuente de video: {source!r}")
    return cap


def main() -> None:
    args = parse_args()

    print(f"Cargando modelo {args.model}...")
    model = YOLO(args.model)
    # La primera inferencia paga la inicialización de torch (puede tardar
    # decenas de segundos); se hace aquí para no contaminar las métricas.
    print("Calentando el modelo...")
    warmup_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    model.predict(warmup_frame, imgsz=args.imgsz, classes=[PERSON_CLASS_ID], verbose=False)
    bg_subtractor = cv2.createBackgroundSubtractorMOG2(
        history=500, varThreshold=16, detectShadows=False
    )

    cap = open_capture(args.source)
    process = psutil.Process()
    process.cpu_percent()  # primera llamada: inicializa el contador

    frames_read = 0
    frames_analyzed = 0
    frames_with_motion = 0
    frames_with_person = 0
    inference_ms: list[float] = []
    cpu_samples: list[float] = []

    analysis_interval = 1.0 / args.analysis_fps
    start = time.monotonic()
    last_analysis = 0.0
    last_cpu_sample = start

    print(f"Midiendo durante {args.duration:.0f}s... (Ctrl+C para terminar antes)")
    try:
        while (time.monotonic() - start) < args.duration:
            ok, frame = cap.read()
            if not ok:
                print("Frame perdido; reintentando lectura...")
                time.sleep(0.5)
                continue
            frames_read += 1

            now = time.monotonic()
            if (now - last_analysis) < analysis_interval:
                continue  # descartar frames intermedios: solo analizamos a N fps
            last_analysis = now
            frames_analyzed += 1

            mask = bg_subtractor.apply(frame)
            mask = cv2.medianBlur(mask, 5)
            motion_ratio = cv2.countNonZero(mask) / (frame.shape[0] * frame.shape[1])
            has_motion = motion_ratio > args.min_motion_ratio

            persons = 0
            if has_motion:
                frames_with_motion += 1
                t0 = time.perf_counter()
                results = model.predict(
                    frame,
                    imgsz=args.imgsz,
                    classes=[PERSON_CLASS_ID],
                    conf=args.confidence,
                    verbose=False,
                )
                inference_ms.append((time.perf_counter() - t0) * 1000)
                persons = len(results[0].boxes)
                if persons:
                    frames_with_person += 1

            if (now - last_cpu_sample) >= 1.0:
                cpu_samples.append(process.cpu_percent())
                last_cpu_sample = now

            if args.display:
                label = f"movimiento={has_motion} personas={persons}"
                cv2.putText(frame, label, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                cv2.imshow("secuh spike (q para salir)", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    except KeyboardInterrupt:
        print("\nInterrumpido por el usuario.")
    finally:
        cap.release()
        if args.display:
            cv2.destroyAllWindows()

    elapsed = time.monotonic() - start
    summary = {
        "timestamp": datetime.now(UTC).isoformat(),
        "source": args.source,
        "model": args.model,
        "imgsz": args.imgsz,
        "target_analysis_fps": args.analysis_fps,
        "elapsed_seconds": round(elapsed, 1),
        "frames_read": frames_read,
        "frames_analyzed": frames_analyzed,
        "achieved_analysis_fps": round(frames_analyzed / elapsed, 2) if elapsed else 0,
        "frames_with_motion": frames_with_motion,
        "frames_with_person": frames_with_person,
        "inference_ms_avg": round(statistics.mean(inference_ms), 1) if inference_ms else None,
        "inference_ms_p95": (
            round(statistics.quantiles(inference_ms, n=20)[18], 1)
            if len(inference_ms) >= 20
            else None
        ),
        "cpu_percent_avg": round(statistics.mean(cpu_samples), 1) if cpu_samples else None,
        "cpu_percent_max": round(max(cpu_samples), 1) if cpu_samples else None,
    }

    print("\n=== Resumen del benchmark ===")
    for key, value in summary.items():
        print(f"  {key}: {value}")

    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)
    out = results_dir / f"benchmark-{datetime.now():%Y%m%d-%H%M%S}.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nGuardado en {out}")
    print("Siguiente paso: volcar estos números al ADR docs/adr/0003-linea-base-de-hardware.md")


if __name__ == "__main__":
    main()
