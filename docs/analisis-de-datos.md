# Análisis del histórico con pandas

secuh registra, en cada evento de persona, **todo lo demás que se veía en la
escena**: la mascota, el bolso, el auto, la moto. Este documento explica el
formato de ese registro y trae recetas que funcionan tal cual.

Ver también: [`docs/architecture.md`](architecture.md) para cómo se produce el
dato, y [`docs/runbook.md`](runbook.md) §8 para las variables `SECUH_SCENE_*`.

---

## 1. Cómo sacar los datos

**Desde el panel** (o con `curl` y una sesión):

```
GET /api/events/objects.csv     una fila por objeto  ← el que quieres para analizar
GET /api/events/export.csv      una fila por evento
```

Ambos aceptan `?from=`, `?to=`, `?camera_id=` y `?label=`. Ojo al pasar fechas
con `curl`: el `+00:00` del offset hay que codificarlo como `%2B00:00`, o el
servidor lo lee como un espacio.

**Desde la máquina del servidor**, sin necesidad de que la API esté arriba:

```bash
cd backend
uv sync --group analysis                      # pandas + pyarrow, solo para esto
uv run python scripts/export_dataset.py --out ../data/analisis
```

Saca CSV y Parquet de las dos tablas. Parquet conserva los tipos y pesa menos;
CSV se abre en cualquier parte. Con `--format csv` te ahorras las dependencias.

> En Windows, si `uv` no está en el PATH: `python -m uv ...`

---

## 2. El formato

Una fila por observación (formato *largo*), que es lo que pandas espera.

| Columna | Qué es |
|---|---|
| `event_id` | Agrupa las filas de un mismo evento |
| `timestamp_utc` | ISO 8601 **con zona**, en UTC |
| `camera_name`, `camera_zone` | De dónde viene |
| `source` | `trigger` o `scene` — **lee la advertencia de abajo** |
| `label` | Clase COCO en inglés: `person`, `dog`, `car`, `motorcycle`… |
| `confidence` | 0..1 |
| `x1,y1,x2,y2` | Caja en píxeles |
| `frame_width`, `frame_height` | Resolución del frame analizado |
| `box_cx_norm`, `box_cy_norm` | Centro de la caja en 0..1 |
| `box_area_ratio` | Fracción del frame que ocupa el objeto |

### ⚠️ La regla que hay que saber antes de contar nada

La columna `source` tiene dos valores y **no se pueden sumar**:

- **`trigger`** — las personas que dispararon el evento, tal como las vio el
  pipeline de detección. Es la auditoría de por qué sonó el teléfono.
- **`scene`** — el barrido completo de la escena, que **incluye a esas mismas
  personas otra vez**.

Para contar objetos filtra por `source == "scene"`. Para auditar disparos usa
`"trigger"`. Si sumas los dos, cada persona cuenta doble.

### Otras cosas que conviene saber

- Las etiquetas van **en inglés** a propósito: son el identificador estable del
  dataset. Si se tradujeran, cualquier retoque de texto en el panel rompería
  los análisis viejos.
- Se registra **todo** lo detectado por encima de `SECUH_SCENE_MIN_CONFIDENCE`
  (0.25 por defecto), no una lista curada. Habrá ruido — un `teddy bear` que
  era un cojín. Filtra por `confidence` al analizar; el criterio se elige en el
  análisis, no en la captura.
- Las coordenadas normalizadas ya vienen calculadas, así que puedes comparar
  cámaras de resoluciones distintas sin hacer nada.
- **Las filas sobreviven a las fotos.** La retención borra imágenes a los N
  días; los registros se quedan. A las dos semanas ya no tienes la captura,
  pero sigues sabiendo que a las 20:14 hubo una persona y un auto.

---

## 3. Recetas

Punto de partida común:

```python
import pandas as pd

obj = pd.read_csv("secuh-objetos.csv", parse_dates=["timestamp_utc"])
obj["hora_local"] = obj["timestamp_utc"].dt.tz_convert("America/Bogota")
escena = obj[obj["source"] == "scene"]
```

