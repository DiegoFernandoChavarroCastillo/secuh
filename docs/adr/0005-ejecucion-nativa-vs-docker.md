# 0005 — Ejecución nativa (`run.py`) como alternativa de primera clase a Docker en Windows

- **Estado:** aceptada
- **Fecha:** 2026-07-16

## Contexto

Tras empaquetar el producto en Docker (Fase 6) y probarlo con hardware real
(una cámara RTSP física y un celular con IP Webcam), se encontró que **Docker
Desktop en Windows no puede recibir el vídeo de cámaras RTSP que transmiten
por UDP**:

- Docker Desktop en Windows corre los contenedores dentro de una VM
  (WSL2/Hyper-V). La red puente (`bridge`, la que usa `docker-compose.yml`)
  hace NAT: el contenedor puede iniciar conexiones salientes, pero un
  paquete UDP entrante hacia un puerto que la cámara elige al negociar RTSP
  no tiene forma de saber a qué contenedor reenviarse.
- Se probó forzar `network_mode: host` para el backend como posible arreglo.
  En Windows esto **no comparte la red del host real**, sino la de la VM
  interna de Docker Desktop — el resultado fue que ni siquiera el panel
  quedó accesible en `localhost:8000` desde Windows. Se revirtió de
  inmediato.
- Se confirmó con pruebas directas (`cv2.VideoCapture` dentro y fuera del
  contenedor) que **forzar TCP tampoco sirve**: la cámara de prueba no
  negocia bien el transporte TCP con el cliente RTSP de FFmpeg (que usa
  OpenCV), aunque conecta sin problema con VLC (motor `live555`, distinto y
  más tolerante). Esto es una incompatibilidad de la cámara/FFmpeg, no de
  Docker, y quedó fuera del alcance de este ADR (ver CHANGELOG 0.6.1,
  sección "Conocido").
- Aparte de las cámaras, el propio ciclo de build de Docker resultó fragil
  en una conexión lenta/inestable (ver ADR previo sobre CPU-only torch): cada
  iteración de diagnóstico costaba minutos de descarga.

## Decisión

Se añade `run.py` en la raíz del repo: un script que levanta el backend
(uvicorn) y el panel (`npm run dev`) juntos, en procesos nativos de Windows,
usando **SQLite** (sin PostgreSQL) para no requerir ningún servicio adicional.
Genera `backend/.env` con credenciales aleatorias en el primer arranque.

- **Docker sigue siendo el camino recomendado para producción en Linux**
  (el objetivo real de instalación, según `docs/runbook.md`): ahí no existe
  la capa de virtualización de red que causa el problema, y `network_mode:
  host` funciona de verdad.
- **`run.py` es la vía recomendada para desarrollo y pruebas en Windows**,
  especialmente si hay cámaras RTSP de por medio. También sirve como
  alternativa permanente si el usuario simplemente prefiere no depender de
  Docker Desktop para una instalación de un solo equipo.

## Consecuencias

- Dos vías de arranque para mantener en paralelo (Docker y nativo), aunque
  ambas leen la misma configuración (`ServerSettings` vía variables
  `SECUH_*`), así que no hay lógica duplicada — solo *cómo* se arrancan los
  procesos.
- En modo nativo, el modelo YOLO se descarga en el primer armado de cámara
  (no viene pre-empaquetado como en la imagen Docker desde 0.6.1), así que el
  primer arranque de una cámara tarda más.
- Si en el futuro se evalúa correr Docker Desktop con WSL2 en modo
  *mirrored networking* (una opción más reciente que puede resolver el
  problema de NAT sin los inconvenientes del modo host) valdría la pena
  revisar esta decisión — no se probó en esta sesión.
