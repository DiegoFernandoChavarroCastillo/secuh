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

Notas de diseño: tipografías autoalojadas vía Fontsource (el panel debe
funcionar sin internet, en la LAN del negocio); tokens de color y componentes
en `src/styles.css` (ámbar = cámara armada/vigilando, verde = señal en línea,
rojo = evidencia). La API se consume solo a través de `src/api.ts`.
