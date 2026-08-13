# Checklist de instalación en sitio

Imprimir y completar en cada instalación. Instalación: ________________
Fecha: ____________ Técnico: ____________

## Vía de instalación (elegir una antes de salir)

- [ ] **A — Docker sobre Linux.** La vía de producción. Marcar si el equipo es
      Linux, o si hay más de una cámara, o si el sistema queda desatendido.
- [ ] **B — Nativo con `run.py` sobre Windows.** Obligatoria si hay cámaras
      **RTSP**: Docker Desktop en Windows no puede recibir su vídeo por UDP
      (ADR 0005). Pensada para instalación de un solo equipo.

Los pasos marcados **[A]** o **[B]** aplican solo a esa vía; el resto, a ambas.

## Antes de ir

- [ ] **[A]** Equipo con Docker probado (el compose levanta en taller).
- [ ] **[A]** `deploy/.env` generado con secretos únicos para este cliente
      (nunca reusar).
- [ ] **[B]** Equipo con `uv` y Node 22+ instalados, y `python run.py` probado
      en taller de punta a punta (la primera vez descarga el peso de YOLO:
      hacerlo con buena red, no en sitio).
- [ ] Celular(es) con IP Webcam instalada y probada (ver `guia-ip-webcam.md`).
- [ ] Cargadores y soportes para cada celular-cámara.
- [ ] App de notificaciones elegida con el cliente (ntfy o Telegram) instalada
      en el teléfono del dueño.

## En sitio — red

- [ ] Equipo de secuh conectado (idealmente por cable) y con IP fija.
- [ ] Celulares-cámara en el WiFi del negocio, con IP fija/reserva DHCP.
- [ ] Stream de cada cámara abre desde el navegador del equipo.

## En sitio — sistema

- [ ] **[A]** `docker compose up -d` y `docker compose ps` muestra el backend
      `healthy`; panel accesible desde el equipo del dueño.
- [ ] **[B]** `python run.py` arranca sin errores; panel accesible en
      `http://localhost:5173` (y la API en `:8000`).
- [ ] **[B]** Arranque automático configurado — ver "Arranque desatendido".
- [ ] Contraseña de admin entregada SOLO al dueño (no dejar por escrito).
      En la vía **[B]** la genera `run.py` y se imprime **una sola vez** al
      primer arranque: anotarla en ese momento (queda en `backend/.env`).
- [ ] Canal de notificación creado y **botón de prueba** exitoso en el
      teléfono del dueño.
- [ ] Cámaras dadas de alta, cada una con nombre claro ("Entrada", "Bodega").
- [ ] Zona de detección dibujada donde aplique (excluir calle/vitrina).
- [ ] Horario configurado según el negocio (ej. nocturno).
- [ ] Canales asignados a cada cámara.

## Prueba de fuego (con el dueño presente)

- [ ] Armar cámara → caminar frente a ella → notificación con foto en el
      teléfono del dueño en < 5 segundos.
- [ ] Ver el clip del evento desde el panel.
- [ ] Apagar el WiFi del celular-cámara → llega alerta "sin señal" →
      reencenderlo → vuelve "en línea" solo.
- [ ] Si hay mascota: verificar que NO genera alerta.
- [ ] Reiniciar el equipo completo → todo vuelve a estar armado y en línea
      sin intervención. En la vía **[B]** esto **solo pasa si se configuró el
      arranque automático** (ver más abajo): comprobarlo aquí, no darlo por
      hecho.

## Entrega

- [ ] Explicar al dueño: armar/desarmar, revisar eventos, botón de prueba.
- [ ] Entregar impresa la guía de IP Webcam.
- [ ] Acordar retención de evidencia (días) y dejarla configurada:
      `SECUH_RETENTION_DAYS` en `deploy/.env` **[A]** o en `backend/.env`
      **[B]**, y reiniciar. Cómo se aplica: runbook §8.
- [ ] Registrar en la ficha del cliente: versión instalada, cámaras, canal,
      vía de instalación (A/B) y días de retención acordados.

## Arranque desatendido

En la vía **[A]** lo resuelve el compose: `restart: unless-stopped` en ambos
servicios, y Docker arranca con el sistema.

En la vía **[B]** no hay nada equivalente — `run.py` es un proceso en primer
plano, atado a la sesión del usuario. Antes de entregar hay que darle arranque
automático a mano, con el Programador de tareas de Windows:

- [ ] Tarea nueva → "Ejecutar tanto si el usuario inició sesión como si no".
- [ ] Desencadenador: **al iniciar el equipo**.
- [ ] Acción: `python`, argumento `run.py`, "Iniciar en" = carpeta del repo.
- [ ] Configuración: reiniciar la tarea si falla (cada 1 min, 3 intentos).
- [ ] Verificado con la prueba de reinicio de la sección anterior.

Dos límites de esta vía que conviene decirle al dueño: el panel lo sirve el
servidor de desarrollo de Vite (`npm run dev`), pensado para desarrollo y no
para funcionar meses sin supervisión; y los logs quedan en la consola de la
tarea, no en un archivo rotado. Si la instalación es desatendida y crítica, la
vía **[A]** sobre Linux es la correcta.
