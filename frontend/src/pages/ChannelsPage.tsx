import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, ApiError } from "../api";
import type { Channel, ChannelType } from "../types";

const EMPTY_FORM = {
  name: "",
  type: "ntfy" as ChannelType,
  topic_url: "",
  bot_token: "",
  chat_id: "",
};

export function ChannelsPage() {
  const [channels, setChannels] = useState<Channel[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [testResults, setTestResults] = useState<Record<string, string>>({});

  const refresh = useCallback(async () => {
    try {
      setChannels(await api.channels.list());
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Sin conexión con el sistema");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    setBusy(true);
    try {
      const config: Record<string, string> =
        form.type === "ntfy"
          ? { topic_url: form.topic_url }
          : { bot_token: form.bot_token, chat_id: form.chat_id };
      await api.channels.create({ name: form.name, type: form.type, config, active: true });
      setForm(EMPTY_FORM);
      await refresh();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "No se pudo crear el canal");
    } finally {
      setBusy(false);
    }
  }

  async function handleTest(channel: Channel) {
    setTestResults((prev) => ({ ...prev, [channel.id]: "Probando…" }));
    try {
      const result = await api.channels.test(channel.id);
      setTestResults((prev) => ({
        ...prev,
        [channel.id]: result.ok
          ? "✓ Notificación de prueba enviada"
          : `✗ ${result.detail ?? "Falló el envío"}`,
      }));
    } catch (err) {
      setTestResults((prev) => ({
        ...prev,
        [channel.id]: `✗ ${err instanceof ApiError ? err.message : "Sin conexión"}`,
      }));
    }
  }

  async function handleDelete(channel: Channel) {
    if (!window.confirm(`¿Eliminar el canal "${channel.name}"?`)) return;
    await api.channels.remove(channel.id);
    await refresh();
  }

  async function toggleActive(channel: Channel) {
    await api.channels.update(channel.id, { active: !channel.active });
    await refresh();
  }

  return (
    <>
      <div className="page-head">
        <h1>Canales de notificación</h1>
      </div>

      {error && (
        <p className="banner banner-error" role="alert">
          {error}
        </p>
      )}

      <div className="channels-layout">
        <section className="channel-list">
          {channels !== null && channels.length === 0 && (
            <div className="empty">
              <p>Sin canales todavía.</p>
              <p className="empty-hint">
                Crea el primero para recibir alertas en tu teléfono: ntfy (app gratuita, sin
                registro) o un bot de Telegram.
              </p>
            </div>
          )}

          {channels?.map((channel) => (
            <article key={channel.id} className="channel-card">
              <div className="channel-head">
                <div>
                  <h2 className="channel-name">{channel.name}</h2>
                  <p className="channel-config mono">
                    {channel.type} ·{" "}
                    {Object.values(channel.config_redacted).join(" · ")}
                  </p>
                </div>
                <span
                  className={`status-chip ${channel.active ? "chip-armed" : "chip-disarmed"}`}
                >
                  {channel.active ? "Activo" : "Inactivo"}
                </span>
              </div>

              {testResults[channel.id] && (
                <p className="channel-test-result mono">{testResults[channel.id]}</p>
              )}

              <div className="camera-actions">
                <button className="btn btn-outline btn-sm" onClick={() => void handleTest(channel)}>
                  Enviar prueba
                </button>
                <button className="btn btn-ghost btn-sm" onClick={() => void toggleActive(channel)}>
                  {channel.active ? "Desactivar" : "Activar"}
                </button>
                <button
                  className="btn btn-ghost btn-sm btn-danger"
                  onClick={() => void handleDelete(channel)}
                >
                  Eliminar
                </button>
              </div>
            </article>
          ))}
        </section>

        <form className="channel-form" onSubmit={handleCreate}>
          <h2 className="modal-title">Nuevo canal</h2>

          <label className="field">
            <span>Nombre</span>
            <input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="ej. Celular de Diego"
              maxLength={64}
              required
            />
          </label>

          <label className="field">
            <span>Tipo</span>
            <select
              value={form.type}
              onChange={(e) => setForm({ ...form, type: e.target.value as ChannelType })}
            >
              <option value="ntfy">ntfy</option>
              <option value="telegram">Telegram</option>
            </select>
          </label>

          {form.type === "ntfy" ? (
            <label className="field">
              <span>URL del topic</span>
              <input
                value={form.topic_url}
                onChange={(e) => setForm({ ...form, topic_url: e.target.value })}
                placeholder="https://ntfy.sh/tu-topic-secreto"
                required
              />
              <small className="field-hint">
                Usa un nombre de topic largo y aleatorio: funciona como contraseña.
              </small>
            </label>
          ) : (
            <>
              <label className="field">
                <span>Token del bot</span>
                <input
                  value={form.bot_token}
                  onChange={(e) => setForm({ ...form, bot_token: e.target.value })}
                  placeholder="123456:ABC…"
                  required
                />
                <small className="field-hint">Créalo con @BotFather en Telegram.</small>
              </label>
              <label className="field">
                <span>Chat ID</span>
                <input
                  value={form.chat_id}
                  onChange={(e) => setForm({ ...form, chat_id: e.target.value })}
                  placeholder="ej. 123456789"
                  required
                />
              </label>
            </>
          )}

          {formError && (
            <p className="form-error" role="alert">
              {formError}
            </p>
          )}

          <button className="btn btn-primary btn-block" disabled={busy}>
            {busy ? "Creando…" : "Crear canal"}
          </button>
        </form>
      </div>
    </>
  );
}
