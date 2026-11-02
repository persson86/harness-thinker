// thinker-visual: Mermaid (ou .md com blocos ```mermaid, ou .excalidraw) →
// cena .excalidraw editável + PNG, com o tema do vault. Rodado por visual.sh
// a partir do cache com as dependências fixadas; não use direto.
import { parseArgs } from "node:util";
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { createRequire } from "node:module";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { resolveTheme } from "./theme.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const FONT_DIRS = { hand: ["Excalifont", "Excalifont"], code: ["Cascadia", "Cascadia"] };

const USAGE = `Uso: visual.sh render <entrada> --out <base> [opções]
       visual.sh check

<entrada>: .mmd (Mermaid), .md (blocos \`\`\`mermaid), .excalidraw ou - (stdin, Mermaid)
--out <base>        caminho sem extensão; gera <base>.excalidraw e <base>.png
                    (vários blocos de um .md: <base>-1, <base>-2, ...)
--block <n>         só o n-ésimo bloco mermaid do .md (1 = primeiro)
--theme <arquivo>   tema JSON; "none" = neutro. Padrão: THINKER_VISUAL_THEME,
                    depois visual-theme.json no root do vault, depois neutro
--font sans|hand|code, --roughness 0|1|2, --font-size <px>   sobrepõem o tema
--scale <n>         resolução do PNG (padrão 2)
--transparent       PNG sem fundo
--no-png            só a cena .excalidraw`;

function fail(msg, code = 2) {
  process.stderr.write(`visual: ${msg}\n`);
  process.exit(code);
}

function findBrowser() {
  const env = process.env.THINKER_VISUAL_BROWSER || process.env.EXCALIDRAW_BROWSER_PATH;
  if (env) return env;
  const candidates = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium", "/usr/bin/chromium-browser",
    "/usr/bin/microsoft-edge",
  ];
  return candidates.find((p) => existsSync(p)) ?? null;
}

function loadTheme(opt) {
  const vault = process.env.THINKER_VAULT;
  let file = opt === "none" ? null : opt || process.env.THINKER_VISUAL_THEME || null;
  if (!file && opt !== "none" && vault && existsSync(join(vault, "visual-theme.json"))) file = join(vault, "visual-theme.json");
  let partial = {};
  if (file) {
    try { partial = JSON.parse(readFileSync(file, "utf8")); } catch (e) { fail(`tema ilegível em ${file}: ${e.message}`); }
  }
  try { return { theme: resolveTheme(partial), file }; } catch (e) { fail(e.message); }
}

function mermaidBlocks(md) {
  return [...md.matchAll(/^(`{3,}|~{3,})[ \t]*mermaid[^\n]*\n([\s\S]*?)^\1[ \t]*$/gm)].map((m) => m[2]);
}

function readInputs(input, block) {
  if (input === "-") return { kind: "mermaid", sources: [readFileSync(0, "utf8")] };
  if (!existsSync(input)) fail(`entrada não encontrada: ${input}`);
  const text = readFileSync(input, "utf8");
  if (input.endsWith(".excalidraw")) return { kind: "scene", sources: [text] };
  if (input.endsWith(".md")) {
    let blocks = mermaidBlocks(text);
    if (!blocks.length) fail(`nenhum bloco \`\`\`mermaid em ${input}`);
    if (block) {
      if (block < 1 || block > blocks.length) fail(`--block ${block} fora do intervalo 1..${blocks.length}`);
      blocks = [blocks[block - 1]];
    }
    return { kind: "mermaid", sources: blocks };
  }
  return { kind: "mermaid", sources: [text] };
}

function fontPayload(font) {
  const spec = FONT_DIRS[font];
  if (!spec) return [];
  const dir = join(HERE, "node_modules", "@excalidraw", "excalidraw", "dist", "prod", "fonts", spec[0]);
  return readdirSync(dir).filter((f) => f.endsWith(".woff2"))
    .map((f) => ({ family: spec[1], data: readFileSync(join(dir, f)).toString("base64") }));
}

async function convert(sources, theme, browserPath) {
  const { chromium } = await import("playwright-core");
  const launch = browserPath ? { executablePath: browserPath } : { channel: "chrome" };
  let browser;
  try { browser = await chromium.launch(launch); } catch (e) {
    fail(`não abri o navegador (${browserPath ?? "canal chrome"}). Defina THINKER_VISUAL_BROWSER. ${e.message.split("\n")[0]}`);
  }
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.setContent("<!doctype html><html><head><meta charset='utf-8'></head><body></body></html>");
    await page.addScriptTag({ path: join(HERE, "bundle.js") });
    const fonts = fontPayload(theme.font);
    const scenes = [];
    for (const source of sources) {
      try {
        scenes.push(await page.evaluate((args) => window.thinkerVisual(args), { source, theme, fonts }));
      } catch (e) {
        const msg = e.message.replace(/^page\.evaluate: /, "").split("\n").slice(0, 4).join(" ");
        fail(`Mermaid não convertido: ${msg}${errors.length ? ` (${errors[0]})` : ""}`, 1);
      }
    }
    return scenes;
  } finally { await browser.close(); }
}

