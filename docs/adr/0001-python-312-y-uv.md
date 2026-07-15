# 0001 — Python 3.12 + uv como gestor de dependencias

- **Estado:** aceptada
- **Fecha:** 2026-07-14

## Contexto

La máquina de desarrollo tiene Python 3.14, pero el ecosistema de visión
(PyTorch, Ultralytics) aún no publica wheels estables para 3.14. Se necesita
una versión soportada por todo el stack y un gestor que la aprovisione de
forma reproducible en cualquier máquina (incluida la de un cliente).

## Decisión

- **Python 3.12** como versión del proyecto, fijada en `backend/.python-version`
  y acotada en `pyproject.toml` (`>=3.12,<3.14`; numpy ≥ 2.5 ya exige 3.12).
- **uv** como gestor de dependencias y entornos: instala el intérprete
  correcto automáticamente, genera `uv.lock` (reproducibilidad) y es
  drásticamente más rápido que pip/poetry.

## Consecuencias

- `uv sync --all-groups` deja el entorno listo en un solo comando; el lockfile
  se versiona en git.
- Cuando torch soporte 3.13/3.14 de forma estable, basta subir el rango en
  `pyproject.toml` y el `.python-version`.
- Los colaboradores no necesitan tener Python 3.12 preinstalado: uv lo baja.
