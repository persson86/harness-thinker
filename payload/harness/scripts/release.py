#!/usr/bin/env python3
"""Deterministic Git steps of the RELEASE operation; JSON output, no provider calls.

The agent keeps judgment (scope, plan, docs, tests, reinstall). This helper only
checks the repository, computes the next version, creates the annotated tag,
pushes branch and tag by full refs and verifies the remote.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$")


class ReleaseError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ReleaseError("invalid_input", message)


def parse_version(text):
    match = VERSION_RE.match(text.strip())
    if not match:
        raise ReleaseError("invalid_version", f"versão fora do formato X.Y.Z: {text.strip()!r}")
    major, minor, patch, suffix = match.groups()
    return int(major), int(minor), int(patch), suffix


def version_key(text):
    major, minor, patch, suffix = parse_version(text)
    # Pré-lançamento ordena antes da versão final; partes numéricas comparam como número (rc.9 < rc.14).
    parts = tuple((0, int(part), "") if part.isdigit() else (1, 0, part) for part in (suffix or "").split(".") if part)
    return (major, minor, patch, 0 if suffix else 1, parts)


def next_version(current, bump="patch"):
    major, minor, patch, suffix = parse_version(current)
    if suffix:
        return f"{major}.{minor}.{patch}"
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def git(repo, *args, check=True):
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and result.returncode != 0:
        raise ReleaseError("git_failed", f"git {' '.join(args)}: {result.stderr.strip() or result.stdout.strip()}")
    return result


def out(repo, *args):
    return git(repo, *args).stdout.strip()


def rev(repo, ref):
    result = git(repo, "rev-parse", "--verify", "--quiet", ref, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def remote_refs(repo, remote, *refs):
    listing = out(repo, "ls-remote", remote, *refs)
    found = {}
    for line in listing.splitlines():
        sha, name = line.split("\t", 1)
        found[name] = sha
    return found


def published_versions(repo, prefix):
    tags = out(repo, "tag", "--list", f"{prefix}*").splitlines()
    versions = []
    for tag in tags:
        candidate = tag[len(prefix):]
        if VERSION_RE.match(candidate):
            versions.append(candidate)
    return sorted(versions, key=version_key)


def read_current(args):
    if args.current:
        return args.current.strip()
    path = Path(args.repo) / args.version_file
    if not path.is_file():
        raise ReleaseError("missing_version_file", f"arquivo de versão ausente: {path}")
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    if not lines:
        raise ReleaseError("invalid_version", f"arquivo de versão vazio: {path}")
    return lines[0].strip()


def fetch_branch(repo, remote, branch):
    """Atualiza o rastreio da branch; remoto ainda sem a branch (primeira release) devolve None."""
    if not remote_refs(repo, remote, f"refs/heads/{branch}"):
        return None
    git(repo, "fetch", remote, f"+refs/heads/{branch}:refs/remotes/{remote}/{branch}")
    return rev(repo, f"refs/remotes/{remote}/{branch}")


def fetch_tags(repo, remote):
    result = git(repo, "fetch", remote, "--tags", check=False)
    if result.returncode != 0:
        raise ReleaseError("tag_diverged", f"tags locais divergem de {remote}: {result.stderr.strip()}")


def releasable_problems(repo, remote, prefix, version, allow_local_tag=False):
    """Política de versão, aplicada em check, tag e push."""
    problems = []
    if parse_version(version)[3]:
        problems.append(f"versão nova com sufixo de pré-lançamento: {version}")
    tag = f"{prefix}{version}"
    others = [v for v in published_versions(repo, prefix) if v != version]
    latest = others[-1] if others else None
    if latest and version_key(version) <= version_key(latest):
        problems.append(f"versão {version} não é maior que a última publicada {latest}")
    if not allow_local_tag and rev(repo, f"refs/tags/{tag}"):
        problems.append(f"tag {tag} já existe no local")
    if remote_refs(repo, remote, f"refs/tags/{tag}"):
        problems.append(f"tag {tag} já existe em {remote}")
    return problems, latest


def head_on_branch(repo, branch):
    head, tip = rev(repo, "HEAD"), rev(repo, f"refs/heads/{branch}")
    symbolic = git(repo, "symbolic-ref", "--quiet", "--short", "HEAD", check=False).stdout.strip()
    return head, tip, symbolic


def cmd_check(args):
    repo, remote, branch, prefix = args.repo, args.remote, args.branch, args.tag_prefix
    problems = []
    if remote not in out(repo, "remote").splitlines():
        raise ReleaseError("unknown_remote", f"remoto inexistente: {remote}")
    head, tip, symbolic = head_on_branch(repo, branch)
    if symbolic != branch or head != tip:
        problems.append(f"HEAD não está na ponta de {branch} (atual: {symbolic or 'detached'})")
    upstream = fetch_branch(repo, remote, branch)
    fetch_tags(repo, remote)
    behind, ahead_commits = [], []
    if upstream and head:
        behind = out(repo, "rev-list", f"HEAD..{upstream}").splitlines()
        ahead_commits = out(repo, "log", "--reverse", "--format=%H %s", f"{upstream}..HEAD").splitlines()
        if behind:
            problems.append(f"local atrás de {remote}/{branch} em {len(behind)} commit(s)")
    pending = [line for line in out(repo, "status", "--porcelain").splitlines() if line]
    current = read_current(args)
    proposed = args.version or next_version(current, args.bump)
    notes = []
    if not args.version and parse_version(current)[3] and args.bump != "patch":
        notes.append(f"--bump {args.bump} ignorado: versão com sufixo legado vira {proposed}")
    policy, latest = releasable_problems(repo, remote, prefix, proposed)
    problems.extend(policy)
    tag = f"{prefix}{proposed}"
    return {
        "ok": not problems,
        "problems": problems,
        "remote": remote,
        "branch": branch,
        "head": head,
        "current_version": current,
        "next_version": proposed,
        "tag": tag,
        "latest_published": latest,
        "remote_branch": upstream,
        "notes": notes,
        "behind": len(behind),
        "ahead": ahead_commits,
        "pending": pending,
    }


def require_aligned(repo, branch, tag=None):
    head, tip, symbolic = head_on_branch(repo, branch)
    if symbolic != branch or head != tip:
        raise ReleaseError("head_not_branch", f"HEAD precisa estar na ponta de {branch}")
    if tag is not None:
        if git(repo, "cat-file", "-t", f"refs/tags/{tag}", check=False).stdout.strip() != "tag":
            raise ReleaseError("tag_not_annotated", f"{tag} ausente ou não anotada")
        target = rev(repo, f"refs/tags/{tag}^{{}}")
        if target != head:
            raise ReleaseError("tag_mismatch", f"{tag} não aponta para HEAD ({target or 'ausente'} != {head})")
    return head


def cmd_tag(args):
    parse_version(args.version)
    tag = f"{args.tag_prefix}{args.version}"
    head = require_aligned(args.repo, args.branch)
    fetch_tags(args.repo, args.remote)
    problems, _ = releasable_problems(args.repo, args.remote, args.tag_prefix, args.version)
    if problems:
        raise ReleaseError("not_releasable", "; ".join(problems))
    message = args.message or tag
    git(args.repo, "tag", "-a", tag, "-m", message, head)
    return {"ok": True, "tag": tag, "commit": head}


def cmd_push(args):
    repo, remote, branch = args.repo, args.remote, args.branch
    tag = f"{args.tag_prefix}{args.version}"
    head = require_aligned(repo, branch, tag)
    problems, _ = releasable_problems(repo, remote, args.tag_prefix, args.version, allow_local_tag=True)
    if problems:
        raise ReleaseError("not_releasable", "; ".join(problems))
    upstream = fetch_branch(repo, remote, branch)
    if upstream and git(repo, "merge-base", "--is-ancestor", upstream, head, check=False).returncode != 0:
        raise ReleaseError("not_fast_forward", f"{remote}/{branch} não é ancestral de HEAD; push recusado")
    git(repo, "-c", "push.followTags=false", "push", remote, f"refs/heads/{branch}:refs/heads/{branch}")
    git(repo, "-c", "push.followTags=false", "push", remote, f"refs/tags/{tag}:refs/tags/{tag}")
    return {**cmd_verify(args), "pushed": [f"refs/heads/{branch}", f"refs/tags/{tag}"]}


def cmd_verify(args):
    repo, remote, branch = args.repo, args.remote, args.branch
    tag = f"{args.tag_prefix}{args.version}"
    commit = rev(repo, f"refs/tags/{tag}^{{}}")
    found = remote_refs(repo, remote, f"refs/heads/{branch}", f"refs/tags/{tag}^{{}}")
    remote_branch = found.get(f"refs/heads/{branch}")
    remote_tag = found.get(f"refs/tags/{tag}^{{}}")
    problems = []
    if not commit:
        problems.append(f"tag {tag} ausente no local")
    elif git(repo, "cat-file", "-t", f"refs/tags/{tag}", check=False).stdout.strip() != "tag":
        problems.append(f"tag {tag} não é anotada")
    if remote_branch != commit:
        problems.append(f"{remote}/{branch} em {remote_branch or 'ausente'}, esperado {commit}")
    if remote_tag != commit:
        problems.append(f"{tag} em {remote} aponta para {remote_tag or 'ausente'}, esperado {commit}")
    return {"ok": not problems, "problems": problems, "tag": tag, "commit": commit,
            "remote_branch": remote_branch, "remote_tag": remote_tag}


def cmd_next(args):
    return {"ok": True, "current_version": args.current_version,
            "next_version": next_version(args.current_version, args.bump)}


def parser():
    root = Parser(description="Passos Git determinísticos da operação RELEASE.")
    root.add_argument("--repo", default=".")
    root.add_argument("--remote", default="origin")
    root.add_argument("--branch", default="main")
    root.add_argument("--tag-prefix", default="v")
    commands = root.add_subparsers(dest="command", required=True, parser_class=Parser)
    nxt = commands.add_parser("next-version")
    nxt.add_argument("current_version")
    nxt.add_argument("--bump", choices=("patch", "minor", "major"), default="patch")
    check = commands.add_parser("check")
    check.add_argument("--version-file", default="VERSION")
    check.add_argument("--current", help="versão atual quando não vive num arquivo de texto simples")
    check.add_argument("--version", help="versão nova escolhida; padrão: próxima pelo --bump")
    check.add_argument("--bump", choices=("patch", "minor", "major"), default="patch")
    tag = commands.add_parser("tag")
    tag.add_argument("--version", required=True)
    tag.add_argument("--message")
    for name in ("push", "verify"):
        command = commands.add_parser(name)
        command.add_argument("--version", required=True)
    return root


HANDLERS = {"next-version": cmd_next, "check": cmd_check, "tag": cmd_tag, "push": cmd_push, "verify": cmd_verify}


def main(argv=None):
    try:
        args = parser().parse_args(argv)
        result = HANDLERS[args.command](args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1
    except ReleaseError as error:
        print(json.dumps({"ok": False, "error": error.code, "message": error.message}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    sys.exit(main())