### 3.1 ¿A qué horas pasa algo?

```python
escena.groupby(escena["hora_local"].dt.hour)["event_id"].nunique()
```

`nunique()` y no `size()`: cuenta **eventos**, no objetos, así que un evento
con cinco cosas en cuadro no pesa cinco veces.

Por día de la semana:

```python
escena.groupby(escena["hora_local"].dt.day_name())["event_id"].nunique()
```

### 3.2 ¿Con qué llega la gente?

```python
por_evento = escena.groupby("event_id")["label"].apply(set)
con_persona = por_evento[por_evento.apply(lambda s: "person" in s)]
con_persona.explode().value_counts().drop("person", errors="ignore")
```

Esto es la co-ocurrencia: de todos los eventos donde había una persona, qué más
se veía. Es la consulta que responde *"¿cuántas veces alguien llegó con un
bulto?"* — con las limitaciones de §4.

### 3.3 Vehículos por franja horaria

```python
veh = escena[escena["label"].isin(["car", "motorcycle", "truck", "bus", "bicycle"])]
veh.groupby([veh["hora_local"].dt.hour, "label"]).size().unstack(fill_value=0)
```

### 3.4 Falsos positivos probables

```python
ev = pd.read_csv("secuh-eventos.csv", parse_dates=["timestamp_utc"])
ev[ev["confidence"] < 0.6][["event_id", "timestamp_utc", "confidence"]]
```

Eventos cuya persona más segura iba justa de confianza. Es la lista con la que
decidir si subir la sensibilidad de una cámara, mirando las capturas de esos
eventos concretos.

Objetos diminutos, que suelen ser ruido:

```python
escena[escena["box_area_ratio"] < 0.005]["label"].value_counts()
```

### 3.5 ¿Cada cuánto pasa algo?

```python
ev = ev.sort_values("timestamp_utc")
(ev["timestamp_utc"].diff().dt.total_seconds() / 60).describe()
```

Minutos entre eventos consecutivos. La mediana dice cuánto ruido genera la
instalación; el mínimo, si el cooldown está bien puesto.

### Extra: mapa de calor de por dónde entra la gente

```python
personas = escena[escena["label"] == "person"]
pd.crosstab(
    pd.cut(personas["box_cy_norm"], bins=6),
    pd.cut(personas["box_cx_norm"], bins=6),
)
```

Una rejilla de 6×6 sobre el cuadro con el conteo de personas en cada celda.
Sirve para colocar la zona de detección donde de verdad pasa algo.

---

## 4. Lo que estos datos **no** pueden decirte

Vale la pena tenerlo claro antes de sacar conclusiones:

- **No hay duración.** Cada fila es un instante, el del disparo del evento. No
  se puede saber cuánto se quedó el auto ni si la persona de las 20:14 es la
  misma de las 20:16. Eso necesita seguimiento de objetos, que no está.
- **No hay identidad.** `person` es `person`; el sistema no distingue personas.
- **Un objeto quieto acaba desapareciendo.** El evento solo se dispara con
  movimiento, así que un auto parqueado desde hace rato deja de generar
  eventos. Que no aparezca en el registro no significa que no esté ahí.
- **Sesgo nocturno.** El modelo está entrenado con fotos diurnas a color; de
  noche y en infrarrojo detecta bastante peor. Menos eventos de madrugada
  pueden ser menos actividad… o el modelo viendo peor. Segmenta por hora antes
  de comparar.
- **No existe la clase "caja" ni "paquete".** COCO no la tiene. `backpack`,
  `handbag` y `suitcase` son la aproximación más cercana, y es floja.
- **Solo hay datos de cuando hubo una persona.** Si pasa un auto y no hay
  nadie, no hay evento y no hay fila.

---

## 5. Privacidad

El CSV lleva movimientos de personas por tu casa con fecha y hora. No lo subas
a ningún sitio compartido sin pensarlo, y si lo compartes para un análisis,
quita `camera_name` y `camera_zone` — bastan para reconstruir el plano de la
vivienda.
