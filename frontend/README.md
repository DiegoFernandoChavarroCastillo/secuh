# secuh — panel web

Panel de vigilancia (React + Vite + TypeScript). Páginas: login, cámaras
(armar/desarmar, formulario, editor de zona sobre el preview), eventos con
evidencia, y canales de notificación con botón de prueba. El estado en vivo
llega por SSE (`src/useStream.ts`).

```bash
npm install
npm run dev     # http://localhost:5173 — proxy /api -> http://localhost:8000
npm run lint
npm run build   # tsc + vite; el Dockerfile lo empaqueta dentro del backend
```

En despliegue con Docker el panel va compilado y lo sirve el propio backend en
`/` (una sola URL). `run.py`, en cambio, levanta el dev server de Vite en
`:5173` — cómodo para desarrollo, pero no pensado para dejarlo corriendo meses
sin supervisión (ver ADR 0005).

## Notas de diseño

Tipografías autoalojadas vía Fontsource: el panel debe funcionar sin internet,
en la LAN de la casa o del negocio. **IBM Plex Mono** lleva los títulos (en
versalitas) y todos los datos; **Barlow**, el texto corrido.

La dirección visual es **"Visor"**: la interfaz construida con el vocabulario
del propio detector. Tokens y componentes en `src/styles.css`, y tres reglas
que conviene no romper al añadir pantallas:

1. **El blanco es el color caliente.** Lo lleva la acción principal de cada
   pantalla y nada más.
2. **El azul (`--signal`) significa "en vivo" y solo eso.** Si además marcara
   nombres o enlaces, dejaría de significar una sola cosa. El rojo
   (`--alert`) queda igual para errores y acciones destructivas.
3. **Lo armado se distingue por peso y contraste, no por tono**: placa más
   clara, escuadras blancas más gruesas y un anillo tenue. Así se lee de reojo
   y sobrevive a un monitor mal calibrado.

La firma son las **escuadras** que encuadran tarjetas y capturas como la caja
que el detector dibuja sobre lo que encuentra; en las tarjetas de cámara se
cierran sobre el objetivo al pasar el cursor. Es el único adorno del panel:
si algo nuevo necesita destacar, que sea con jerarquía, no con otro efecto.

La API se consume solo a través de `src/api.ts`.
