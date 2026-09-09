"""Small, explainable routing gate; availability is not an obligation to spawn."""
from __future__ import annotations

import time

from . import adapters


def principal(provider, model, effort):
    values = (provider, model, effort)
    if not any(values):
        return None
    if not all(values):
        raise adapters.AdapterError("Informe provider, model e effort do principal juntos.")
    profile = adapters.resolve_profile(explicit=model, provider=provider, effort=effort)
    return {key: profile[key] for key in ("provider", "model", "effort")} | {
        "identity_evidence": "declared_not_verified"}


def decide(profile, task, *, host=None, benefit="", independent=False,
           critical=False, quota=None, now=None):
    """No scores or inferred balances; all judgments stay visible to the principal."""
    now = time.time() if now is None else now
    benefit = (benefit or "").strip()
    result = {"action": "local", "principal": host,
              "principal_identity": "declared_not_verified" if host else "unknown",
              "benefit": benefit[:1000], "independent": bool(independent),
              "critical_review": bool(critical), "quota": "unknown",
              "same_model": bool(host and host.get("provider") == profile["provider"]
                                 and host.get("model") == profile["model"])}
    if quota and quota.get("expires_at", 0) > now:
        result["quota"] = quota["availability"]
        result["quota_evidence"] = "manual_account_snapshot_not_attributed"
    if result["quota"] == "blocked":
        result.update(action="blocked", reason="provider_quota_blocked")
    elif not benefit:
        result["reason"] = "no_marginal_benefit_declared"
    elif not (independent or critical):
        result["reason"] = "no_independent_work_or_critical_review"
    elif result["quota"] == "constrained" and not critical:
        result["reason"] = "preserve_constrained_provider_quota"
    else:
        result.update(action="delegate", reason="bounded_critical_review" if critical
                      else "independent_contribution")
    result["note"] = ("Mesmo modelo só se justifica por trabalho independente ou revisão crítica; "
                      "diversidade não é corroboracão. Git pode executar sem chamada de modelo. "
                      "Quota desconhecida não significa quota disponível.")
    return result
