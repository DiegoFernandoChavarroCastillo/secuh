"""Dominio puro del sistema.

Este paquete no debe importar OpenCV, Ultralytics, FastAPI ni ninguna
librería de infraestructura: solo entidades, interfaces (puertos) y la
orquestación del pipeline. Los adaptadores concretos viven en
``secuh.detection``, ``secuh.video``, ``secuh.notifications`` y ``secuh.storage``.
"""