function renderPng(sceneFile, png, { scale, transparent, browserPath }) {
  const cliPkg = require.resolve("@excalidraw/cli/package.json");
  const cli = join(dirname(cliPkg), JSON.parse(readFileSync(cliPkg, "utf8")).bin.excalidraw);
  const max = String(Math.min(16384, 4096 * scale));
  const args = [cli, "render", sceneFile, "--out", png, "--scale", String(scale), "--max-width", max, "--max-height", max];
  if (transparent) args.push("--transparent");
  if (browserPath) args.push("--browser-path", browserPath);
  const r = spawnSync(process.execPath, args, { encoding: "utf8", env: { ...process.env, EXCALIDRAW_NO_UPDATE_NOTIFIER: "1" } });
  if (r.status !== 0) fail(`render falhou para ${sceneFile}: ${(r.stderr || r.stdout).trim()}`, 1);
  return JSON.parse(r.stdout);
}

async function render(argv) {
  const { values, positionals } = parseArgs({
    args: argv, allowPositionals: true,
    options: {
      out: { type: "string" }, block: { type: "string" }, theme: { type: "string" }, font: { type: "string" },
      roughness: { type: "string" }, "font-size": { type: "string" }, scale: { type: "string", default: "2" }, transparent: { type: "boolean" },
      "no-png": { type: "boolean" },
    },
  });
  if (positionals.length !== 1) fail(USAGE);
  if (!values.out) fail("--out é obrigatório");
  const scale = Number(values.scale);
  if (!(scale > 0 && scale <= 16)) fail("--scale deve ficar entre 0 e 16");
  const { theme, file: themeFile } = loadTheme(values.theme);
  if (values.font) theme.font = values.font;
  if (values.roughness !== undefined) theme.roughness = Number(values.roughness);
  if (values["font-size"] !== undefined) {
    if (!/^\d+$/.test(values["font-size"])) fail(`--font-size deve ser inteiro, veio ${values["font-size"]}`);
    theme.fontSize = Number(values["font-size"]);
  }
  try { resolveTheme(theme); } catch (e) { fail(e.message); }

  if (values.block !== undefined && !/^[1-9]\d*$/.test(values.block)) fail(`--block deve ser inteiro positivo, veio ${values.block}`);
  const { kind, sources } = readInputs(positionals[0], values.block !== undefined ? Number(values.block) : null);
  const browserPath = findBrowser();
  const scenes = kind === "scene" ? sources.map((s) => JSON.parse(s)) : await convert(sources, theme, browserPath);
  const base = resolve(values.out.replace(/\.(png|excalidraw)$/, ""));
  mkdirSync(dirname(base), { recursive: true });
  const results = scenes.map((scene, i) => {
    const stem = scenes.length > 1 ? `${base}-${i + 1}` : base;
    const sceneFile = `${stem}.excalidraw`;
    if (kind !== "scene" || resolve(positionals[0]) !== sceneFile) writeFileSync(sceneFile, JSON.stringify(scene, null, 2));
    const out = { scene: sceneFile, elements: scene.elements.length };
    if (!values["no-png"]) {
      const png = renderPng(sceneFile, `${stem}.png`, { scale, transparent: values.transparent, browserPath });
      Object.assign(out, { png: png.path, width: png.width, height: png.height });
    }
    return out;
  });
  process.stdout.write(`${JSON.stringify({ theme: theme.name, themeFile, font: theme.font, outputs: results }, null, 2)}\n`);
}

function check() {
  const browser = findBrowser();
  const report = {
    node: process.versions.node,
    browser: browser ?? "não encontrado; o canal chrome do Playwright será tentado",
    bundle: existsSync(join(HERE, "bundle.js")),
    excalidrawCli: require("@excalidraw/cli/package.json").version,
    converter: require("@excalidraw/mermaid-to-excalidraw/package.json").version,
    theme: loadTheme(undefined).file ?? "neutro",
    sandbox: process.env.THINKER_VISUAL_SANDBOX ?? process.env.CODEX_SANDBOX ?? "nenhum",
  };
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
}

const [cmd, ...rest] = process.argv.slice(2);
if (cmd === "render") await render(rest);
else if (cmd === "check") check();
else fail(USAGE, cmd && !["-h", "--help", "help"].includes(cmd) ? 2 : 0);
