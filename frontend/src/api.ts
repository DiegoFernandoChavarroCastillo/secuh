import type {
  Camera,
  CameraInput,
  Channel,
  ChannelInput,
  ChannelTestResult,
  EventPage,
  Polygon,
  User,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    headers: options.body ? { "Content-Type": "application/json" } : undefined,
    credentials: "same-origin",
    ...options,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // sin cuerpo JSON: se queda el statusText
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  login: (username: string, password: string) =>
    request<User>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  logout: () => request<void>("/auth/logout", { method: "POST" }),
  me: () => request<User>("/auth/me"),

  cameras: {
    list: () => request<Camera[]>("/cameras"),
    create: (input: CameraInput) =>
      request<Camera>("/cameras", { method: "POST", body: JSON.stringify(input) }),
    update: (id: string, input: Partial<CameraInput>) =>
      request<Camera>(`/cameras/${id}`, { method: "PATCH", body: JSON.stringify(input) }),
    remove: (id: string) => request<void>(`/cameras/${id}`, { method: "DELETE" }),
    arm: (id: string) => request<Camera>(`/cameras/${id}/arm`, { method: "POST" }),
    disarm: (id: string) => request<Camera>(`/cameras/${id}/disarm`, { method: "POST" }),
    setZone: (id: string, polygon: Polygon | null) =>
      request<Camera>(`/cameras/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ mask_polygon: polygon }),
      }),
    previewUrl: (id: string) => `/api/cameras/${id}/preview`,
  },

  channels: {
    list: () => request<Channel[]>("/channels"),
    create: (input: ChannelInput) =>
      request<Channel>("/channels", { method: "POST", body: JSON.stringify(input) }),
    update: (id: string, input: Partial<ChannelInput>) =>
      request<Channel>(`/channels/${id}`, { method: "PATCH", body: JSON.stringify(input) }),
    remove: (id: string) => request<void>(`/channels/${id}`, { method: "DELETE" }),
    test: (id: string) =>
      request<ChannelTestResult>(`/channels/${id}/test`, { method: "POST" }),
  },

  events: {
    list: (page: number, cameraId?: string, label?: string) => {
      const params = new URLSearchParams({ page: String(page), page_size: "20" });
      if (cameraId) params.set("camera_id", cameraId);
      if (label) params.set("label", label);
      return request<EventPage>(`/events?${params}`);
    },
    snapshotUrl: (id: string) => `/api/events/${id}/snapshot`,
    rawSnapshotUrl: (id: string) => `/api/events/${id}/snapshot/raw`,
    clipUrl: (id: string) => `/api/events/${id}/clip`,
    objectsCsvUrl: (label?: string) =>
      `/api/events/objects.csv${label ? `?label=${encodeURIComponent(label)}` : ""}`,
  },
};
