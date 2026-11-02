// Tema dos diagramas: funções puras, sem dependências, usadas pelo bundle do
// navegador e pelos testes. O tema só preenche o que veio com a cor padrão do
// conversor; cor escrita no Mermaid (classDef, style) vence.

export const FONTS = { sans: 2, code: 3, hand: 5 };

export const NEUTRAL_THEME = {
  name: "neutral",
  font: "hand",
  fontSize: 20,
  roughness: 1,
  strokeWidth: 2,
  corners: "round",
  background: "#ffffff",
  text: "#1e1e1e",
  node: { fill: "#ffffff", stroke: "#1e1e1e", text: "#1e1e1e" },
  decision: { fill: "#ffffff", stroke: "#1e1e1e", text: "#1e1e1e" },
  edge: { stroke: "#1e1e1e", text: "#1e1e1e" },
  guide: { stroke: "#999999" },
  classes: {},
};

const DEFAULT_STROKES = new Set(["#1e1e1e", "#000", "#000000", "#999", "#999999"]);
const DEFAULT_FILLS = new Set(["#ffffff", "#fff", "transparent"]);
const isDefaultStroke = (c) => c === undefined || DEFAULT_STROKES.has(String(c).toLowerCase());
const isDefaultFill = (c) => c === undefined || DEFAULT_FILLS.has(String(c).toLowerCase());
const HEX = /^#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?$/;

// Mescla um tema parcial sobre o neutro e valida o que o renderer recebe.
export function resolveTheme(partial = {}) {
  const t = { ...NEUTRAL_THEME, ...partial };
  for (const k of ["node", "decision", "edge", "guide"]) t[k] = { ...NEUTRAL_THEME[k], ...(partial[k] || {}) };
  t.classes = { ...(partial.classes || {}) };
  if (!(t.font in FONTS)) throw new Error(`tema: font deve ser ${Object.keys(FONTS).join("|")}, veio ${t.font}`);
  if (!(Number.isInteger(t.fontSize) && t.fontSize >= 10 && t.fontSize <= 64)) throw new Error(`tema: fontSize deve ser inteiro entre 10 e 64, veio ${JSON.stringify(t.fontSize)}`);
  if (![0, 1, 2].includes(t.roughness)) throw new Error(`tema: roughness deve ser 0, 1 ou 2, veio ${t.roughness}`);
  if (!["round", "sharp"].includes(t.corners)) throw new Error(`tema: corners deve ser round|sharp, veio ${t.corners}`);
  const colors = [t.background, t.text, ...["node", "decision", "edge", "guide"].flatMap((k) => Object.values(t[k]))];
  for (const [name, c] of Object.entries(t.classes)) {
    if (!/^[A-Za-z][\w-]*$/.test(name)) throw new Error(`tema: nome de classe inválido: ${name}`);
    colors.push(...Object.values(c));
  }
  for (const c of colors) if (c !== "transparent" && !HEX.test(c)) throw new Error(`tema: cor inválida: ${c}`);
  return t;
}

// Tipo do diagrama: primeira linha útil depois do front matter e dos comentários.
export function diagramType(src) {
  const lines = src.split(/\r?\n/);
  let i = 0;
  if (lines[0]?.trim() === "---") { i = 1; while (i < lines.length && lines[i].trim() !== "---") i++; i++; }
  for (; i < lines.length; i++) {
    const l = lines[i].trim();
    if (!l || l.startsWith("%%")) continue;
    return l.split(/\s+/)[0];
  }
  return "";
}

// Comandos do Mermaid: linhas e trechos separados por ";" (o Mermaid aceita os dois).
const statements = (src) => src.split(/[\n;]/).map((l) => l.trim()).filter((l) => l && !l.startsWith("%%"));

// Propriedades de estilo ("fill:#fff,stroke:#000,color:#000") que importam ao tema.
function styleKeys(props) {
  const keys = new Set();
  for (const part of props.split(",")) {
    const k = part.split(":")[0]?.trim().toLowerCase();
    if (k === "fill") keys.add("fill");
    else if (k === "stroke") keys.add("stroke");
    else if (k === "color") keys.add("color");
  }
  return keys;
}

