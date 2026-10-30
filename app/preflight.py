"""Preflight checks and actionable error hints for Google Cloud newcomers.

Used by `make eval`, `make deploy`, `make test-remote`, `make delete` and the
Seed Pack `load.py` scripts so that the most common setup mistakes (no ADC,
missing quota project, API not enabled, missing bucket/dataset, wrong Gemini
location) fail with one clear "do this next" message instead of a traceback.
"""

from __future__ import annotations

import re
from typing import Any

from app.loader import is_placeholder, resolve_env_config

REQUIRED_APIS = (
    "aiplatform.googleapis.com",
    "bigquery.googleapis.com",
    "storage.googleapis.com",
    "cloudresourcemanager.googleapis.com",
)

_RESOURCE_RE = re.compile(
    r"^projects/(?P<project>[^/]+)/locations/(?P<location>[^/]+)/reasoningEngines/(?P<id>[^/]+)$"
)


class GcpPreflightValidator:
    """Object-Oriented preflight validator for Google Cloud credentials and Agent Runtime setup."""

    def __init__(self, required_apis: tuple[str, ...] = REQUIRED_APIS) -> None:
        self.required_apis = required_apis

    def require_project(self, context: str | None = None) -> str:
        """Return GOOGLE_CLOUD_PROJECT or raise a RuntimeError explaining how to set it."""
        project = resolve_env_config("GOOGLE_CLOUD_PROJECT")
        if not project:
            ctx_msg = f" ({context})" if context else ""
            raise RuntimeError(
                f"GOOGLE_CLOUD_PROJECT is not set{ctx_msg}. Run `cp .env.example .env` and set "
                "GOOGLE_CLOUD_PROJECT=<your project id> in .env."
            )
        return project

    def check_adc(self, project: str | None = None, context: str | None = None) -> None:
        """Raise a RuntimeError with the fix if Application Default Credentials are missing."""
        proj = project or resolve_env_config("GOOGLE_CLOUD_PROJECT") or "<your-project-id>"
        try:
            import google.auth
            from google.auth.exceptions import DefaultCredentialsError
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("google-auth is not installed. Run `make setup`.") from exc
        try:
            google.auth.default()
        except DefaultCredentialsError as exc:
            ctx_msg = f" during {context}" if context else ""
            raise RuntimeError(
                f"No Application Default Credentials found{ctx_msg}. Run:\n"
                "  gcloud auth application-default login\n"
                f"  gcloud auth application-default set-quota-project {proj}"
            ) from exc

    def parse_reasoning_engine_name(self, resource_name: str) -> dict[str, str]:
        """Split `projects/P/locations/L/reasoningEngines/ID` into its parts (or raise ValueError)."""
        match = _RESOURCE_RE.match((resource_name or "").strip())
        if not match:
            raise ValueError(
                f"'{resource_name}' is not a full Agent Runtime resource name. Expected "
                "projects/<project>/locations/<region>/reasoningEngines/<id>."
            )
        return match.groupdict()

    def explain_gcp_error(
        self,
        exc: BaseException,
        project: str | None = None,
        context: str | None = None,
    ) -> str:
        """Return a one-paragraph actionable hint for common Google Cloud errors ('' if unknown)."""
        text = f"{type(exc).__name__}: {exc}"
        lowered = text.lower()
        proj = project or resolve_env_config("GOOGLE_CLOUD_PROJECT") or "<your-project-id>"

        if "defaultcredentialserror" in lowered or "default credentials" in lowered:
            return (
                "No Application Default Credentials. Run `gcloud auth application-default login` "
                f"and `gcloud auth application-default set-quota-project {proj}`."
            )
        if "reauthentication" in lowered or "invalid_grant" in lowered:
            return "Your gcloud credentials expired. Run `gcloud auth application-default login` again."
        if "service_disabled" in lowered or "has not been used in project" in lowered or (
            "api" in lowered and "is disabled" in lowered
        ):
            return (
                "A required Google Cloud API is not enabled. Run:\n"
                f"  gcloud services enable {' '.join(self.required_apis)} --project={proj}\n"
                "then wait ~1 minute and retry."
            )
        if "quota project" in lowered or "user_project_denied" in lowered or "x-goog-user-project" in lowered:
            return f"ADC has no/incorrect quota project. Run `gcloud auth application-default set-quota-project {proj}`."
        if "not found: dataset" in lowered:
            return "The BigQuery dataset does not exist yet. Run `make seed PACK=<your pack>` first."
        if "bucket does not exist" in lowered or ("notfound: 404" in lowered and "/b/" in lowered):
            return (
                "The staging bucket does not exist. Create it once with:\n"
                f"  gcloud storage buckets create gs://{proj}-hackathon-staging --location=europe-west1 --project={proj}"
            )
        if ("publisher model" in lowered or "models/" in lowered) and ("404" in lowered or "not_found" in lowered or "not found" in lowered):
            return (
                "Gemini model not found at this location. Check GEMINI_MODEL in .env and keep "
                "GOOGLE_CLOUD_LOCATION=global (Gemini 3.8 Flash is served on the global endpoint)."
            )
        if "build failed" in lowered:
            return (
                "Agent Runtime could not build the container. Read the build log with:\n"
                "  gcloud logging read 'resource.type=\"aiplatform.googleapis.com/ReasoningEngine\"' "
                f"--project={proj} --freshness=30m --limit=50 --format='value(textPayload)'\n"
                "A timeout pulling the base image is transient: just re-run `make deploy`. A pip error "
                "means a package in PINNED_REQUIREMENTS (deploy/deploy.py) is wrong."
            )
        if "missing key inputs" in lowered or "api_key" in lowered:
            return (
                "The Gemini client is not in Vertex AI mode. Set GOOGLE_GENAI_USE_VERTEXAI=1 and "
                "GOOGLE_CLOUD_PROJECT in .env."
            )
        if "permission_denied" in lowered or "403" in lowered:
            return (
                f"Permission denied in project '{proj}'. Check you are using the right project "
                "(`gcloud config get-value project`), that your account has Vertex AI User, BigQuery "
                "User and Storage Admin roles, and that the quota project is set "
                f"(`gcloud auth application-default set-quota-project {proj}`)."
            )
        if "resource_exhausted" in lowered or "429" in lowered:
            return "Gemini quota exhausted (429). Wait 30-60 seconds and retry; avoid parallel eval runs."
        return ""

    def format_error(
        self,
        exc_or_title: BaseException | str,
        project_or_problem: str | None = None,
        fix_commands: list[str] | None = None,
        *,
        title: str | None = None,
        problem: str | None = None,
    ) -> str:
        """Return `ERROR: <exc>` plus a `HINT:` line when a known fix exists, or formatted message with fix commands."""
        if isinstance(exc_or_title, BaseException):
            hint = self.explain_gcp_error(exc_or_title, project_or_problem)
            message = f"ERROR: {type(exc_or_title).__name__}: {exc_or_title}"
            return f"{message}\nHINT: {hint}" if hint else message

        if fix_commands or title or problem:
            t = title or str(exc_or_title)
            p = problem or (project_or_problem or "")
            fixes = ("\n" + "\n".join(f"  {c}" for c in fix_commands)) if fix_commands else ""
            return f"ERROR [{t}]: {p}{fixes}".strip()

        hint = self.explain_gcp_error(RuntimeError(str(exc_or_title)), project_or_problem)
        message = f"ERROR: {exc_or_title}"
        return f"{message}\nHINT: {hint}" if hint else message


