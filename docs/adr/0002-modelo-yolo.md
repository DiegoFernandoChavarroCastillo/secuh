# 0002 — YOLOv8n como modelo de detección inicial

- **Estado:** aceptada (confirmada por el benchmark del ADR 0003: 4.2 fps de análisis en CPU i3, detección fiable)
- **Fecha:** 2026-07-14 (confirmada 2026-07-15)

## Contexto

El sistema debe detectar personas en tiempo casi real sobre hardware modesto
(sin GPU dedicada garantizada). Las opciones consideradas: YOLOv8n/s y
YOLO11n/s de Ultralytics.

## Decisión

Empezar con **YOLOv8n** (nano) filtrando la clase `person` (índice 0 de COCO),
inferencia a `imgsz=640` y análisis a ~5 fps. Es el punto de partida con más
documentación y comunidad; la API de Ultralytics permite cambiar de peso
(`yolov8s.pt`, `yolo11n.pt`) sin tocar código.

## Consecuencias

- Si el benchmark (ADR 0003) muestra holgura de CPU, se probará `yolo11n` o la
  variante `s` para mejor precisión; si muestra apuro, se bajará `imgsz` o los
  fps de análisis antes de cambiar de modelo.
- El adaptador `YoloPersonDetector` (Fase 1) recibirá el nombre del peso por
  configuración, nunca hardcodeado.
- Los pesos `.pt` no se versionan en git (están en `.gitignore`); Ultralytics
  los descarga en el primer uso.
