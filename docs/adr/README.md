# Architecture Decision Records (ADR)

Cada decisión de arquitectura relevante queda registrada en un archivo corto de
este directorio, numerado secuencialmente. El objetivo es no re-discutir
decisiones y facilitar el retomar el proyecto tras un tiempo.

## Formato

```markdown
# NNNN — Título de la decisión

- **Estado:** propuesta | aceptada | reemplazada por NNNN
- **Fecha:** AAAA-MM-DD

## Contexto
Qué problema o pregunta motivó la decisión.

## Decisión
Qué se decidió, en una o dos frases.

## Consecuencias
Qué implica: costos, límites, qué habría que revisar si cambia el contexto.
```

## Índice

| # | Decisión | Estado |
|---|---|---|
| [0001](0001-python-312-y-uv.md) | Python 3.12 + uv como gestor de dependencias | aceptada |
| [0002](0002-modelo-yolo.md) | YOLOv8n como modelo de detección inicial | aceptada (provisional) |
| [0003](0003-linea-base-de-hardware.md) | Línea base de hardware | aceptada (revalidar en hardware de despliegue) |
