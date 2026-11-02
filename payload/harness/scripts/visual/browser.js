// Entrada do bundle que roda no Chrome headless: Mermaid → esqueleto → tema →
// elementos completos do Excalidraw, com o texto medido na fonte final.
import { parseMermaidToExcalidraw } from "@excalidraw/mermaid-to-excalidraw";
import { convertToExcalidrawElements, restoreElements } from "@excalidraw/excalidraw";
import { applyTheme, explicitStyles, injectClasses } from "./theme.mjs";

window.thinkerVisual = async ({ source, theme, fonts }) => {
  for (const { family, data } of fonts) {
    const bytes = Uint8Array.from(atob(data), (c) => c.charCodeAt(0));
    const face = new FontFace(family, bytes);
    await face.load();
    document.fonts.add(face);
  }
  await document.fonts.ready;
  const themed = injectClasses(source, theme);
  const { elements, files } = await parseMermaidToExcalidraw(themed, { themeVariables: { fontSize: `${theme.fontSize}px` } });
  applyTheme(elements, theme, explicitStyles(themed));
  const converted = convertToExcalidrawElements(elements, { regenerateIds: false });
  return {
    type: "excalidraw",
    version: 2,
    source: "thinker-visual",
    elements: restoreElements(converted, null, { refreshDimensions: true, repairBindings: true }),
    appState: { viewBackgroundColor: theme.background, gridSize: null },
    files: files ?? {},
  };
};
