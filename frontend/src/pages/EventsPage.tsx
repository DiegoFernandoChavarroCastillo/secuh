import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "../api";
import { describeCount, describeLabel, sortLabels } from "../objectLabels";
import type { EventPage } from "../types";
import { useStream, type StreamStatus } from "../useStream";

// Fallback lento; los eventos nuevos llegan al instante por SSE.
const REFRESH_MS = 60000;

function formatTime(iso: string): { time: string; date: string } {
  const value = new Date(iso);
  return {
    time: value.toLocaleTimeString("es", { hour12: false }),
    date: value.toLocaleDateString("es", { day: "2-digit", month: "short" }),
  };
}

export function EventsPage() {
  const [page, setPage] = useState(1);
  const [label, setLabel] = useState<string>("");
  const [data, setData] = useState<EventPage | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setData(await api.events.list(page, undefined, label || undefined));
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Sin conexión con el sistema");
    }
  }, [page, label]);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), REFRESH_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  const lastEventId = useRef<string | null>(null);
  const onLiveStatus = useCallback(
    (status: StreamStatus) => {
      if (status.latest_event_id !== lastEventId.current) {
        lastEventId.current = status.latest_event_id;
        void refresh();
      }
    },
    [refresh],
  );
  useStream(onLiveStatus);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  // Clases presentes en la página actual, para poblar el filtro. Se toma de lo
  // que hay a la vista en vez de pedir el catálogo entero: si el filtro está
  // puesto, la opción activa se conserva aparte para poder quitarlo.
  const availableLabels = useMemo(() => {
    const found = new Set<string>();
    for (const event of data?.items ?? []) {
      for (const key of Object.keys(event.object_counts)) found.add(key);
    }
    if (label) found.add(label);
    return sortLabels([...found]);
  }, [data, label]);

  return (
    <>
      <div className="page-head">
        <h1>Eventos</h1>
        {data && <span className="page-count mono">{data.total} registrados</span>}
      </div>

      <div className="event-tools">
        <label className="event-filter">
          <span>Filtrar por objeto</span>
          <select
            value={label}
            onChange={(e) => {
              setLabel(e.target.value);
              setPage(1);
            }}
          >
            <option value="">Todos</option>
            {availableLabels.map((key) => (
              <option key={key} value={key}>
                {describeLabel(key)}
              </option>
            ))}
          </select>
        </label>
        <a
          className="btn btn-outline btn-sm"
          href={api.events.objectsCsvUrl(label || undefined)}
          download
        >
          Descargar CSV
        </a>
      </div>

      {error && (
        <p className="banner banner-error" role="alert">
          {error}
        </p>
      )}

      {data !== null && data.items.length === 0 && (
        <div className="empty">
          <p>Sin eventos registrados.</p>
          <p className="empty-hint">
            Cuando una cámara armada detecte a una persona, la evidencia aparecerá aquí.
          </p>
        </div>
      )}

      <ol className="event-log">
        {data?.items.map((event) => {
          const { time, date } = formatTime(event.timestamp);
          return (
            <li key={event.id} className="event-row">
              {event.has_snapshot ? (
                <a
                  href={api.events.snapshotUrl(event.id)}
                  target="_blank"
                  rel="noreferrer"
                  className="event-thumb-link"
                  aria-label={`Ver captura del evento en ${event.camera_name}`}
                >
                  <img
                    src={api.events.snapshotUrl(event.id)}
                    alt={`Captura de ${event.camera_name}`}
                    className="event-thumb"
                    loading="lazy"
                  />
                </a>
              ) : (
                <div className="event-thumb event-thumb-empty">sin captura</div>
              )}

              <div className="event-body">
                <p className="event-title">
                  {event.person_count === 1
                    ? "Persona detectada"
                    : `${event.person_count} personas detectadas`}
                  <span className="event-camera"> · {event.camera_name}</span>
                </p>
                <p className="event-meta mono">
                  {date} {time} · confianza {Math.round(event.confidence * 100)}%
                  {!event.notified && " · sin notificar"}
                </p>
                {Object.keys(event.object_counts).length > 0 && (
                  <ul className="event-objects" aria-label="También en la escena">
                    {sortLabels(Object.keys(event.object_counts)).map((key) => (
                      <li key={key} className="object-chip">
                        {describeCount(key, event.object_counts[key])}
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              {event.has_clip && (
                <a
                  className="btn btn-outline btn-sm"
                  href={api.events.clipUrl(event.id)}
                  target="_blank"
                  rel="noreferrer"
                >
                  Ver clip
                </a>
              )}
            </li>
          );
        })}
      </ol>

      {data !== null && totalPages > 1 && (
        <div className="pager">
          <button
            className="btn btn-ghost"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            ← Más recientes
          </button>
          <span className="mono">
            {page} / {totalPages}
          </span>
          <button
            className="btn btn-ghost"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
          >
            Más antiguos →
          </button>
        </div>
      )}
    </>
  );
}
