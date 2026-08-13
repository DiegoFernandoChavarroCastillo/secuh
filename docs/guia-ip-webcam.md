# Guía: convertir un celular Android en cámara de vigilancia

Para el cliente: cómo dejar un celular viejo funcionando como cámara de
secuh. Tiempo estimado: 10 minutos.

## 1. Instalar la app

1. Abrir **Play Store** y buscar **"IP Webcam"** (desarrollador: Pavel Khlebovich).
2. Instalar (gratuita).

## 2. Configurar

1. Abrir IP Webcam.
2. (Recomendado) En **Preferencias de video → Resolución**, elegir **640x480**:
   suficiente para detectar personas y no satura el WiFi.
3. Bajar hasta el final y tocar **Iniciar servidor**.
4. La pantalla muestra una dirección como `http://192.168.1.50:8080` —
   **anotarla**. La URL de video para secuh es esa dirección + `/video`:
   `http://192.168.1.50:8080/video`.

## 3. Dejarlo fijo

- **Corriente:** el celular queda enchufado 24/7 (el video consume batería).
- **Posición:** apuntando a la zona a vigilar (puerta, caja, bodega), firme
  (soporte o cinta doble faz), lente limpio.
- **WiFi:** misma red que el equipo donde corre secuh. Idealmente, pedir al
  router una **IP fija** para el celular (o "reserva DHCP"): si la IP cambia,
  la cámara queda sin señal hasta actualizar la URL en el panel.
- En IP Webcam → **Preferencias → Modo de arranque**, activar iniciar con el
  teléfono, por si se reinicia.

## 4. Registrar en el panel de secuh

1. Entrar al panel → **Cámaras** → **Añadir cámara**.
2. Tipo de fuente: **Celular (IP Webcam)**; fuente: la URL anotada
   (`http://…:8080/video`).
3. Guardar y **Armar**. En unos segundos debe aparecer **En línea**.
4. Caminar frente a la cámara: debe llegar la notificación con foto.

## Problemas comunes

| Problema | Solución |
|---|---|
| "Sin señal" en el panel | ¿IP Webcam sigue abierta con el servidor iniciado? ¿Misma red? Abrir la URL en un navegador para comprobar |
| La imagen se congela | Activar en IP Webcam: Preferencias → **Bloqueos** → mantener CPU activa (wake lock) |
| La IP cambió | Configurar IP fija en el router y actualizar la URL en el panel (Editar cámara) |
| Imagen muy oscura de noche | Revisar iluminación de la zona; una detección fiable necesita algo de luz |