_default_validator = GcpPreflightValidator()


def require_project(context: str | None = None) -> str:
    """Return GOOGLE_CLOUD_PROJECT or raise a RuntimeError explaining how to set it."""
    return _default_validator.require_project(context=context)


def check_adc(project: str, context: str | None = None) -> None:
    """Raise a RuntimeError with the fix if Application Default Credentials are missing."""
    _default_validator.check_adc(project=project, context=context)


def parse_reasoning_engine_name(resource_name: str) -> dict[str, str]:
    """Split `projects/P/locations/L/reasoningEngines/ID` into its parts (or raise ValueError)."""
    return _default_validator.parse_reasoning_engine_name(resource_name)


def explain_gcp_error(
    exc: BaseException,
    project: str | None = None,
    context: str | None = None,
) -> str:
    """Return a one-paragraph actionable hint for common Google Cloud errors ('' if unknown)."""
    return _default_validator.explain_gcp_error(exc, project=project, context=context)


def format_error(
    exc: BaseException | str,
    project: str | None = None,
    fix_commands: list[str] | None = None,
    *,
    title: str | None = None,
    problem: str | None = None,
) -> str:
    """Return `ERROR: <exc>` plus a `HINT:` line when a known fix exists."""
    return _default_validator.format_error(
        exc,
        project_or_problem=project,
        fix_commands=fix_commands,
        title=title,
        problem=problem,
    )


__all__ = [
    "REQUIRED_APIS",
    "GcpPreflightValidator",
    "require_project",
    "check_adc",
    "parse_reasoning_engine_name",
    "explain_gcp_error",
    "format_error",
]
