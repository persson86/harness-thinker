#!/usr/bin/env python3
"""build-index.py — índice gerado do second-brain a partir do frontmatter.

Fonte da verdade = campo `summary:` no frontmatter de cada página. O inbox cru
(caminho configurado em `vault.config.json`) nunca é indexado — exclusão por
LOCALIZAÇÃO, independente de ter `summary:`; só vira página indexável ao ser
promovido para fora do inbox. `search`/`graph` continuam enxergando o inbox.
Estrutura two-tier: root fino (wiki/index.md) + um shard por categoria
(wiki/[cat]/_index.md). Carregamento hierárquico: lê-se o root sempre e só
o(s) shard(s) da(s) categoria(s) relevante(s). Categorias em SUBSHARDED
(gatilho Fase 3: shard > SHARD_LINE_LIMIT) têm shard fino que aponta para
sub-shards por tipo (wiki/[cat]/_index-[type].md) — um nível a mais, mesmo
princípio.

Subcomandos:
  generate             Escreve o root + os shards a partir do frontmatter.
  check                Verifica se root+shards no disco batem com o frontmatter
                       (sincronia/idempotência) e detecta colisões de slug global
                       e páginas em categoria fora do config. Exit 0 se em sync,
                       1 se drift.
  gate [--new F] [--edited F]
                       Stop gate em UMA passada (check-ingest.sh): summary nas
                       páginas novas, wikilinks quebrados em novas+editadas e
                       sincronia do índice. F = arquivo com paths relativos a
                       wiki/, um por linha. Exit 0 = limpo; 1 = bloqueio.
  health               Health-check em UMA passada (verify.sh): sincronia,
                       summaries ausentes, categorias fora do config, colisões
                       de slug (FAIL) + estatísticas de grafo (informativo).
  quality [<paths>]    Juiz determinístico de conteúdo: wikilinks quebrados nas
                       páginas especificadas (relativas a wiki/). Sem args: lê
                       paths de stdin. Exit 0 = limpo; 1 = links quebrados.
  search "<termos>"    Recall ranqueado por keyword (title>summary>tags>body)
                       sobre todas as páginas — grep-before-fetch para base grande.
  review <slug>         Referências diretas candidatas a revisão (wikilinks no
                       corpo e `sources:`), sem inferir correção automática.
  graph                Saúde do grafo: publicadas vs. inbox, ilhas e links quebrados.
  stale [--days N]     Entidades/conceitos com `updated:` antigo (default 90d)
                       em esferas de movimento rápido, mais insights em qualquer
                       esfera; ignora inbox, histórico e superado — insumo DREAM.
                       Informacional, exit 0 sempre.
  thresholds           Avisa se gatilhos adiados (Fase 3) dispararam: shard
                       > 150 linhas (sub-shard) ou > 800 páginas (FTS5).
  migrate [--dry-run]  (one-shot, Fase 1) Insere `summary:` no frontmatter a
                       partir de um index.md monolítico legado. Inerte após o
                       cutover (o root não tem entradas por página).

Sem dependências externas — o python do sistema não tem pyyaml. Saída é função
pura do frontmatter (sem timestamps) → idempotente.
"""
import json
import os
import re
import sys

# Raiz do vault: $CLAUDE_PROJECT_DIR quando o Claude Code define; senão, três
# níveis acima deste script (.claude/scripts/build-index.py → raiz do vault).
VAULT_ROOT = os.environ.get("CLAUDE_PROJECT_DIR") or os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VAULT = os.path.join(VAULT_ROOT, "wiki")
INDEX = os.path.join(VAULT, "index.md")
EXCLUDE = {"index.md", "log.md", "_index.md"}

# Configuração POR-VAULT (categorias, sub-shards, esferas rápidas, dir do inbox)
# vive em `vault.config.json` no root do vault — é dado do vault, não lógica do
# harness. Editar categorias = editar esse arquivo, nunca este script. Fallback
# neutro se ausente (vault recém-criado sem config ainda).
_DEFAULT_CONFIG = {
    "categories": [
        ["ideas", "Ideas", "Raw inbox plus generated insights."],
    ],
    "subsharded": [],
    "fast_spheres": [],
    "inbox_dir": "ideas/inbox",
}


