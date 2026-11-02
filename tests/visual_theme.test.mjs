// Testes das funções puras do tema de diagramas (sem rede, sem navegador).
// Uso: node --test tests/visual_theme.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { applyTheme, definedClasses, diagramType, explicitStyles, injectClasses, resolveTheme, NEUTRAL_THEME } from "../payload/harness/scripts/visual/theme.mjs";

const THEME = resolveTheme({
  font: "sans",
  corners: "sharp",
  node: { fill: "#EEEEEE", stroke: "#123456", text: "#000000" },
  decision: { fill: "#DDEEFF", stroke: "#123456" },
  edge: { stroke: "#666666", text: "#666666" },
  classes: { destaque: { fill: "#123456", stroke: "#123456", text: "#FFFFFF" } },
});

test("resolveTheme mescla sobre o neutro e preserva campos não informados", () => {
  assert.equal(THEME.roughness, NEUTRAL_THEME.roughness);
  assert.equal(THEME.decision.text, NEUTRAL_THEME.decision.text);
  assert.equal(THEME.node.stroke, "#123456");
});

test("resolveTheme recusa fonte, cor e nome de classe inválidos", () => {
  assert.throws(() => resolveTheme({ font: "comic" }), /font/);
  assert.throws(() => resolveTheme({ node: { fill: "azul" } }), /cor inválida/);
  assert.throws(() => resolveTheme({ classes: { "1x": { fill: "#fff" } } }), /classe/);
  assert.throws(() => resolveTheme({ roughness: 3 }), /roughness/);
});

test("diagramType ignora front matter e comentários", () => {
  assert.equal(diagramType("---\ntitle: X\n---\n%% nota\nflowchart LR\n A-->B"), "flowchart");
  assert.equal(diagramType("\nsequenceDiagram\n A->>B: oi"), "sequenceDiagram");
});

test("injectClasses acrescenta só classes do tema usadas e não definidas", () => {
  const src = "flowchart LR\n  A[x]:::destaque --> B[y]:::outra\n";
  const out = injectClasses(src, THEME);
  assert.match(out, /classDef destaque fill:#123456,stroke:#123456,color:#FFFFFF/);
  assert.doesNotMatch(out, /classDef outra/);
  const own = "flowchart LR\n  A:::destaque\n  classDef destaque fill:#ff0000\n";
  assert.equal(injectClasses(own, THEME), own);
  const seq = "sequenceDiagram\n  A->>B: x:::destaque\n";
  assert.equal(injectClasses(seq, THEME), seq);
});

test("classDef com vários nomes ou depois de ; conta como definido", () => {
  const semi = "flowchart LR; A:::destaque; classDef destaque fill:#ff0000";
  assert.equal(injectClasses(semi, THEME), semi);
  const multi = "flowchart LR\n  A:::destaque\n  classDef outra,destaque fill:#ff0000\n";
  assert.equal(injectClasses(multi, THEME), multi);
  assert.deepEqual([...definedClasses(multi).keys()], ["outra", "destaque"]);
});

test("explicitStyles acha style, class e :::classe por id de nó", () => {
  const src = [
    "flowchart LR",
    '  A["rótulo: x"]:::branco --> B(redondo) --> C',
    "  style B fill:#ffffff,stroke:#000000",
    "  class C,D branco",
    "  classDef branco fill:#fff,color:#000",
  ].join("\n");
  const ex = explicitStyles(src);
  assert.deepEqual([...ex.get("A")].sort(), ["color", "fill"]);
  assert.deepEqual([...ex.get("B")].sort(), ["fill", "stroke"]);
  assert.deepEqual([...ex.get("C")].sort(), ["color", "fill"]);
  assert.equal(ex.has("E"), false);
});

test("branco e preto escritos no Mermaid vencem o tema", () => {
  const src = "flowchart LR\n  A[x] --> B[y]\n  style A fill:#ffffff,stroke:#000000,color:#000000\n";
  const els = [
    { id: "A", type: "rectangle", strokeColor: "#000000", backgroundColor: "#ffffff", label: { text: "x", strokeColor: "#000000" } },
    { id: "B", type: "rectangle", strokeColor: "#1e1e1e", backgroundColor: "#ffffff", label: { text: "y" } },
  ];
  applyTheme(els, THEME, explicitStyles(src));
  assert.equal(els[0].backgroundColor, "#ffffff");
  assert.equal(els[0].strokeColor, "#000000");
  assert.equal(els[0].label.strokeColor, "#000000");
  assert.equal(els[1].backgroundColor, "#EEEEEE");
  assert.equal(els[1].strokeColor, "#123456");
});

test("classe do tema com branco sobrevive porque vira estilo escrito", () => {
  const theme = resolveTheme({ node: { fill: "#EEEEEE" }, classes: { apoio: { fill: "#FFFFFF" } } });
  const src = injectClasses("flowchart LR\n  A[x]:::apoio\n", theme);
  const [node] = applyTheme([{ id: "A", type: "rectangle", strokeColor: "#1e1e1e", backgroundColor: "#FFFFFF" }], theme, explicitStyles(src));
  assert.equal(node.backgroundColor, "#FFFFFF");
  assert.equal(node.strokeColor, NEUTRAL_THEME.node.stroke);
});

test("applyTheme pinta o que veio no padrão e respeita cor escrita no Mermaid", () => {
  const els = [
    { type: "rectangle", strokeColor: "#1e1e1e", backgroundColor: "#ffffff", roundness: { type: 3 }, label: { text: "a" } },
    { type: "rectangle", strokeColor: "#333", backgroundColor: "#ffcc00", label: { text: "b", strokeColor: "#fff" } },
    { type: "diamond", strokeColor: "#1e1e1e", backgroundColor: "transparent" },
    { type: "arrow", strokeColor: "#1e1e1e", label: { text: "c" } },
    { type: "line", strokeColor: "#999" },
    { type: "text", text: "d", strokeColor: "#000" },
  ];
  applyTheme(els, THEME);
  const [plain, styled, decision, arrow, line, text] = els;
  assert.equal(plain.backgroundColor, "#EEEEEE");
  assert.equal(plain.strokeColor, "#123456");
  assert.equal(plain.roundness, null);
  assert.equal(plain.label.fontFamily, 2);
  assert.equal(plain.label.strokeColor, "#000000");
  assert.equal(styled.backgroundColor, "#ffcc00");
  assert.equal(styled.strokeColor, "#333");
  assert.equal(styled.label.strokeColor, "#fff");
  assert.equal(decision.backgroundColor, "#DDEEFF");
  assert.equal(arrow.strokeColor, "#666666");
  assert.equal(arrow.label.strokeColor, "#666666");
  assert.equal(line.strokeColor, NEUTRAL_THEME.guide.stroke);
  assert.equal(text.fontFamily, 2);
  assert.equal(text.strokeColor, THEME.text);
});
