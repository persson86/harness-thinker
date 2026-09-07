"""Fail-closed preparation for a proposal-only Grok worker.

Grok 1.0.13 discovers Claude plugins even when Claude compatibility hooks are
disabled.  The runtime honors project ``[plugins].disabled``, but ``inspect``
reports raw discoveries instead of the active registry in this release.  This
module therefore pins the inspected binary, writes a private project config,
and records that narrow source-asserted qualification.  It never copies or
returns authentication material.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
from typing import Dict, Iterable, List, Mapping, Optional, Tuple

try:  # Python 3.11+
    import tomllib as _toml
except ImportError:  # pragma: no cover - exercised by the supported Python 3.9 runtime
    try:
        from ._vendor import tomli as _toml
    except ImportError:  # standalone import used by the detached worker
        from _vendor import tomli as _toml


class GrokIsolationError(ValueError):
    pass


PINNED_VERSION = "1.0.13"
PINNED_FINGERPRINT = "grok 1.0.13 (5e9a58528b76) [stable]"
QUALIFICATION_SOURCE = (
    "https://github.com/xai-org/grok-build/tree/"
    "72a61251fcffb464bcc687aeb5a998e5a98ec0c9"
)
INSPECT_TIMEOUT = 15
MAX_CONFIG_BYTES = 1024 * 1024
_CONFIG_ROLES = {
    "system-managed", "managed", "user", "requirements",
    "system-requirements", "mdm",
}
_BAD_NOTE = re.compile(r"parse|error|malform|unread|ignored", re.I)
_ABSENT_NOTE = re.compile(r"not[ -]?found|does not exist|missing|absent", re.I)
_BENIGN_WARNINGS = ({
    "target": "configKey",
    "path": "privacy",
    "kind": "unknown-field",
    "reason": "unrecognized config key",
},)
_FORBIDDEN_ROOTS = {
    "auth", "authentication", "credentials", "endpoints", "login", "model",
    "model_providers",
}
_FORBIDDEN_KEYS = {
    "api_backend", "api_key", "auth_mode", "auth_scope", "base_url",
    "bearer_token", "credential", "credentials", "env_http_headers", "env_key",
    "extra_headers", "force_login_team_uuid", "model_id", "model_provider",
    "models_base_url", "models_list_url", "oidc_issuer", "primary_model",
    "query_params", "refresh_token", "selected_model", "token", "token_header",
}
_SELECTED_MODEL_KEYS = {"default", "default_model", "selected", "web_search"}
_REQUIRED_ENV = {
    "GROK_DISABLE_API_KEY_AUTH": "1",
    "GROK_DISABLE_AUTOUPDATER": "1",
    "GROK_MEMORY": "0",
    "GROK_SUBAGENTS": "0",
    "GROK_WRITE_FILE": "0",
    "GROK_TOOL_SEARCH": "0",
    "GROK_LSP_TOOLS": "0",
    "GROK_WEB_FETCH": "0",
}
_FORBIDDEN_ENV = {
    "XAI_API_KEY", "GROK_API_KEY", "GROK_MODELS_BASE_URL",
    "GROK_MODELS_LIST_URL",
}


def _fail(message: str) -> None:
    raise GrokIsolationError(message)


def _binary(profile: Mapping[str, object]) -> str:
    candidate = profile.get("binary") or shutil.which("grok")
    if not isinstance(candidate, str) or not candidate:
        _fail("CLI Grok indisponivel.")
    path = Path(candidate).expanduser().resolve()
    if not path.is_file() or not os.access(str(path), os.X_OK):
        _fail("Executavel Grok invalido.")
    return str(path)


def _private_workspace(workspace: Path) -> Path:
    if workspace.is_symlink() or not workspace.is_dir():
        _fail("Workspace Grok deve ser um diretorio real.")
    info = workspace.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        _fail("Workspace Grok deve pertencer ao usuario e usar modo 0700.")
    if (workspace / ".git").exists():
        _fail("Workspace Grok isolado nao pode ser um repositorio Git.")
    if (workspace / ".grok").exists():
        _fail("Workspace Grok ja contem configuracao local.")
    return workspace.resolve()


def _preserved_homes(env: Mapping[str, str]) -> Path:
    home = os.environ.get("HOME")
    if not home or env.get("HOME") != home:
        _fail("HOME deve ser preservado para autenticacao da assinatura.")
    inherited_grok = os.environ.get("GROK_HOME")
    if env.get("GROK_HOME") != inherited_grok:
        _fail("GROK_HOME deve ser preservado; realocacao de credenciais recusada.")
    for key, value in _REQUIRED_ENV.items():
        if env.get(key) != value:
            _fail("Ambiente Grok nao preservou todos os controles obrigatorios.")
    for product in ("CURSOR", "CLAUDE", "CODEX"):
        for kind in ("SKILLS", "RULES", "AGENTS", "MCPS", "HOOKS"):
            if env.get("GROK_" + product + "_" + kind + "_ENABLED") != "0":
                _fail("Compatibilidade executavel Grok nao foi integralmente desligada.")
    if any(env.get(key) for key in _FORBIDDEN_ENV):
        _fail("Ambiente Grok contem override de API ou endpoint nao permitido.")
    if env.get("GROK_CONFIG") is not None:
        _fail("GROK_CONFIG nao e aceito; o isolamento usa apenas o arquivo privado verificado.")
    return Path(inherited_grok) if inherited_grok else Path(home) / ".grok"


def _run(argv: List[str], workspace: Path, env: Mapping[str, str]) -> str:
    try:
        result = subprocess.run(argv, cwd=str(workspace), env=dict(env),
                                text=True, capture_output=True,
                                timeout=INSPECT_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise GrokIsolationError("Preflight Grok nao concluiu no prazo.") from error
    if result.returncode:
        _fail("Preflight Grok encerrou com erro.")
    return result.stdout


def _json_report(binary: str, workspace: Path,
                 env: Mapping[str, str]) -> Dict[str, object]:
    raw = _run([binary, "inspect", "--json"], workspace, env)
    try:
        report = json.loads(raw)
    except (TypeError, ValueError) as error:
        raise GrokIsolationError("Inspect Grok nao devolveu JSON valido.") from error
    if not isinstance(report, dict):
        _fail("Inspect Grok devolveu estrutura invalida.")
    if report.get("grokVersion") != PINNED_VERSION:
        _fail("Versao Grok fora do pin 1.0.13; isolamento nao qualificado.")
    login = report.get("loginPolicy")
    if not isinstance(login, dict) or login.get("apiKeyAuthDisabled") is not True \
            or login.get("disableApiKeyAuth") is not True:
        _fail("Inspect nao confirmou o bloqueio efetivo de API key.")
    warnings = report.get("configWarnings", [])
    if not isinstance(warnings, list) or any(warning not in _BENIGN_WARNINGS
                                             for warning in warnings):
        _fail("Configuracao Grok contem aviso que afeta a qualificacao.")
    if report.get("mcpConfigProblems"):
        _fail("Configuracao MCP Grok e invalida.")
    return report


def _layers(report: Mapping[str, object]) -> List[Dict[str, object]]:
    sources = report.get("configSources")
    rows = sources.get("layers") if isinstance(sources, dict) else None
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        _fail("Inspect nao informou fontes de configuracao validas.")
    return rows  # type: ignore[return-value]


def _normalize_key(value: object) -> str:
    return str(value).strip().lower().replace("-", "_")


def _validate_config_values(config: Mapping[str, object]) -> None:
    """Reject routing/auth overrides while allowing ordinary UI preferences."""
    roots = {_normalize_key(key) for key in config}
    if roots & _FORBIDDEN_ROOTS:
        _fail("Fonte Grok redefine autenticacao, endpoint, provedor ou modelos.")

    def walk(value: object, path: Tuple[str, ...]) -> None:
        if isinstance(value, list):
            for child in value:
                walk(child, path)
            return
        if not isinstance(value, dict):
            return
        for raw_key, child in value.items():
            key = _normalize_key(raw_key)
            child_path = path + (key,)
            if key in _FORBIDDEN_KEYS or re.search(
                    r"(?:api|auth|access|bearer|secret|credential)_(?:key|token)$", key):
                _fail("Fonte Grok contem helper de autenticacao ou endpoint.")
            if (path and path[0] == "models" and key in _SELECTED_MODEL_KEYS) \
                    or (not path and key in {"model", "default_model", "selected_model"}):
                _fail("Fonte Grok tenta selecionar um modelo fora do perfil pedido.")
            walk(child, child_path)

    walk(dict(config), ())


def _read_config(path: Path) -> Tuple[str, Mapping[str, object]]:
    """Read one inspected config without following links or exposing its values."""
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(str(path), flags)
    except OSError as error:
        raise GrokIsolationError("Fonte de configuracao Grok nao pode ser aberta com seguranca.") from error
    try:
        info = os.fstat(fd)
        mode = stat.S_IMODE(info.st_mode)
        if not stat.S_ISREG(info.st_mode) or info.st_uid not in {0, os.getuid()} \
                or mode & 0o022 or info.st_size > MAX_CONFIG_BYTES:
            _fail("Fonte de configuracao Grok tem propriedade, modo ou tamanho inseguro.")
        raw = bytearray()
        while len(raw) <= MAX_CONFIG_BYTES:
            chunk = os.read(fd, min(65536, MAX_CONFIG_BYTES + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        if len(raw) > MAX_CONFIG_BYTES:
            _fail("Fonte de configuracao Grok excede o limite seguro.")
    finally:
        os.close(fd)
    try:
        text = bytes(raw).decode("utf-8")
        parsed = _toml.loads(text)
    except (UnicodeDecodeError, ValueError) as error:
        raise GrokIsolationError("Fonte de configuracao Grok nao e TOML valido.") from error
    if not isinstance(parsed, dict):
        _fail("Fonte de configuracao Grok tem estrutura invalida.")
    _validate_config_values(parsed)
    return hashlib.sha256(raw).hexdigest(), parsed


def _layer_snapshot(layer: Mapping[str, object], grok_home: Path,
                    project_config: Optional[Path] = None) -> Optional[Tuple[str, str, str]]:
    role, raw_path, note = layer.get("role"), layer.get("path"), layer.get("note")
    if not isinstance(role, str) or not isinstance(raw_path, str) or not raw_path:
        _fail("Inspect informou fonte de configuracao incompleta.")
    if note is not None and not isinstance(note, str):
        _fail("Inspect informou nota de configuracao invalida.")
    path = Path(raw_path)
    if not path.is_absolute():
        _fail("Inspect informou caminho de configuracao relativo.")
    exists = path.exists()
    if not exists:
        if isinstance(note, str) and _ABSENT_NOTE.search(note) and not _BAD_NOTE.search(note):
            return None
        _fail("Inspect informou fonte de configuracao ausente sem prova de ausencia.")
    if isinstance(note, str) and note != "empty":
        _fail("Fonte Grok existente possui diagnostico nao qualificado.")
    if role == "project":
        if project_config is None or path.resolve() != project_config.resolve():
            _fail("Configuracao de projeto Grok apareceu fora do workspace privado.")
    elif role == "user":
        if path.resolve() != (grok_home / "config.toml").resolve():
            _fail("Fonte de usuario Grok apareceu fora de GROK_HOME.")
    elif role not in _CONFIG_ROLES:
        _fail("Inspect informou uma fonte Grok existente de papel desconhecido.")
    digest, parsed = _read_config(path)
    if note == "empty" and parsed:
        _fail("Inspect classificou como vazia uma fonte Grok com conteudo efetivo.")
    return role, str(path.resolve()), digest


def _ambient_layers(report: Mapping[str, object], grok_home: Path,
                    project_config: Optional[Path] = None) -> Tuple[Tuple[str, str, str], ...]:
    snapshots = []
    for layer in _layers(report):
        if layer.get("role") == "project":
            snapshot = _layer_snapshot(layer, grok_home, project_config)
            if snapshot is not None and project_config is None:
                _fail("Workspace Grok ja tinha configuracao de projeto efetiva.")
            continue
        snapshot = _layer_snapshot(layer, grok_home)
        if snapshot is not None:
            snapshots.append(snapshot)
    return tuple(sorted(snapshots))


def _plugin_identities(report: Mapping[str, object]) -> Tuple[Tuple[object, ...], ...]:
    rows = report.get("plugins")
    if not isinstance(rows, list):
        _fail("Inspect nao informou plugins.")
    identities = []
    for row in rows:
        if not isinstance(row, dict):
            _fail("Entrada de plugin invalida.")
        name, scope, path = row.get("name"), row.get("scope"), row.get("path")
        if not isinstance(name, str) or not name or len(name) > 149 \
                or any(ord(char) < 32 for char in name):
            _fail("Plugin sem nome seguro para desativacao.")
        if not isinstance(scope, str) or not isinstance(path, str) or not path:
            _fail("Identidade de plugin incompleta.")
        provides = row.get("provides")
        encoded = json.dumps(provides, sort_keys=True, separators=(",", ":"))
        identities.append((name, scope, path, encoded))
    return tuple(sorted(identities))


def _plugin_source(item: object, disabled: Iterable[str]) -> bool:
    if not isinstance(item, dict):
        return False
    source = item.get("source")
    return (isinstance(source, dict) and source.get("type") == "plugin"
            and source.get("plugin_name") in disabled)


def _reject_executables(report: Mapping[str, object], disabled: Iterable[str]) -> None:
    disabled = set(disabled)
    for key in ("hooks", "mcpServers", "lspServers"):
        rows = report.get(key)
        if not isinstance(rows, list):
            _fail("Inspect omitiu superficies executaveis.")
        if any(not _plugin_source(row, disabled) for row in rows):
            _fail("Grok descobriu hook, MCP ou LSP fora dos plugins desativados.")


def _verify_oidc(grok_home: Path) -> None:
    auth_path = grok_home / "auth.json"
    if auth_path.is_symlink() or not auth_path.is_file():
        _fail("Metadados locais de autenticacao Grok indisponiveis.")
    try:
        data = json.loads(auth_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise GrokIsolationError("Metadados de autenticacao Grok invalidos.") from error
    if not isinstance(data, dict):
        _fail("Metadados de autenticacao Grok invalidos.")
    oidc = []
    for scope, entry in data.items():
        if not isinstance(scope, str) or not isinstance(entry, dict):
            _fail("Entrada de autenticacao Grok invalida.")
        if entry.get("auth_mode") == "api_key" or scope == "xai::api_key":
            _fail("Autenticacao API key persistida nao e aceita nesta rota.")
        if entry.get("auth_mode") == "oidc" and entry.get("oidc_issuer") == "https://auth.x.ai":
            valid_scope = scope.startswith("https://auth.x.ai::")
            has_token = isinstance(entry.get("key"), str) and bool(entry.get("key"))
            has_refresh = isinstance(entry.get("refresh_token"), str) and bool(entry.get("refresh_token"))
            if valid_scope and has_token and has_refresh:
                oidc.append(scope)
    if len(oidc) != 1:
        _fail("Assinatura OIDC xAI unica e valida nao foi confirmada por metadados.")


def _write_config(workspace: Path, names: Iterable[str]) -> Path:
    directory = workspace / ".grok"
    os.mkdir(str(directory), 0o700)
    path = directory / "config.toml"
    encoded = ", ".join(json.dumps(name, ensure_ascii=True) for name in sorted(names))
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, ("[plugins]\ndisabled = [" + encoded + "]\n").encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    return path


def prepare(profile: Mapping[str, object], workspace: Path,
            env: Mapping[str, str]) -> Dict[str, object]:
    """Prepare one fresh job workspace and return non-secret assertions.

    ``inspect`` 1.0.13 omits effective endpoint/model provenance, so every
    existing ambient TOML layer is parsed and screened before and after the
    private project plugin policy is written.
    """
    if profile.get("provider") != "grok" or profile.get("auth") != "subscription":
        _fail("Isolamento Grok aceita apenas o perfil de assinatura Grok.")
    workspace = _private_workspace(Path(workspace))
    grok_home = _preserved_homes(env)
    binary = _binary(profile)
    binary_info = os.stat(binary)
    binary_identity = (binary_info.st_dev, binary_info.st_ino, binary_info.st_size,
                       binary_info.st_mtime_ns)
    fingerprint = _run([binary, "--version"], workspace, env).strip()
    if fingerprint != PINNED_FINGERPRINT:
        _fail("Build Grok nao corresponde ao fingerprint qualificado.")
    _verify_oidc(grok_home)

    first = _json_report(binary, workspace, env)
    if first.get("projectRoot") is not None:
        _fail("Workspace Grok deve permanecer fora de repositorios.")
    ambient = _ambient_layers(first, grok_home)

    identities = _plugin_identities(first)
    names = sorted({str(identity[0]) for identity in identities})
    _reject_executables(first, names)
    config_path = _write_config(workspace, names)

    second = _json_report(binary, workspace, env)
    if second.get("projectRoot") is not None:
        _fail("Workspace Grok mudou de raiz durante o preflight.")
    if _plugin_identities(second) != identities:
        _fail("Plugins Grok mudaram durante o preflight.")
    _reject_executables(second, names)
    project = [row for row in _layers(second)
               if row.get("role") == "project" and Path(str(row.get("path"))).exists()]
    if len(project) != 1:
        _fail("Inspect nao confirmou a configuracao privada de plugins.")
    if _ambient_layers(second, grok_home, config_path) != ambient:
        _fail("Fontes globais Grok mudaram durante o preflight.")
    if config_path.is_symlink() or stat.S_IMODE(config_path.stat().st_mode) != 0o600:
        _fail("Configuracao privada Grok perdeu suas garantias de arquivo.")
    current = os.stat(binary)
    if (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns) != binary_identity \
            or _run([binary, "--version"], workspace, env).strip() != fingerprint:
        _fail("Executavel Grok mudou durante o preflight.")

    return {
        "schema": 1,
        "version": PINNED_VERSION,
        "fingerprint": fingerprint,
        "disabled_plugins": sorted(names),
        "auth": "oidc_subscription_metadata_verified",
        "assertions": [
            "home_preserved", "api_key_auth_disabled", "oidc_metadata_verified",
            "ambient_config_parsed_and_stable", "project_config_loaded",
            "plugin_identity_stable", "binary_identity_stable",
            "standalone_executables_absent",
        ],
        "warnings": [
            "Grok 1.0.13 inspect reports discovered plugin rows, not the active registry; "
            "project disablement is qualified from pinned official source behavior."
        ],
        "qualification": "pinned_1.0.13_source_asserted_project_plugin_disable",
        "qualification_source": QUALIFICATION_SOURCE,
    }