def _load_vault_config():
    path = os.path.join(VAULT_ROOT, "vault.config.json")
    try:
        with open(path, encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (FileNotFoundError, ValueError):
        return _DEFAULT_CONFIG
    # tolerante: completa chaves ausentes com o default
    return {**_DEFAULT_CONFIG, **cfg}


_CFG = _load_vault_config()

# Inbox cru nunca é indexado — por LOCALIZAÇÃO, independente de ter `summary:`.
# (search/graph continuam vendo o inbox; só a indexação o exclui.) Per-vault.
INBOX_DIR = os.path.join(*_CFG["inbox_dir"].split("/"))

# Ordem, display name e escopo (1 linha) das categorias. Fonte: vault.config.json.
CATEGORIES = [tuple(c) for c in _CFG["categories"]]
DISPLAY_TO_SLUG = {disp: slug for slug, disp, _ in CATEGORIES}
SCOPE = {slug: scope for slug, _disp, scope in CATEGORIES}

# Categorias com shard dividido em sub-shards por tipo (_index-[type].md).
# Mecanismo EXPLÍCITO, não automático — evita flapping na fronteira do limite.
SUBSHARDED = set(_CFG["subsharded"])

TYPE_ORDER = ["concept", "entity", "source", "insight", "inbox"]
TYPE_LABEL = {"concept": "Conceitos", "entity": "Entidades", "source": "Fontes",
              "insight": "Insights", "inbox": "Inbox"}

# Gatilhos adiados na Fase 3 (ver reestruturacao-index-spec) — vigiados por `thresholds`.
SHARD_LINE_LIMIT = 150   # shard maior que isto → sub-shard da categoria por tipo
TOTAL_PAGE_LIMIT = 800   # vault maior que isto → avaliar camada FTS5

# Esferas onde conhecimento envelhece rápido — vigiadas por `stale` (insumo do DREAM).
FAST_SPHERES = set(_CFG["fast_spheres"])
STALE_DAYS = 90          # default; sobrescrevível com --days N


def iter_pages():
    for root, _, files in os.walk(VAULT):
        for fn in files:
            # _index-*.md (sub-shards gerados) não são páginas, como _index.md
            if fn.endswith(".md") and fn not in EXCLUDE and not fn.startswith("_index"):
                yield os.path.join(root, fn)


def page_category(path):
    return os.path.relpath(path, VAULT).split(os.sep)[0]


def is_inbox(path):
    return os.path.relpath(path, VAULT).startswith(INBOX_DIR + os.sep)


def slug_of(path):
    return os.path.splitext(os.path.basename(path))[0]


def read_file(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


# ---------- frontmatter (mínimo, sem pyyaml) ----------
def split_fm(text):
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return lines[1:i], i, lines
    return None


def read_scalar(raw):
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        return raw[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    if len(raw) >= 2 and raw[0] == "'" and raw[-1] == "'":
        return raw[1:-1].replace("''", "'")
    return raw


def fm_get(fm_lines, key):
    pref = key + ":"
    for ln in fm_lines:
        if ln.startswith(pref):
            return read_scalar(ln[len(pref):])
    return None


def fm_list(fm_lines, key):
    """Lê a forma simples `key: [slug, outro-slug]` do frontmatter.

    Não tenta ser um parser YAML: este comando só precisa reconhecer a forma
    canônica de `sources:` do contrato e não deve introduzir dependências.
    """
    raw = fm_get(fm_lines, key)
    if raw is None:
        return []
    raw = raw.strip()
    if not (raw.startswith("[") and raw.endswith("]")):
        return []
    return [read_scalar(value.strip()) for value in raw[1:-1].split(",")
            if value.strip()]


def knowledge_status(fm_lines):
    """Metadados opcionais; ausência nunca implica que a página seja atual."""
    status = fm_get(fm_lines, "knowledge_status")
    if status not in ("current", "historical", "superseded"):
        return None, None, None
    as_of = fm_get(fm_lines, "as_of")
    superseded_by = fm_get(fm_lines, "superseded_by")
    return status, as_of, superseded_by


def status_label(status, as_of=None, superseded_by=None):
    """Sinal humano, sem criar wikilink a um slug que talvez não exista."""
    if status is None:
        return "sem status declarado"
    labels = {"current": "atual", "historical": "histórico", "superseded": "superado"}
    parts = [labels[status]]
    if as_of:
        parts.append("estado em %s" % as_of)
    if superseded_by:
        if status == "historical":
            parts.append("estado posterior: %s" % superseded_by)
        elif status == "superseded":
            parts.append("substituído por %s" % superseded_by)
    return "; ".join(parts)


def status_badge(status, as_of=None, superseded_by=None):
    if status is None:
        return ""
    return " **[%s]**" % status_label(status, as_of, superseded_by)


def emit_dq(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


# ---------- coleta do frontmatter ----------
def load_pages():
    """Lê cada página do vault UMA vez: [(path, texto)]. Insumo comum de
    collect/graph/gate/health — evita varreduras repetidas do disco."""
    return [(p, read_file(p)) for p in iter_pages()]


def collect(pages=None):
    """Coleta o frontmatter para indexação.

    Retorna (by_cat, skipped, inbox_summary, unknown):
      by_cat        {cat_slug: [(slug, summary, type, status, as_of,
                    superseded_by)]} das páginas indexáveis.
      skipped       páginas (não-inbox) sem frontmatter ou sem summary.
      inbox_summary páginas em inbox/ que TÊM summary mas não são indexadas por
                    localização — candidatas a promoção (avisadas no generate).
      unknown       páginas indexáveis em categoria fora do vault.config.json —
                    nunca entrariam em shard algum; erro silencioso sem isto.
    """
    if pages is None:
        pages = load_pages()
    by_cat = {slug: [] for slug, _d, _s in CATEGORIES}
    skipped = []
    inbox_summary = []
    unknown = []
    for p, text in pages:
        res = split_fm(text)
        summ = fm_get(res[0], "summary") if res is not None else None
        if is_inbox(p):
            # inbox nunca indexa; só sinalizamos as que já têm summary.
            if summ is not None:
                inbox_summary.append(os.path.relpath(p, VAULT))
            continue
        if res is None or summ is None:
            skipped.append(os.path.relpath(p, VAULT))
            continue
        cat = page_category(p)
        if cat in by_cat:
            status, as_of, superseded_by = knowledge_status(res[0])
            by_cat[cat].append((slug_of(p), summ, fm_get(res[0], "type"),
                                status, as_of, superseded_by))
        else:
            unknown.append(os.path.relpath(p, VAULT))
    return by_cat, skipped, inbox_summary, unknown


# ---------- render (determinístico, sem timestamp) ----------
def group_by_type(items):
    by_type = {}
    for slug, summ, typ, status, as_of, superseded_by in items:
        by_type.setdefault(typ or "", []).append((slug, summ, status, as_of, superseded_by))
    return by_type


def type_order(by_type):
    return [t for t in TYPE_ORDER if t in by_type] + sorted(t for t in by_type if t not in TYPE_ORDER)


def type_slug(t):
    return t or "outros"


def render_shard(disp, items):
    out = ["# %s — índice" % disp, "",
           "> Shard gerado por `.claude/scripts/build-index.py` — não editar à mão.", ""]
    by_type = group_by_type(items)
    for t in type_order(by_type):
        out += ["## %s" % TYPE_LABEL.get(t, t or "Outros"), ""]
        for slug, summ, status, as_of, superseded_by in sorted(by_type[t]):
            out.append("- [[%s]] — %s%s" % (slug, summ, status_badge(status, as_of, superseded_by)))
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def render_thin_shard(disp, items):
    out = ["# %s — índice" % disp, "",
           "> Shard fino gerado por `.claude/scripts/build-index.py` — não editar à mão. "
           "Entradas nos sub-shards por tipo; carregue só o(s) relevante(s).", ""]
    by_type = group_by_type(items)
    for t in type_order(by_type):
        fn = "_index-%s.md" % type_slug(t)
        out.append("- **%s** `%d páginas` → [`%s`](%s)" % (TYPE_LABEL.get(t, t or "Outros"), len(by_type[t]), fn, fn))
    return "\n".join(out).rstrip() + "\n"


def render_subshard(disp, t, entries):
    out = ["# %s — %s" % (disp, TYPE_LABEL.get(t, t or "Outros")), "",
           "> Sub-shard gerado por `.claude/scripts/build-index.py` — não editar à mão.", ""]
    for slug, summ, status, as_of, superseded_by in sorted(entries):
        out.append("- [[%s]] — %s%s" % (slug, summ, status_badge(status, as_of, superseded_by)))
    return "\n".join(out).rstrip() + "\n"


def shard_files(slug, disp, items):
    """Arquivos gerados esperados na pasta da categoria: {basename: conteúdo}."""
    if not items:
        return {}
    if slug in SUBSHARDED:
        files = {"_index.md": render_thin_shard(disp, items)}
        by_type = group_by_type(items)
        for t in type_order(by_type):
            files["_index-%s.md" % type_slug(t)] = render_subshard(disp, t, by_type[t])
        return files
    return {"_index.md": render_shard(disp, items)}


def stale_shards(cat_dir, expected):
    """_index*.md presentes na pasta mas não esperados (type sumiu, cat saiu/entrou no SUBSHARDED)."""
    if not os.path.isdir(cat_dir):
        return []
    return [fn for fn in os.listdir(cat_dir)
            if fn.startswith("_index") and fn.endswith(".md") and fn not in expected]


def render_root(by_cat):
    out = ["# Wiki Index", "",
           "Mapa do vault. Cada esfera tem seu índice em `[categoria]/_index.md` — "
           "carregue só o(s) relevante(s) (progressive disclosure). "
           "Gerado por `.claude/scripts/build-index.py generate`; não editar à mão.", "",
           "---", ""]
    total = 0
    for slug, disp, scope in CATEGORIES:
        n = len(by_cat.get(slug, []))
        total += n
        out.append("- **%s** — %s `%d páginas` → [`%s/_index.md`](%s/_index.md)" % (disp, scope, n, slug, slug))
    out += ["", "_Total: %d páginas indexadas._" % total, ""]
    return "\n".join(out)


# ---------- generate ----------
def cmd_generate():
    by_cat, skipped, inbox_summary, unknown = collect()
    with open(INDEX, "w", encoding="utf-8") as f:
        f.write(render_root(by_cat))
    written = ["index.md (root)"]
    for slug, disp, _s in CATEGORIES:
        items = by_cat.get(slug, [])
        cat_dir = os.path.join(VAULT, slug)
        files = shard_files(slug, disp, items)
        for fn, content in files.items():
            with open(os.path.join(cat_dir, fn), "w", encoding="utf-8") as f:
                f.write(content)
        for fn in stale_shards(cat_dir, files):
            os.remove(os.path.join(cat_dir, fn))
        if files:
            label = "%s/_index.md (%d)" % (slug, len(items))
            if len(files) > 1:
                label += " + %d sub-shards" % (len(files) - 1)
            written.append(label)
    print("[generate] %d páginas indexadas em %d shards + root" % (sum(len(v) for v in by_cat.values()), len(written) - 1))
    for w in written:
        print("  - %s" % w)
    if skipped:
        print("  páginas sem summary (não indexadas): %d" % len(skipped))
        for s in sorted(skipped):
            print("      - %s" % s)
    if inbox_summary:
        print("  inbox com summary (não indexadas por localização — candidatas a promoção): %d" % len(inbox_summary))
        for s in sorted(inbox_summary):
            print("      - %s" % s)
    if unknown:
        print("  ⚠ CATEGORIA FORA DO CONFIG (páginas invisíveis ao índice): %d" % len(unknown))
        for s in sorted(unknown):
            print("      - %s" % s)
        print("      => mova para uma categoria de vault.config.json ou adicione a categoria ao config")
    return 0


# ---------- check (sincronia / idempotência + colisões de slug) ----------
def slug_collisions(pages=None):
    """Detecta slugs duplicados entre categorias (basename global deve ser único)."""
    if pages is None:
        pages = [(p, None) for p in iter_pages()]
    seen = {}
    dupes = []
    for p, _text in pages:
        s = slug_of(p)
        rel = os.path.relpath(p, VAULT)
        if s in seen:
            dupes.append((s, seen[s], rel))
        else:
            seen[s] = rel
    return dupes


def index_drift(by_cat, unknown, dupes):
    """Divergências índice <-> frontmatter + integridade estrutural (lista de strings)."""
    drift = []
    if render_root(by_cat).rstrip() != (read_file(INDEX).rstrip() if os.path.exists(INDEX) else ""):
        drift.append("index.md")
    for slug, disp, _s in CATEGORIES:
        items = by_cat.get(slug, [])
        cat_dir = os.path.join(VAULT, slug)
        files = shard_files(slug, disp, items)
        for fn, content in files.items():
            path = os.path.join(cat_dir, fn)
            if not os.path.exists(path):
                drift.append("%s/%s (ausente)" % (slug, fn))
            elif content.rstrip() != read_file(path).rstrip():
                drift.append("%s/%s" % (slug, fn))
        for fn in stale_shards(cat_dir, files):
            drift.append("%s/%s (deveria sumir)" % (slug, fn))
    for s in sorted(unknown):
        drift.append("categoria fora do config: %s (invisível ao índice)" % s)
    for s, p1, p2 in dupes:
        drift.append("slug duplicado: '%s' em %s e %s" % (s, p1, p2))
    return drift


def cmd_check():
    pages = load_pages()
    by_cat, skipped, _inbox, unknown = collect(pages)
    drift = index_drift(by_cat, unknown, slug_collisions(pages))
    print("[check] sincronia índice <-> frontmatter")
    print("  páginas indexadas: %d | sem summary (puladas): %d" % (sum(len(v) for v in by_cat.values()), len(skipped)))
    if drift:
        print("  DRIFT: %s" % ", ".join(drift))
        print("  => rode: python3 .claude/scripts/build-index.py generate")
        return 1
    print("  => EM SYNC")
    return 0


# ---------- quality (juiz determinístico de conteúdo — val_bpb do vault) ----------
def cmd_quality(rel_paths):
    """Verifica wikilinks quebrados nas páginas especificadas (paths relativos a wiki/).

    Análogo ao val_bpb de Karpathy: juiz computacional que não pode ser manipulado
    por sycophancy — detecta links inventados em vez de links existentes.
    Exit 0 = limpo; 1 = links quebrados encontrados.
    """
    all_slugs = {slug_of(p) for p in iter_pages()}
    broken = []
    checked = 0
    for rel in rel_paths:
        rel = rel.strip()
        if not rel:
            continue
        path = os.path.join(VAULT, rel)
        if not os.path.exists(path):
            continue
        checked += 1
        text = strip_code(read_file(path))
        for m in WIKILINK_RE.finditer(text):
            t = m.group(1).split("|")[0].split("#")[0].strip()
            if t and t not in all_slugs:
                broken.append((rel, t))
    print("[quality] wikilinks verificados em %d página(s)" % checked)
    if broken:
        print("  LINKS QUEBRADOS: %d" % len(broken))
        for src, tgt in sorted(broken):
            print("      - %s -> [[%s]]" % (src, tgt))
        return 1
    print("  => nenhum link quebrado")
    return 0


# ---------- thresholds (gatilhos adiados da Fase 3 se denunciam sozinhos) ----------
def cmd_thresholds():
    by_cat, _skipped, _inbox, _unknown = collect()
    total = sum(len(v) for v in by_cat.values())
    lines = {}  # "cat/arquivo" -> nº de linhas (shard cheio ou sub-shard; o fino nunca é gargalo)
    for slug, disp, _s in CATEGORIES:
        items = by_cat.get(slug, [])
        for fn, content in shard_files(slug, disp, items).items():
            if slug in SUBSHARDED and fn == "_index.md":
                continue
            lines["%s/%s" % (slug, fn)] = len(content.splitlines())
    tripped = []
    for name, n in sorted(lines.items(), key=lambda kv: -kv[1]):
        if n <= SHARD_LINE_LIMIT:
            continue
        slug = name.split("/")[0]
        if slug in SUBSHARDED:
            tripped.append("sub-shard %s: %d linhas (> %d) → avaliar divisão adicional da esfera" % (name, n, SHARD_LINE_LIMIT))
        else:
            tripped.append("shard %s: %d linhas (> %d) → adicionar '%s' a SUBSHARDED + generate [Fase 3]" % (name, n, SHARD_LINE_LIMIT, slug))
    if total > TOTAL_PAGE_LIMIT:
        tripped.append("total %d páginas (> %d) → avaliar FTS5 [Fase 3]" % (total, TOTAL_PAGE_LIMIT))
    biggest = max(lines, key=lines.get) if lines else "-"
    print("[thresholds] gatilhos adiados da Fase 3 (ver reestruturacao-index-spec)")
    print("  páginas indexadas: %d / %d (gatilho FTS5)" % (total, TOTAL_PAGE_LIMIT))
    print("  maior (sub-)shard: %s = %d / %d linhas (gatilho sub-shard)" % (biggest, lines.get(biggest, 0), SHARD_LINE_LIMIT))
    if tripped:
        print("  ⚠ GATILHO(S) DISPARADO(S):")
        for t in tripped:
            print("      - %s" % t)
        return 1
    print("  => nenhum gatilho disparado (folga ok)")
    return 0


# ---------- migrate (one-shot Fase 1; inerte após cutover) ----------
LINE_RE = re.compile(r"^- \[\[([^\]]+)\]\]\s+—\s+(.*)$")
TAG_TAIL_RE = re.compile(r"\s*`[^`]+`\s*$")
CROSSREF_RE = re.compile(r"(?i)^ver .*acima\.?$")


def strip_tags(text):
    s = text.rstrip()
    while True:
        m = TAG_TAIL_RE.search(s)
        if not m:
            return s
        s = s[:m.start()].rstrip()


def parse_index():
    cur_cat, raw = None, []
    for ln in read_file(INDEX).split("\n"):
        if ln.startswith("## "):
            cur_cat = DISPLAY_TO_SLUG.get(ln[3:].strip())
            continue
        m = LINE_RE.match(ln)
        if not m:
            continue
        slug, summary = m.group(1), strip_tags(m.group(2))
        if CROSSREF_RE.match(summary):
            continue
        raw.append((slug, summary, cur_cat))
    entries = {}
    for slug, summary, cat in raw:
        if slug not in entries or len(summary) > len(entries[slug][0]):
            entries[slug] = (summary, cat)
    return entries


def cmd_migrate(dry_run):
    entries = parse_index()
    pathmap = {}
    for p in iter_pages():
        pathmap.setdefault(slug_of(p), p)
    migrated = 0
    for slug, (summary, _c) in entries.items():
        path = pathmap.get(slug)
        if not path:
            continue
        res = split_fm(read_file(path))
        if res is None:
            continue
        _, end_idx, lines = res
        new_line = "summary: " + emit_dq(summary)
        title_pos = summary_pos = None
        for i in range(1, end_idx):
            if lines[i].startswith("title:"):
                title_pos = i
            if lines[i].startswith("summary:"):
                summary_pos = i
        if summary_pos is not None:
            lines[summary_pos] = new_line
        else:
            lines.insert((title_pos + 1) if title_pos is not None else 1, new_line)
        if not dry_run:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
        migrated += 1
    print("[migrate%s] entradas: %d | migradas: %d" % (" --dry-run" if dry_run else "", len(entries), migrated))
    return 0


WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def strip_code(text):
    """Remove blocos cercados e inline code — `[[...]]` ali (bash `[[ ]]`,
    classe regex `[[:space:]]`, exemplos de formato) não são arestas do grafo."""
    text = re.sub(r"(?s)```.*?```", " ", text)
    return re.sub(r"`[^`]*`", " ", text)


def cmd_search(query):
    """Recall ranqueado por keyword. grep-before-fetch: devolve candidatos com
    summary inline para o agente abrir só os melhores."""
    terms = [t.lower() for t in query.split() if t]
    if not terms:
        print('uso: build-index.py search "<termos>"')
        return 2
    results = []
    for p in iter_pages():
        res = split_fm(read_file(p))
        if res is None:
            continue
        fm, end_idx, lines = res
        title = (fm_get(fm, "title") or "").lower()
        summary = (fm_get(fm, "summary") or "").lower()
        tags = (fm_get(fm, "tags") or "").lower()
        body = "\n".join(lines[end_idx + 1:]).lower()
        score = 0
        for t in terms:
            score += 5 * (t in title) + 3 * (t in summary) + 2 * (t in tags) + (t in body)
        if score:
            status, as_of, superseded_by = knowledge_status(fm)
            results.append((score, page_category(p), slug_of(p), fm_get(fm, "summary") or "",
                            status, as_of, superseded_by))
    results.sort(key=lambda r: (-r[0], r[1], r[2]))
    print("[search] '%s' — %d resultado(s)" % (query, len(results)))
    for score, cat, slug, summ, status, as_of, superseded_by in results[:25]:
        print("  [%d] [[%s]] (%s) — %s%s" %
              (score, slug, cat, summ, status_badge(status, as_of, superseded_by)))
    if len(results) > 25:
        print("  ... (+%d; refine os termos)" % (len(results) - 25))
    return 0


def cmd_review(target_slug):
    """Mostra dependências candidatas que referenciam DIRETAMENTE uma página.

    A relação é apenas contexto para revisão: não prova que o conteúdo esteja
    errado, não escolhe sucessor e não modifica páginas.
    """
    pages = load_pages()
    matches = []
    for p, text in pages:
        if slug_of(p) == target_slug:
            matches.append((p, text))
    if not matches:
        print("[review] slug não encontrado: %s" % target_slug)
        return 2
    if len(matches) != 1:
        print("[review] slug ambíguo: %s (%s)" %
              (target_slug, ", ".join(sorted(os.path.relpath(p, VAULT) for p, _text in matches))))
        return 2

    target_path, target_text = matches[0]
    target_fm = split_fm(target_text)
    target_status = knowledge_status(target_fm[0]) if target_fm is not None else (None, None, None)
    references = []
    for p, text in pages:
        if p == target_path:
            continue
        res = split_fm(text)
        fm = res[0] if res is not None else []
        body = "\n".join(res[2][res[1] + 1:]) if res is not None else text
        reasons = []
        for match in WIKILINK_RE.finditer(strip_code(body)):
            linked = match.group(1).split("|")[0].split("#")[0].strip()
            if linked == target_slug:
                reasons.append("wikilink no corpo")
                break
        if target_slug in fm_list(fm, "sources"):
            reasons.append("sources no frontmatter")
        if reasons:
            status, as_of, superseded_by = knowledge_status(fm)
            references.append((page_category(p), slug_of(p), status_label(status, as_of, superseded_by), reasons))

    print("[review] [[%s]] — status: %s" %
          (target_slug, status_label(*target_status)))
    print("  referências diretas candidatas a dependência/contexto: %d" % len(references))
    print("  sinalização de contexto; não prova ou correção automática.")
    for cat, slug, status, reasons in sorted(references):
        print("      - [[%s]] (%s; %s) — %s" % (slug, cat, status, "; ".join(reasons)))
    return 0


def graph_stats(pages):
    """Arestas do grafo de [[wikilinks]] (só páginas; shards/index/digests excluídos).

    Digests do DREAM (digest-*.md) são excluídos porque citam páginas como *propostas*,
    não como conhecimento real — incluí-los des-orfanizaria páginas artificialmente.
    """
    pmap = {slug_of(p): text for p, text in pages
            if not slug_of(p).startswith("digest-")}
    outbound, inbound, dangling = {}, {}, []
    for slug, text in pmap.items():
        targets = set()
        for m in WIKILINK_RE.finditer(strip_code(text)):
            t = m.group(1).split("|")[0].split("#")[0].strip()
            if t and t != slug:
                targets.add(t)
        outbound[slug] = targets
        for t in targets:
            if t in pmap:
                inbound.setdefault(t, set()).add(slug)
            else:
                dangling.append((slug, t))
    return pmap, outbound, inbound, dangling


def graph_groups(page_rows, pmap, outbound, inbound):
    """Separa sinal editorial de rascunhos intencionalmente no inbox.

    Retorna órfãs/sub-conectadas por localização e componentes com mais de uma
    página desconectados do maior componente do vault (ilhas internas).
    """
    path_by_slug = {slug_of(p): p for p, _text in page_rows if slug_of(p) in pmap}
    nodes = set(pmap)
    inbox_slugs = {s for s, p in path_by_slug.items() if is_inbox(p)}
    published_slugs = nodes - inbox_slugs

    def connected_count(slug):
        return len((outbound.get(slug, set()) & nodes) | inbound.get(slug, set()))

    orphans = {s for s in pmap if not inbound.get(s)}
    under = {s for s in pmap if connected_count(s) < 2}

    adjacency = {
        s: (outbound.get(s, set()) & nodes) | inbound.get(s, set())
        for s in pmap
    }
    components = []
    unseen = set(nodes)
    while unseen:
        seed = min(unseen)
        component = set()
        pending = [seed]
        while pending:
            current = pending.pop()
            if current in component:
                continue
            component.add(current)
            pending.extend(sorted(adjacency[current] - component, reverse=True))
        unseen -= component
        components.append(component)
    components.sort(key=lambda c: (-len(c), sorted(c)))
    islands = [sorted(c) for c in components[1:] if len(c) > 1]

    return {
        "orphan_published": sorted(orphans & published_slugs),
        "orphan_inbox": sorted(orphans & inbox_slugs),
        "under_published": sorted(under & published_slugs),
        "under_inbox": sorted(under & inbox_slugs),
        "islands": islands,
    }


def cmd_graph():
    page_rows = load_pages()
    pages, outbound, inbound, dangling = graph_stats(page_rows)
    groups = graph_groups(page_rows, pages, outbound, inbound)
    n = len(pages) or 1
    valid_edges = sum(len(v) for v in inbound.values())
    print("[graph] %d páginas | %d links válidos | densidade %.1f/página" % (len(pages), valid_edges, valid_edges / n))
    print("  órfãs publicadas (0 inbound): %d" % len(groups["orphan_published"]))
    for s in groups["orphan_published"]:
        print("      - %s" % s)
    print("  órfãs no inbox (triagem, não erro): %d" % len(groups["orphan_inbox"]))
    for s in groups["orphan_inbox"]:
        print("      - %s" % s)
    print("  sub-conectadas publicadas (<2 links): %d" % len(groups["under_published"]))
    for s in groups["under_published"]:
        print("      - %s" % s)
    print("  sub-conectadas no inbox (<2 links): %d" % len(groups["under_inbox"]))
    for s in groups["under_inbox"]:
        print("      - %s" % s)
    print("  ilhas desconectadas do componente principal (>1 página): %d" % len(groups["islands"]))
    for component in groups["islands"]:
        print("      - %s" % " <-> ".join(component))
    print("  links quebrados (alvo inexistente): %d" % len(set(dangling)))
    for src, tgt in sorted(set(dangling)):
        print("      - %s -> [[%s]]" % (src, tgt))
    return 1 if dangling else 0


def cmd_stale(days):
    """Entidades/conceitos rápidos e insights com `updated:` antigo — insumo do DREAM.

    Histórico/superado e inbox são excluídos. Informacional (exit 0 sempre):
    aponta candidatos a refresh, não erros ou afirmações de desatualização.
    """
    import datetime
    cutoff = datetime.date.today() - datetime.timedelta(days=days)
    found = []
    for p in iter_pages():
        cat = page_category(p)
        if is_inbox(p):
            continue
        res = split_fm(read_file(p))
        if res is None:
            continue
        fm = res[0]
        typ = fm_get(fm, "type") or ""
        if not (typ == "insight" or (cat in FAST_SPHERES and typ in ("entity", "concept"))):
            continue
        status, _as_of, _superseded_by = knowledge_status(fm)
        if status in ("historical", "superseded"):
            continue
        raw_date = (fm_get(fm, "updated") or fm_get(fm, "created") or "").strip()
        try:
            upd = datetime.date.fromisoformat(raw_date)
        except ValueError:
            found.append((None, cat, slug_of(p), "updated: ilegível (%r)" % raw_date))
            continue
        if upd < cutoff:
            found.append((upd, cat, slug_of(p), "updated: %s (%d dias)" % (upd, (datetime.date.today() - upd).days)))
    found.sort(key=lambda r: (r[0] is not None, r[0] or datetime.date.min, r[1], r[2]))
    print("[stale] entity/concept em esferas rápidas e insights sem update há >%d dias" % days)
    print("  candidatos a refresh: %d" % len(found))
    for _d, cat, slug, info in found:
        print("      - [[%s]] (%s) — %s" % (slug, cat, info))
    return 0


# ---------- gate (Stop hook em UMA passada: summary + wikilinks + sincronia) ----------
def cmd_gate(args):
    """Substitui as 3 chamadas python do check-ingest.sh (config + quality + check)
    por uma só, com uma única varredura do vault. Marcadores de saída estáveis —
    o hook faz grep neles: 'SEM SUMMARY', 'LINKS QUEBRADOS', 'INDICE DESSINCRONIZADO'."""
    def read_list(flag):
        if flag not in args:
            return []
        path = args[args.index(flag) + 1]
        try:
            with open(path, encoding="utf-8") as fh:
                return sorted({ln.strip() for ln in fh if ln.strip()})
        except FileNotFoundError:
            return []
    new_rels = read_list("--new")
    edited_rels = read_list("--edited")
    pages = load_pages()
    by_rel = {os.path.relpath(p, VAULT): text for p, text in pages}
    all_slugs = {slug_of(p) for p, _t in pages}

    # 1. summary no frontmatter das páginas novas (inbox cru é isento; página
    #    criada e removida na mesma sessão também — o check de sincronia cobre).
    missing = []
    for rel in new_rels:
        if rel.startswith(INBOX_DIR + os.sep) or rel not in by_rel:
            continue
        res = split_fm(by_rel[rel])
        if res is None or fm_get(res[0], "summary") is None:
            missing.append(rel)

    # 2. wikilinks quebrados em páginas novas ou editadas (juiz determinístico).
    broken = set()
    for rel in sorted(set(new_rels) | set(edited_rels)):
        text = by_rel.get(rel)
        if text is None:
            continue
        for m in WIKILINK_RE.finditer(strip_code(text)):
            t = m.group(1).split("|")[0].split("#")[0].strip()
            if t and t not in all_slugs:
                broken.add((rel, t))

    # 3. índice em sync com o frontmatter (mesma lógica do `check`).
    by_cat, _skipped, _inbox, unknown = collect(pages)
    drift = index_drift(by_cat, unknown, slug_collisions(pages))

    print("[gate] páginas novas: %d | editadas: %d" % (len(new_rels), len(edited_rels)))
    if missing:
        print("  SEM SUMMARY: %s" % " ".join(missing))
    if broken:
        print("  LINKS QUEBRADOS: %d" % len(broken))
        for src, tgt in sorted(broken):
            print("      - %s -> [[%s]]" % (src, tgt))
    if drift:
        print("  INDICE DESSINCRONIZADO: %s" % ", ".join(drift))
    if missing or broken or drift:
        return 1
    print("  => OK")
    return 0


# ---------- health (verify.sh em UMA passada) ----------
def cmd_health():
    """Consolida check + páginas sem summary + grafo numa varredura só.

    FAIL (exit 1): drift de índice, categoria fora do config, colisão de slug,
    página indexável sem summary. Grafo (órfãs, sub-conectadas, links quebrados)
    é informativo — mesma semântica do antigo `diagnose graph` no verify.sh.
    """
    pages = load_pages()
    by_cat, skipped, _inbox, unknown = collect(pages)
    drift = index_drift(by_cat, unknown, slug_collisions(pages))
    gpages, outbound, inbound, dangling = graph_stats(pages)
    groups = graph_groups(pages, gpages, outbound, inbound)
    n = len(gpages) or 1
    valid_edges = sum(len(v) for v in inbound.values())

    print("[health] páginas indexadas: %d" % sum(len(v) for v in by_cat.values()))
    if drift:
        print("  DRIFT: %s" % ", ".join(drift))
        print("  => rode: python3 .claude/scripts/build-index.py generate")
    else:
        print("  índice: EM SYNC")
    if skipped:
        print("  SEM SUMMARY (não-inbox, fora do índice): %d" % len(skipped))
        for s in sorted(skipped):
            print("      - %s" % s)
    print("  grafo: %d links válidos | densidade %.1f/página | "
          "órfãs publicadas: %d | órfãs inbox: %d | "
          "sub-conectadas publicadas: %d | sub-conectadas inbox: %d | "
          "ilhas: %d | quebrados: %d (informativo)"
          % (valid_edges, valid_edges / n,
             len(groups["orphan_published"]), len(groups["orphan_inbox"]),
             len(groups["under_published"]), len(groups["under_inbox"]),
             len(groups["islands"]), len(set(dangling))))
    for src, tgt in sorted(set(dangling)):
        print("      - link quebrado: %s -> [[%s]]" % (src, tgt))
    return 1 if (drift or skipped) else 0


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    if args[0] == "generate":
        return cmd_generate()
    if args[0] == "check":
        return cmd_check()
    if args[0] == "gate":
        return cmd_gate(args[1:])
    if args[0] == "health":
        return cmd_health()
    if args[0] == "quality":
        paths = args[1:] if len(args) > 1 else sys.stdin.read().splitlines()
        return cmd_quality(paths)
    if args[0] == "migrate":
        return cmd_migrate("--dry-run" in args)
    if args[0] == "search":
        return cmd_search(" ".join(args[1:]))
    if args[0] == "review":
        if len(args) != 2:
            print("uso: build-index.py review <slug>")
            return 2
        return cmd_review(args[1])
    if args[0] == "graph":
        return cmd_graph()
    if args[0] == "thresholds":
        return cmd_thresholds()
    if args[0] == "stale":
        days = STALE_DAYS
        if "--days" in args:
            days = int(args[args.index("--days") + 1])
        return cmd_stale(days)
    print("subcomando desconhecido: %s" % args[0])
    return 2


if __name__ == "__main__":
    sys.exit(main())
