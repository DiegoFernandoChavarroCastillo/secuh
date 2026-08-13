"""Adaptadores de notificación: ntfy, Telegram y consola.

`ntfy.py`, `telegram.py` y `console.py` implementan la interfaz ``Notifier``
de ``secuh.core.ports``; `factory.py` construye el notificador de cada cámara
a partir de los canales que tiene asignados en la base de datos. Añadir un
canal nuevo (correo SMTP, por ejemplo) es escribir un adaptador más y
registrarlo en la fábrica.
"""
