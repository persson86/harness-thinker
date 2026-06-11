#!/usr/bin/env python3
"""build-index.py — índice gerado do second-brain a partir do frontmatter.

Fonte da verdade = campo `summary:` no frontmatter de cada página. O inbox cru
(`ideias-pensamentos/inbox/`) nunca é indexado — exclusão por LOCALIZAÇÃO,
independente de ter `summary:`; só vira página indexável ao ser promovido para
fora do inbox. `search`/`graph` continuam enxergando o inbox.
Estrutura two-tier: root fino (wiki/index.md) + um shard por categoria
(wiki/[cat]/_index.md). Carregamento hierárquico: lê-se o root sempre e só
o(s) shard(s) da(s) categoria(s) relevante(s). Categorias em SUBSHARDED
(gatilho Fase 3: shard > SHARD_LINE_LIMIT) têm shard fino que aponta para
sub-shards por tipo (wiki/[cat]/_index-[type].md) — um nível a mais, mesmo
princípio.

Subcomandos:
  generate             Escreve o root + os shards a partir do frontmatter.
  check                Verifica se root+shards no disco batem com o frontmatter
                       (sincronia/idempotência) e detecta colisões de slug global.
                       Exit 0 se em sync, 1 se drift. Stop gate (check-ingest.sh).
  quality [<paths>]    Juiz determinístico de conteúdo: wikilinks quebrados nas
                       páginas especificadas (relativas a wiki/). Sem args: lê
                       paths de stdin. Exit 0 = limpo; 1 = links quebrados.
                       Chamado pelo Stop gate para páginas novas.
  search "<termos>"    Recall ranqueado por keyword (title>summary>tags>body)
                       sobre todas as páginas — grep-before-fetch para base grande.
  graph                Saúde do grafo: órfãs, sub-conectadas, links quebrados.
  stale [--days N]     Entidades/conceitos com `updated:` antigo (default 90d)
                       em esferas de movimento rápido — insumo do DREAM.
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
        ["ideias-pensamentos", "Ideias & Pensamentos", "Inbox de ideias + insights gerados pelo vault."],
    ],
    "subsharded": [],
    "fast_spheres": [],
    "inbox_dir": "ideias-pensamentos/inbox",
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


def emit_dq(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


# ---------- coleta do frontmatter ----------
def collect():
    """Coleta o frontmatter para indexação.

    Retorna (by_cat, skipped, inbox_summary):
      by_cat        {cat_slug: [(slug, summary, type)]} das páginas indexáveis.
      skipped       páginas (não-inbox) sem frontmatter ou sem summary.
      inbox_summary páginas em inbox/ que TÊM summary mas não são indexadas por
                    localização — candidatas a promoção (avisadas no generate).
    """
    by_cat = {slug: [] for slug, _d, _s in CATEGORIES}
    skipped = []
    inbox_summary = []
    for p in iter_pages():
        res = split_fm(read_file(p))
        summ = fm_get(res[0], "summary") if res is not None else None
        if is_inbox(p):
            # inbox nunca indexa; só sinalizamos as que já têm summary.
            if summ is not None:
                inbox_summary.append(os.path.relpath(p, VAULT))
            continue
        if res is None or summ is None:
            skipped.append(os.path.relpath(p, VAULT))
            continue
        by_cat.setdefault(page_category(p), []).append((slug_of(p), summ, fm_get(res[0], "type")))
    return by_cat, skipped, inbox_summary


# ---------- render (determinístico, sem timestamp) ----------
def group_by_type(items):
    by_type = {}
    for slug, summ, typ in items:
        by_type.setdefault(typ or "", []).append((slug, summ))
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
        for slug, summ in sorted(by_type[t]):
            out.append("- [[%s]] — %s" % (slug, summ))
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
    for slug, summ in sorted(entries):
        out.append("- [[%s]] — %s" % (slug, summ))
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
    by_cat, skipped, inbox_summary = collect()
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
    return 0


# ---------- check (sincronia / idempotência + colisões de slug) ----------
def slug_collisions():
    """Detecta slugs duplicados entre categorias (basename global deve ser único)."""
    seen = {}
    dupes = []
    for p in iter_pages():
        s = slug_of(p)
        rel = os.path.relpath(p, VAULT)
        if s in seen:
            dupes.append((s, seen[s], rel))
        else:
            seen[s] = rel
    return dupes


def cmd_check():
    by_cat, skipped, _inbox = collect()
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
    dupes = slug_collisions()
    for s, p1, p2 in dupes:
        drift.append("slug duplicado: '%s' em %s e %s" % (s, p1, p2))
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
    by_cat, _skipped, _inbox = collect()
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
            results.append((score, page_category(p), slug_of(p), fm_get(fm, "summary") or ""))
    results.sort(key=lambda r: (-r[0], r[1], r[2]))
    print("[search] '%s' — %d resultado(s)" % (query, len(results)))
    for score, cat, slug, summ in results[:25]:
        print("  [%d] [[%s]] (%s) — %s" % (score, slug, cat, summ))
    if len(results) > 25:
        print("  ... (+%d; refine os termos)" % (len(results) - 25))
    return 0


def cmd_graph():
    """Saúde do grafo de [[wikilinks]] (só páginas; shards/index/digests excluídos).

    Digests do DREAM (digest-*.md) são excluídos porque citam páginas como *propostas*,
    não como conhecimento real — incluí-los des-orfanizaria páginas artificialmente.
    """
    pages = {slug_of(p): p for p in iter_pages()
             if not slug_of(p).startswith("digest-")}
    outbound, inbound, dangling = {}, {}, []
    for slug, path in pages.items():
        targets = set()
        for m in WIKILINK_RE.finditer(strip_code(read_file(path))):
            t = m.group(1).split("|")[0].split("#")[0].strip()
            if t and t != slug:
                targets.add(t)
        outbound[slug] = targets
        for t in targets:
            if t in pages:
                inbound.setdefault(t, set()).add(slug)
            else:
                dangling.append((slug, t))
    n = len(pages) or 1
    valid_edges = sum(len(v) for v in inbound.values())
    orphans = sorted(s for s in pages if not inbound.get(s))
    under = sorted(s for s in pages if len(outbound.get(s, set()) | inbound.get(s, set())) < 2)
    print("[graph] %d páginas | %d links válidos | densidade %.1f/página" % (len(pages), valid_edges, valid_edges / n))
    print("  órfãs (0 inbound): %d" % len(orphans))
    for s in orphans:
        print("      - %s" % s)
    print("  sub-conectadas (<2 links): %d" % len(under))
    for s in under:
        print("      - %s" % s)
    print("  links quebrados (alvo inexistente): %d" % len(set(dangling)))
    for src, tgt in sorted(set(dangling)):
        print("      - %s -> [[%s]]" % (src, tgt))
    return 1 if dangling else 0


def cmd_stale(days):
    """Entidades/conceitos com `updated:` antigo em FAST_SPHERES — insumo do DREAM.

    Informacional (exit 0 sempre): aponta candidatos a refresh, não erros.
    """
    import datetime
    cutoff = datetime.date.today() - datetime.timedelta(days=days)
    found = []
    for p in iter_pages():
        cat = page_category(p)
        if cat not in FAST_SPHERES or is_inbox(p):
            continue
        res = split_fm(read_file(p))
        if res is None:
            continue
        fm = res[0]
        if (fm_get(fm, "type") or "") not in ("entity", "concept"):
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
    print("[stale] entity/concept sem update há >%d dias em %s" % (days, ", ".join(sorted(FAST_SPHERES))))
    print("  candidatos a refresh: %d" % len(found))
    for _d, cat, slug, info in found:
        print("      - [[%s]] (%s) — %s" % (slug, cat, info))
    return 0


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    if args[0] == "generate":
        return cmd_generate()
    if args[0] == "check":
        return cmd_check()
    if args[0] == "quality":
        paths = args[1:] if len(args) > 1 else sys.stdin.read().splitlines()
        return cmd_quality(paths)
    if args[0] == "migrate":
        return cmd_migrate("--dry-run" in args)
    if args[0] == "search":
        return cmd_search(" ".join(args[1:]))
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
