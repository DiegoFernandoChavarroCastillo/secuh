/**
 * Traducción de las clases COCO al español, solo para mostrar.
 *
 * El backend guarda y exporta las etiquetas en inglés a propósito: son el
 * identificador estable del dataset. Traducirlas en la base haría que retocar
 * un texto de interfaz rompiera los análisis históricos, así que el español
 * vive aquí y solo aquí.
 *
 * Las clases sin traducir se muestran tal cual: el modelo conoce 80 y no tiene
 * sentido mantener a mano un diccionario completo de cosas que no van a
 * aparecer en una casa (`toaster`, `frisbee`…).
 */
const LABELS: Record<string, { singular: string; plural: string }> = {
  person: { singular: "persona", plural: "personas" },
  dog: { singular: "perro", plural: "perros" },
  cat: { singular: "gato", plural: "gatos" },
  bird: { singular: "ave", plural: "aves" },
  car: { singular: "auto", plural: "autos" },
  motorcycle: { singular: "moto", plural: "motos" },
  bicycle: { singular: "bicicleta", plural: "bicicletas" },
  truck: { singular: "camión", plural: "camiones" },
  bus: { singular: "bus", plural: "buses" },
  backpack: { singular: "mochila", plural: "mochilas" },
  handbag: { singular: "bolso", plural: "bolsos" },
  suitcase: { singular: "maleta", plural: "maletas" },
  umbrella: { singular: "paraguas", plural: "paraguas" },
  "cell phone": { singular: "celular", plural: "celulares" },
  laptop: { singular: "portátil", plural: "portátiles" },
  bottle: { singular: "botella", plural: "botellas" },
  chair: { singular: "silla", plural: "sillas" },
  "potted plant": { singular: "planta", plural: "plantas" },
};

/** "2 perros", "1 moto", o la etiqueta cruda si no está traducida. */
export function describeCount(label: string, count: number): string {
  const entry = LABELS[label];
  if (!entry) return `${count} ${label}`;
  return `${count} ${count === 1 ? entry.singular : entry.plural}`;
}

/** Nombre en singular, para filtros y menús. */
export function describeLabel(label: string): string {
  return LABELS[label]?.singular ?? label;
}

/**
 * Orden de presentación: primero lo que importa en una casa, luego el resto
 * alfabéticamente. Sin esto el orden lo decide el modelo, que es arbitrario.
 */
const PRIORITY = [
  "person",
  "dog",
  "cat",
  "car",
  "motorcycle",
  "bicycle",
  "truck",
  "backpack",
  "handbag",
  "suitcase",
];

export function sortLabels(labels: string[]): string[] {
  return [...labels].sort((a, b) => {
    const ia = PRIORITY.indexOf(a);
    const ib = PRIORITY.indexOf(b);
    if (ia !== -1 && ib !== -1) return ia - ib;
    if (ia !== -1) return -1;
    if (ib !== -1) return 1;
    return a.localeCompare(b);
  });
}