// Classes definidas no próprio Mermaid, inclusive "classDef a,b ...".
export function definedClasses(src) {
  const out = new Map();
  for (const st of statements(src)) {
    const m = st.match(/^classDef\s+([\w,-]+)\s+(.*)$/);
    if (m) for (const name of m[1].split(",")) out.set(name.trim(), styleKeys(m[2]));
  }
  return out;
}

// Nós com estilo escrito no Mermaid, por id: style, class e :::classe.
// O tema não toca essas propriedades, mesmo quando a cor escrita é branco ou preto.
export function explicitStyles(src) {
  const classes = definedClasses(src);
  const out = new Map();
  const add = (id, keys) => {
    if (!keys?.size) return;
    const cur = out.get(id) ?? new Set();
    for (const k of keys) cur.add(k);
    out.set(id, cur);
  };
  for (const st of statements(src)) {
    let m = st.match(/^style\s+([\w,-]+)\s+(.*)$/);
    if (m) { for (const id of m[1].split(",")) add(id.trim(), styleKeys(m[2])); continue; }
    m = st.match(/^class\s+([\w,-]+)\s+([\w,-]+)\s*$/);
    if (m) { for (const id of m[1].split(",")) for (const c of m[2].split(",")) add(id.trim(), classes.get(c.trim())); continue; }
    if (/^classDef\s/.test(st)) continue;
    for (const hit of st.matchAll(/([A-Za-z0-9_][\w-]*)(?:\s*[\[({>](?:"[^"]*"|[^\])}"])*[\])}]+)?:::([A-Za-z][\w-]*)/g)) {
      add(hit[1], classes.get(hit[2]));
    }
  }
  return out;
}

// Acrescenta classDef das classes do tema usadas com :::nome e não definidas
// no próprio Mermaid. Só em tipos que aceitam classDef.
export function injectClasses(src, theme) {
  const type = diagramType(src);
  if (!/^(flowchart|graph|stateDiagram(-v2)?|classDiagram)$/.test(type)) return src;
  const used = new Set([...src.matchAll(/:::([A-Za-z][\w-]*)/g)].map((m) => m[1]));
  const defined = definedClasses(src);
  const extra = [];
  for (const name of used) {
    const c = theme.classes?.[name];
    if (!c || defined.has(name)) continue;
    const parts = [c.fill && `fill:${c.fill}`, c.stroke && `stroke:${c.stroke}`, c.text && `color:${c.text}`].filter(Boolean);
    if (parts.length) extra.push(`  classDef ${name} ${parts.join(",")}`);
  }
  return extra.length ? `${src.replace(/\s*$/, "")}\n${extra.join("\n")}\n` : src;
}

const roleOf = (el) =>
  el.type === "diamond" ? "decision"
  : el.type === "arrow" ? "edge"
  : el.type === "line" ? "guide"
  : ["rectangle", "ellipse"].includes(el.type) ? "node"
  : null;

// Aplica o tema aos esqueletos do mermaid-to-excalidraw, antes da conversão,
// para que o texto seja medido já na fonte final. `explicit` (de explicitStyles)
// protege as propriedades escritas no Mermaid; sem ele, só a cor decide.
export function applyTheme(skeletons, theme, explicit = new Map()) {
  const font = FONTS[theme.font];
  for (const el of skeletons) {
    const role = roleOf(el);
    const own = explicit.get(el.id) ?? new Set();
    if (el.type === "text") {
      el.fontFamily = font;
      if (isDefaultStroke(el.strokeColor)) el.strokeColor = theme.text;
      continue;
    }
    if (!role) continue;
    const r = theme[role];
    if (!own.has("stroke") && isDefaultStroke(el.strokeColor)) el.strokeColor = r.stroke;
    if (role === "node" || role === "decision") {
      if (!own.has("fill") && isDefaultFill(el.backgroundColor)) { el.backgroundColor = r.fill; el.fillStyle = "solid"; }
      if (theme.corners === "sharp") el.roundness = null;
    }
    if (role !== "guide") el.strokeWidth = theme.strokeWidth;
    el.roughness = theme.roughness;
    if (el.label) {
      el.label.fontFamily = font;
      if (!own.has("color") && isDefaultStroke(el.label.strokeColor)) el.label.strokeColor = r.text ?? theme.text;
    }
  }
  return skeletons;
}
