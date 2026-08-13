import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api";
import { CameraForm } from "../components/CameraForm";
import { ZoneEditor } from "../components/ZoneEditor";
import type { Camera, CameraInput } from "../types";
import { useStream, type StreamStatus } from "../useStream";

// Refresco completo lento (por si otro navegador edita); el estado en vivo
// (armada / en línea) llega por SSE cada ~2 s.
const REFRESH_MS = 30000;

function scheduleLabel(camera: Camera): string {
  if (camera.schedule_mode === "night") return "Nocturno 22:00–06:00";
  if (camera.schedule_mode === "custom" && camera.schedule_start && camera.schedule_end) {
    return `${camera.schedule_start.slice(0, 5)}–${camera.schedule_end.slice(0, 5)}`;
  }
  return "Siempre";
}

export function CamerasPage() {
  const [cameras, setCameras] = useState<Camera[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Camera | "new" | null>(null);
  const [zoneEditing, setZoneEditing] = useState<Camera | null>(null);

  const refresh = useCallback(async () => {
    try {
      setCameras(await api.cameras.list());
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Sin conexión con el sistema");
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), REFRESH_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  const applyLiveStatus = useCallback((status: StreamStatus) => {
    setCameras((prev) =>
      prev === null
        ? prev
        : prev.map((camera) => {
            const live = status.cameras.find((c) => c.id === camera.id);
            return live ? { ...camera, online: live.online, state: live.state } : camera;
          }),
    );
  }, []);
  useStream(applyLiveStatus);

  async function handleSave(input: CameraInput) {
    if (editing === "new") {
      await api.cameras.create(input);
    } else if (editing) {
      await api.cameras.update(editing.id, input);
    }
    setEditing(null);
    await refresh();
  }

  async function handleDelete(camera: Camera) {
    const confirmed = window.confirm(
      `¿Eliminar la cámara "${camera.name}"? Sus eventos también se eliminarán.`,
    );
    if (!confirmed) return;
    await api.cameras.remove(camera.id);
    await refresh();
  }

  async function toggleArm(camera: Camera) {
    if (camera.state === "armed") {
      await api.cameras.disarm(camera.id);
    } else {
      await api.cameras.arm(camera.id);
    }
    await refresh();
  }

  return (
    <>
      <div className="page-head">
        <h1>Cámaras</h1>
        <button className="btn btn-primary" onClick={() => setEditing("new")}>
          Añadir cámara
        </button>
      </div>

      {error && (
        <p className="banner banner-error" role="alert">
          {error}
        </p>
      )}

      {cameras !== null && cameras.length === 0 && (
        <div className="empty">
          <p>Sin cámaras todavía.</p>
          <p className="empty-hint">
            Añade la primera: puede ser un celular con la app IP Webcam, una cámara RTSP o la
            webcam de este equipo.
          </p>
        </div>
      )}

      <div className="camera-grid">
        {cameras?.map((camera) => (
          <article
            key={camera.id}
            className={`camera-card ${camera.state === "armed" ? "is-armed" : ""}`}
          >
            <div className="camera-head">
              <div>
                <h2 className="camera-name">{camera.name}</h2>
                {camera.zone && <p className="camera-zone">{camera.zone}</p>}
              </div>
              <span
                className={`status-chip ${camera.state === "armed" ? "chip-armed" : "chip-disarmed"}`}
              >
                {camera.state === "armed" ? "Armada" : "Desarmada"}
              </span>
            </div>

            <dl className="camera-meta">
              <div>
                <dt>Señal</dt>
                <dd className={camera.online ? "online" : "offline"}>
                  <span className="signal-dot" aria-hidden="true" />
                  {camera.online ? "En línea" : camera.state === "armed" ? "Sin señal" : "—"}
                </dd>
              </div>
              <div>
                <dt>Fuente</dt>
                <dd className="mono">{camera.source_url_redacted}</dd>
              </div>
              <div>
                <dt>Sensibilidad</dt>
                <dd className="mono">{Math.round(camera.confidence_threshold * 100)}%</dd>
              </div>
              <div>
                <dt>Horario</dt>
                <dd className="mono">{scheduleLabel(camera)}</dd>
              </div>
              <div>
                <dt>Zona</dt>
                <dd className="mono">
                  {camera.mask_polygon ? `${camera.mask_polygon.length} puntos` : "frame completo"}
                </dd>
              </div>
            </dl>

            <div className="camera-actions">
              <button
                className={`btn ${camera.state === "armed" ? "btn-outline" : "btn-primary"}`}
                onClick={() => void toggleArm(camera)}
              >
                {camera.state === "armed" ? "Desarmar" : "Armar"}
              </button>
              <button className="btn btn-ghost" onClick={() => setEditing(camera)}>
                Editar
              </button>
              <button className="btn btn-ghost" onClick={() => setZoneEditing(camera)}>
                Zona
              </button>
              <button className="btn btn-ghost btn-danger" onClick={() => void handleDelete(camera)}>
                Eliminar
              </button>
            </div>
          </article>
        ))}
      </div>

      {editing !== null && (
        <CameraForm
          camera={editing === "new" ? null : editing}
          onSave={handleSave}
          onClose={() => setEditing(null)}
        />
      )}

      {zoneEditing !== null && (
        <ZoneEditor
          camera={zoneEditing}
          onSaved={refresh}
          onClose={() => setZoneEditing(null)}
        />
      )}
    </>
  );
}
