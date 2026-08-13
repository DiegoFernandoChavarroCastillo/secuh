# Checklist de instalación en sitio

Imprimir y completar en cada instalación. Instalación: ________________
Fecha: ____________ Técnico: ____________

## Antes de ir

- [ ] Equipo con Docker probado (el compose levanta en taller).
- [ ] `.env` generado con secretos únicos para este cliente (nunca reusar).
- [ ] Celular(es) con IP Webcam instalada y probada (ver `guia-ip-webcam.md`).
- [ ] Cargadores y soportes para cada celular-cámara.
- [ ] App de notificaciones elegida con el cliente (ntfy o Telegram) instalada
      en el teléfono del dueño.

## En sitio — red

- [ ] Equipo de secuh conectado (idealmente por cable) y con IP fija.
- [ ] Celulares-cámara en el WiFi del negocio, con IP fija/reserva DHCP.
- [ ] Stream de cada cámara abre desde el navegador del equipo.

## En sitio — sistema

- [ ] `docker compose up -d` y panel accesible desde el equipo del dueño.
- [ ] Contraseña de admin entregada SOLO al dueño (no dejar por escrito).
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
      sin intervención.

## Entrega

- [ ] Explicar al dueño: armar/desarmar, revisar eventos, botón de prueba.
- [ ] Entregar impresa la guía de IP Webcam.
- [ ] Acordar retención de evidencia (días) y dejarla configurada.
- [ ] Registrar en la ficha del cliente: versión instalada, cámaras, canal.
