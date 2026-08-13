"""Adaptadores de captura de video (RTSP / MJPEG de IP Webcam / USB).

`source.py` implementa la interfaz ``VideoSource`` de ``secuh.core.ports``
con una sola clase sobre OpenCV para los tres tipos de fuente (reconexión con
backoff y redacción de credenciales incluidas); `worker.py` es el hilo por
cámara que la consume.
"""
