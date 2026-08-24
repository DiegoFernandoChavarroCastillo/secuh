export type SourceType = "rtsp" | "ip_webcam" | "usb";
export type CameraState = "armed" | "disarmed";
export type ScheduleMode = "always" | "night" | "custom";
export type Polygon = [number, number][];

export interface Camera {
  id: string;
  name: string;
  zone: string;
  source_type: SourceType;
  source_url_redacted: string;
  state: CameraState;
  confidence_threshold: number;
  cooldown_seconds: number;
  analysis_fps: number;
  schedule_mode: ScheduleMode;
  schedule_start: string | null; // "HH:MM:SS"
  schedule_end: string | null;
  mask_polygon: Polygon | null;
  channel_ids: string[];
  online: boolean;
}

export interface CameraInput {
  name: string;
  zone: string;
  source_type: SourceType;
  source_url: string;
  confidence_threshold: number;
  cooldown_seconds: number;
  analysis_fps: number;
  schedule_mode: ScheduleMode;
  schedule_start: string | null;
  schedule_end: string | null;
  channel_ids: string[];
}

export type ChannelType = "ntfy" | "telegram";

export interface Channel {
  id: string;
  name: string;
  type: ChannelType;
  active: boolean;
  config_redacted: Record<string, string>;
}

export interface ChannelInput {
  name: string;
  type: ChannelType;
  config: Record<string, string>;
  active: boolean;
}

export interface ChannelTestResult {
  ok: boolean;
  detail: string | null;
}

export interface EventItem {
  id: string;
  camera_id: string;
  camera_name: string;
  timestamp: string;
  confidence: number;
  person_count: number;
  notified: boolean;
  has_snapshot: boolean;
  has_clip: boolean;
  /**
   * Qué más se veía en la escena, por clase. Las claves son etiquetas COCO en
   * inglés — identificadores estables del dataset; la traducción al español es
   * cosa de la interfaz (ver `objectLabels`).
   */
  object_counts: Record<string, number>;
}

export interface EventPage {
  items: EventItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface User {
  username: string;
}
