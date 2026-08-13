import { useEffect } from "react";

export interface StreamStatus {
  type: "status";
  cameras: { id: string; state: "armed" | "disarmed"; online: boolean }[];
  latest_event_id: string | null;
}

/**
 * Suscripción al estado en vivo del servidor (SSE). EventSource reconecta
 * solo si la conexión se cae; el callback debe ser estable (useCallback).
 */
export function useStream(onMessage: (status: StreamStatus) => void) {
  useEffect(() => {
    const source = new EventSource("/api/stream");
    source.onmessage = (event) => {
      try {
        onMessage(JSON.parse(event.data) as StreamStatus);
      } catch {
        // mensaje malformado: se ignora
      }
    };
    return () => source.close();
  }, [onMessage]);
}
