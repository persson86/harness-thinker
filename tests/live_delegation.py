#!/usr/bin/env python3
"""Opt-in account smoke test. Synthetic temporary vault; no API switch or real Git push.

python3 -B tests/live_delegation.py --run --model luna --model sonnet
This is deliberately excluded from unittest discovery and tests/run.sh.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def extract_static_html(text):
    """Review one explicit HTML artifact, never append the model's delivery notes."""
    import re
    from html.parser import HTMLParser
    blocks = re.findall(r"```(?:html)?[ \t]*\n(.*?)\n```", text, flags=re.IGNORECASE | re.DOTALL)
    if len(blocks) > 1:
        return None
    code = (blocks[0] if blocks else text).strip()
    if not re.fullmatch(r"<!doctype html>\s*<html\b[\s\S]*</html>", code, flags=re.IGNORECASE):
        return None
    class InspectHTML(HTMLParser):
        def __init__(self):
            super().__init__()
            self.tags, self.external = [], []
        def handle_starttag(self, tag, attrs):
            self.tags.append(tag)
            self.external += [(k, v) for k, v in attrs if k in {"src", "href"} or k.startswith("on")]
    inspector = InspectHTML()
    inspector.feed(code)
    safe = (all(t in inspector.tags for t in ("html", "head", "body", "title"))
            and not set(inspector.tags) & {"script", "iframe", "object", "embed", "base"}
            and not inspector.external and not re.search(r"url\s*\(|@import", code, re.IGNORECASE))
    return code if safe else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Authorize real synthetic model calls using existing subscription login")
    parser.add_argument("--model", action="append", required=True)
    parser.add_argument("--scenario", choices=["summary", "html"], default="summary")
    args = parser.parse_args()
    if not args.run:
        parser.error("Live test requires explicit --run; no model was called")
    source = Path(__file__).resolve().parents[1]
    lab = Path(tempfile.mkdtemp(prefix="thinker-live-")).resolve()
    lab.chmod(0o700)
    vault, state = lab / "vault", lab / "state"
    install = subprocess.run(["bash", str(source / "install.sh"), "--init", str(vault)], capture_output=True, text=True)
    if install.returncode:
        raise RuntimeError("Isolated installation failed: " + install.stderr[-1000:])
    draft = vault / "drafts" / "synthetic.md"
    draft.parent.mkdir(exist_ok=True)
    draft.write_text("# Reunião sintética\n\nAna propôs testar a página na próxima semana. Bruno ainda não confirmou. Não existem resultados medidos.\n", encoding="utf-8")
    original = hashlib.sha256(draft.read_bytes()).hexdigest()
    brief = vault / "drafts" / "brief.md"
    instruction = ("Resuma a reunião sintética em até 70 palavras. Separe proposta, pendência e ausência de resultado medido. Inclua THINKER-SMOKE no texto. Entregue somente sua contribuição; não altere arquivos."
                   if args.scenario == "summary" else
                   "Crie uma página HTML completa e curta para apresentar esta reunião sintética, com CSS inline, duas seções Proposta e Pendência e o aviso de que não existem resultados medidos. Inclua THINKER-SMOKE no título. Sem JavaScript, links ou recursos externos. Entregue apenas o HTML (pode usar bloco de código), até 80 linhas. Não altere arquivos.")
    brief.write_text(instruction + "\n", encoding="utf-8")
    cli = [sys.executable, "-B", str(vault / "harness/scripts/delegate.py"), "--state-dir", str(state), "--session", "synthetic-smoke", "--json"]
    def call(*commands):
        result = subprocess.run(cli + list(commands), capture_output=True, text=True, timeout=60)
        try:
            data = json.loads(result.stdout if result.returncode == 0 else result.stderr)
        except ValueError:
            data = {"error": "CLI response was not JSON", "returncode": result.returncode}
        return data
    report = {"lab": str(lab), "scenario": args.scenario, "scope": "synthetic-only; existing subscription; no API fallback", "models": []}
    print(json.dumps({"lab": str(lab)}), flush=True)
    call("on")
    try:
        for model in args.model:
            print(json.dumps({"starting": model}), flush=True)
            submitted = call("submit", "--task", "transcript" if args.scenario == "summary" else "draft", "--model", model,
                             "--brief", "drafts/brief.md", "--file", "drafts/synthetic.md",
                             "--reason", "Teste sintético explícito de integração", "--timeout", "120")
            identifier = submitted.get("id")
            entry = {"requested": model, "submission": submitted}
            if identifier:
                deadline = time.monotonic() + 130
                while time.monotonic() < deadline:
                    output = call("result", identifier)
                    if output.get("state") not in {"queued", "running"}:
                        break
                    time.sleep(1)
                entry["result"] = output
                text = (output.get("result") or {}).get("text", "")
                entry["marker_received"] = "THINKER-SMOKE" in text
                if output.get("state") == "completed" and output.get("validation") == "valid":
                    entry["accepted"] = call("accept", identifier)
                    call("ack", identifier)
                    if args.scenario == "html":
                        code = extract_static_html(text)
                        entry["html_checked"] = code is not None
                        if entry["html_checked"]:
                            artifact = lab / ("reviewed-" + model + ".html")
                            artifact.write_text(code + "\n", encoding="utf-8")
                            entry["html_artifact"] = str(artifact)
            entry["original_preserved"] = original == hashlib.sha256(draft.read_bytes()).hexdigest()
            report["models"].append(entry)
            (lab / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
            print(json.dumps({"finished": model, "state": entry.get("result", {}).get("state"),
                              "error": submitted.get("error") or entry.get("result", {}).get("error"),
                              "original_preserved": entry["original_preserved"]}, ensure_ascii=False), flush=True)
        report["history"] = call("history", "--export")
    finally:
        report["off"] = call("off", "--all")
        (lab / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"report": str(lab / "report.json"), "off": not report["off"].get("enabled")}), flush=True)
    success = all(item.get("result", {}).get("state") == "completed" and item["original_preserved"]
                  and item.get("marker_received") and (args.scenario != "html" or item.get("html_checked"))
                  for item in report["models"])
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
