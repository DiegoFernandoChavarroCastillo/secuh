import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, ApiError } from "../api";
import type { Camera, CameraInput, Channel, ScheduleMode, SourceType } from "../types";

const SOURCE_HINTS: Record<SourceType, string> = {
  ip_webcam: "URL que muestra la app IP Webcam, ej. http://192.168.1.50:8080/video",
  rtsp: "ej. rtsp://usuario:clave@192.168.1.60:554/stream1",
  usb: "Índice de la webcam local: 0 para la principal",
};

interface Props {
  camera: Camera | null; // null = crear nueva
  onSave: (input: CameraInput) => Promise<void>;
  onClose: () => void;
}

export function CameraForm({ camera, onSave, onClose }: Props) {
  const [form, setForm] = useState<CameraInput>({
    name: camera?.name ?? "",
    zone: camera?.zone ?? "",
    source_type: camera?.source_type ?? "ip_webcam",
    // La URL nunca se lee de vuelta (puede llevar credenciales): al editar
    // se deja vacía y solo se envía si el usuario escribe una nueva.
    source_url: "",
    confidence_threshold: camera?.confidence_threshold ?? 0.5,
    cooldown_seconds: camera?.cooldown_seconds ?? 60,
    analysis_fps: camera?.analysis_fps ?? 5,
    schedule_mode: camera?.schedule_mode ?? "always",
    schedule_start: camera?.schedule_start?.slice(0, 5) ?? null,
    schedule_end: camera?.schedule_end?.slice(0, 5) ?? null,
    channel_ids: camera?.channel_ids ?? [],
  });
  const [channels, setChannels] = useState<Channel[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.channels
      .list()
      .then(setChannels)
      .catch(() => setChannels([]));
  }, []);

  function toggleChannel(id: string) {
    setForm((prev) => ({
      ...prev,
      channel_ids: prev.channel_ids.includes(id)
        ? prev.channel_ids.filter((c) => c !== id)
        : [...prev.channel_ids, id],
    }));
  }

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  function set<K extends keyof CameraInput>(key: K, value: CameraInput[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const payload: Partial<CameraInput> = { ...form };
      if (camera && form.source_url === "") {
        // Edición sin cambiar la fuente: no enviar la URL vacía.
        delete payload.source_url;
      }
      if (payload.schedule_mode !== "custom") {
        payload.schedule_start = null;
        payload.schedule_end = null;
      }
      await onSave(payload as CameraInput);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo guardar la cámara");
      setBusy(false);
    }
  }

  return (
    <div
      className="modal-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal" role="dialog" aria-modal="true" aria-label="Datos de la cámara" ref={dialogRef}>
        <h2 className="modal-title">{camera ? `Editar ${camera.name}` : "Nueva cámara"}</h2>
        <form onSubmit={handleSubmit}>
          <label className="field">
            <span>Nombre</span>
            <input
              value={form.name}
              onChange={(e) => set("name", e.target.value)}
              placeholder="ej. Entrada"
              maxLength={64}
              autoFocus
              required
            />
          </label>

          <label className="field">
            <span>Zona / ubicación</span>
            <input
              value={form.zone}
              onChange={(e) => set("zone", e.target.value)}
              placeholder="ej. Puerta principal"
              maxLength={128}
            />
          </label>

          <label className="field">
            <span>Tipo de fuente</span>
            <select
              value={form.source_type}
              onChange={(e) => set("source_type", e.target.value as SourceType)}
            >
              <option value="ip_webcam">Celular (IP Webcam)</option>
              <option value="rtsp">Cámara IP (RTSP)</option>
              <option value="usb">Webcam USB</option>
            </select>
          </label>

          <label className="field">
            <span>Fuente de video</span>
            <input
              value={form.source_url}
              onChange={(e) => set("source_url", e.target.value)}
              placeholder={camera ? "Dejar vacío para no cambiarla" : SOURCE_HINTS[form.source_type]}
              required={!camera}
            />
            <small className="field-hint">{SOURCE_HINTS[form.source_type]}</small>
          </label>

          <label className="field">
            <span>
              Sensibilidad — <strong>{Math.round(form.confidence_threshold * 100)}%</strong>
            </span>
            <input
              type="range"
              min={0.2}
              max={0.9}
              step={0.05}
              value={form.confidence_threshold}
              onChange={(e) => set("confidence_threshold", Number(e.target.value))}
            />
            <small className="field-hint">
              Más alta = menos falsas alarmas, pero puede pasar por alto detecciones dudosas.
            </small>
          </label>

          <label className="field">
            <span>Horario de vigilancia</span>
            <select
              value={form.schedule_mode}
              onChange={(e) => set("schedule_mode", e.target.value as ScheduleMode)}
            >
              <option value="always">Siempre activa</option>
              <option value="night">Nocturno (22:00 – 06:00)</option>
              <option value="custom">Horario personalizado</option>
            </select>
            <small className="field-hint">
              Fuera del horario, la cámara armada no detecta ni graba.
            </small>
          </label>

          {form.schedule_mode === "custom" && (
            <div className="field-row">
              <label className="field">
                <span>Desde</span>
                <input
                  type="time"
                  value={form.schedule_start ?? ""}
                  onChange={(e) => set("schedule_start", e.target.value || null)}
                  required
                />
              </label>
              <label className="field">
                <span>Hasta</span>
                <input
                  type="time"
                  value={form.schedule_end ?? ""}
                  onChange={(e) => set("schedule_end", e.target.value || null)}
                  required
                />
              </label>
            </div>
          )}

          <label className="field">
            <span>Silencio entre alertas (segundos)</span>
            <input
              type="number"
              min={0}
              max={3600}
              value={form.cooldown_seconds}
              onChange={(e) => set("cooldown_seconds", Number(e.target.value))}
            />
          </label>

          {channels.length > 0 && (
            <fieldset className="field channel-picker">
              <legend>Canales de notificación</legend>
              {channels.map((channel) => (
                <label key={channel.id} className="channel-option">
                  <input
                    type="checkbox"
                    checked={form.channel_ids.includes(channel.id)}
                    onChange={() => toggleChannel(channel.id)}
                  />
                  {channel.name}
                  <span className="channel-type mono">{channel.type}</span>
                </label>
              ))}
              <small className="field-hint">
                Sin canales marcados, la cámara usa el canal global del servidor.
              </small>
            </fieldset>
          )}

          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}

          <div className="modal-actions">
            <button type="button" className="btn btn-ghost" onClick={onClose}>
              Cancelar
            </button>
            <button className="btn btn-primary" disabled={busy}>
              {busy ? "Guardando…" : "Guardar cámara"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
