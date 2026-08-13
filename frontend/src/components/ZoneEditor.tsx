import { useState, type MouseEvent } from "react";
import { api, ApiError } from "../api";
import type { Camera, Polygon } from "../types";

interface Props {
  camera: Camera;
  onSaved: () => Promise<void>;
  onClose: () => void;
}

/**
 * Editor de zona de detección: se dibuja un polígono sobre el frame actual
 * de la cámara haciendo clic. Todo fuera del polígono se ignora (movimiento
 * y personas) — útil para excluir la calle u otras áreas ajenas.
 */
export function ZoneEditor({ camera, onSaved, onClose }: Props) {
  const [points, setPoints] = useState<Polygon>(camera.mask_polygon ?? []);
  const [previewFailed, setPreviewFailed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function handleClick(event: MouseEvent<SVGSVGElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const x = (event.clientX - rect.left) / rect.width;
    const y = (event.clientY - rect.top) / rect.height;
    setPoints((prev) => [...prev, [Math.min(1, Math.max(0, x)), Math.min(1, Math.max(0, y))]]);
  }

  async function save(polygon: Polygon | null) {
    setError(null);
    setBusy(true);
    try {
      await api.cameras.setZone(camera.id, polygon);
      await onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo guardar la zona");
      setBusy(false);
    }
  }

  const svgPoints = points.map(([x, y]) => `${x * 100},${y * 100}`).join(" ");

  return (
    <div
      className="modal-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal modal-wide" role="dialog" aria-modal="true" aria-label="Zona de detección">
        <h2 className="modal-title">Zona de detección — {camera.name}</h2>
        <p className="zone-help">
          Haz clic sobre la imagen para marcar los vértices de la zona a vigilar. Lo que quede
          fuera (por ejemplo, la calle) no generará alertas.
        </p>

        <div className="zone-canvas">
          {previewFailed ? (
            <div className="zone-no-signal">
              La cámara no entrega señal en este momento. Verifica la conexión e inténtalo de
              nuevo.
            </div>
          ) : (
            <img
              src={api.cameras.previewUrl(camera.id)}
              alt={`Vista actual de ${camera.name}`}
              onError={() => setPreviewFailed(true)}
            />
          )}
          <svg
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
            onClick={handleClick}
            role="application"
            aria-label="Dibujar zona"
          >
            {points.length >= 2 && (
              <polygon points={svgPoints} className="zone-polygon" />
            )}
            {points.map(([x, y], index) => (
              <circle key={index} cx={x * 100} cy={y * 100} r={1.4} className="zone-vertex" />
            ))}
          </svg>
        </div>

        <p className="zone-status mono">
          {points.length === 0
            ? "Sin zona: se vigila el frame completo"
            : `${points.length} punto${points.length === 1 ? "" : "s"}${points.length < 3 ? " (mínimo 3)" : ""}`}
        </p>

        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}

        <div className="modal-actions">
          <button
            className="btn btn-ghost"
            onClick={() => setPoints([])}
            disabled={busy || points.length === 0}
          >
            Limpiar puntos
          </button>
          {camera.mask_polygon && (
            <button className="btn btn-ghost btn-danger" onClick={() => void save(null)} disabled={busy}>
              Quitar zona
            </button>
          )}
          <button className="btn btn-ghost" onClick={onClose} disabled={busy}>
            Cancelar
          </button>
          <button
            className="btn btn-primary"
            onClick={() => void save(points)}
            disabled={busy || points.length < 3}
          >
            {busy ? "Guardando…" : "Guardar zona"}
          </button>
        </div>
      </div>
    </div>
  );
}
