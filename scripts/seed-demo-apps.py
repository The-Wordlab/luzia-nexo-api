#!/usr/bin/env python3
"""
Seed demo apps in Nexo via the public HTTP API.

This script is the single source of truth for demo app definitions.
It reads demo-apps.json and creates/updates apps via Nexo's REST API.

Usage:
    # Local Docker (default)
    python scripts/seed-demo-apps.py

    # Production
    python scripts/seed-demo-apps.py --env production

    # Custom
    NEXO_API_URL=https://staging.nexo.example.com \
    NEXO_ADMIN_EMAIL=admin@example.com \
    NEXO_ADMIN_PASSWORD=secret \
    python scripts/seed-demo-apps.py

    # Dry run (print what would happen)
    python scripts/seed-demo-apps.py --dry-run

    # Skip webhook apps (CI-safe)
    python scripts/seed-demo-apps.py --ci-safe
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

try:
    import httpx
except ImportError:
    print("httpx is required: pip install httpx", file=sys.stderr)
    sys.exit(1)

SCRIPT_DIR = Path(__file__).parent
DEMO_APPS_FILE = SCRIPT_DIR / "demo-apps.json"
CONFIG_FILE = SCRIPT_DIR / "seed-config.json"
DEFAULT_DEMO_WEBHOOK_SECRET = "nexo-example-secret"
DEFAULT_OPENCLAW_WEBHOOK_SECRET = "nexo-openclaw-secret"

# ANSI colors
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
BLUE = "\033[0;34m"
NC = "\033[0m"


def log(msg: str) -> None:
    print(f"{BLUE}[seed]{NC} {msg}")


def ok(msg: str) -> None:
    print(f"{GREEN}[seed]{NC} {msg}")


def warn(msg: str) -> None:
    print(f"{YELLOW}[seed]{NC} {msg}")


def err(msg: str) -> None:
    print(f"{RED}[seed]{NC} {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------


def _expand_env_vars(value: str) -> str:
    """Expand ${VAR} references in a string using environment variables."""
    def replacer(match: re.Match) -> str:
        var_name = match.group(1)
        return os.environ.get(var_name, match.group(0))
    return re.sub(r"\$\{(\w+)\}", replacer, value)


def load_config(env_name: str) -> dict:
    """Load config for the given environment, with env var overrides."""
    config = {}
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            all_configs = json.load(f)
        config = all_configs.get(env_name, {})
        # Expand env var references in config values
        config = {k: _expand_env_vars(v) if isinstance(v, str) else v for k, v in config.items()}

    # Env vars always override config file
    config["api_url"] = os.environ.get("NEXO_API_URL", config.get("api_url", "http://localhost:8000"))
    config["admin_email"] = os.environ.get("NEXO_ADMIN_EMAIL", config.get("admin_email", "admin@test.com"))
    config["admin_password"] = os.environ.get("NEXO_ADMIN_PASSWORD", config.get("admin_password", "password"))
    return config


def load_demo_apps() -> dict:
    """Load demo app definitions from demo-apps.json."""
    with open(DEMO_APPS_FILE) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Webhook URL resolution
# ---------------------------------------------------------------------------


def resolve_webhook_url(app_def: dict) -> str | None:
    """Resolve the webhook URL for a demo app definition."""
    # Explicit null means no webhook
    if app_def.get("webhook_url") is None and "webhook_url_env" not in app_def and "webhook_url_template" not in app_def:
        return None

    # Environment variable override (for standalone RAG servers)
    env_var = app_def.get("webhook_url_env")
    if env_var:
        return os.environ.get(env_var, app_def.get("webhook_url_default"))

    # Template with env var expansion (for shared demo receiver)
    template = app_def.get("webhook_url_template")
    if template:
        expanded = _expand_env_vars(template)
        # If expansion didn't resolve (still has ${...}), fall back to default
        if "${" in expanded:
            return app_def.get("webhook_url_default")
        return expanded

    return app_def.get("webhook_url")


def resolve_webhook_secret(app_def: dict) -> str | None:
    """Resolve webhook signing secret for webhook-mode demo apps."""
    integration_mode = app_def.get("config_json", {}).get("integration_mode", "simulator")
    if integration_mode != "webhook":
        return None
    return os.environ.get("DEMO_EXAMPLES_WEBHOOK_SECRET", DEFAULT_DEMO_WEBHOOK_SECRET)


# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------


class NexoApiClient:
    """Sync HTTP client for Nexo API operations."""

    def __init__(self, base_url: str, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(base_url=self.base_url, timeout=timeout)
        self.token: str | None = None

    def close(self) -> None:
        self.client.close()

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def login(self, email: str, password: str) -> bool:
        """Authenticate and store JWT token."""
        resp = self.client.post(
            "/api/auth/jwt/login",
            data={"username": email, "password": password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if resp.status_code == 200:
            data = resp.json()
            self.token = data.get("access_token")
            return True
        elif resp.status_code == 204:
            # Some auth flows return 204 with cookie-based auth
            return True
        err(f"Login failed: {resp.status_code} {resp.text}")
        return False

    def get_organizations(self) -> list[dict]:
        """List all organizations visible to the current user."""
        resp = self.client.get("/api/organizations", headers=self._headers())
        resp.raise_for_status()
        data = resp.json()
        # Handle both list and paginated response
        if isinstance(data, list):
            return data
        return data.get("items", data.get("results", []))

    def create_organization(self, slug: str, name: str, description: str = "") -> dict:
        """Create an organization."""
        resp = self.client.post(
            "/api/organizations",
            json={"slug": slug, "name": name, "description": description},
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    def get_apps(self, page: int = 1, size: int = 100) -> list[dict]:
        """List apps with pagination."""
        resp = self.client.get(
            "/api/apps",
            params={"page": page, "size": size},
            headers=self._headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        return data.get("items", data.get("results", []))

    def create_app(
        self,
        org_id: str,
        name: str,
        description: str,
        config_json: dict,
        webhook_url: str | None = None,
        webhook_secret: str | None = None,
    ) -> dict:
        """Create a new app."""
        payload: dict = {
            "org_id": org_id,
            "name": name,
            "description": description,
            "config_json": config_json,
        }
        if webhook_url:
            payload["webhook_url"] = webhook_url
        if webhook_secret:
            payload["webhook_secret"] = webhook_secret
        resp = self.client.post("/api/apps", json=payload, headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    def update_app(self, app_id: str, **fields) -> dict:
        """Update an existing app (PATCH)."""
        resp = self.client.patch(f"/api/apps/{app_id}", json=fields, headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    def create_trigger_rule(self, app_id: str, trigger_type: str, keywords: list[str], priority: int, cooldown_seconds: int) -> dict:
        """Create a card trigger rule for an app."""
        resp = self.client.post(
            f"/api/apps/{app_id}/trigger-rules",
            json={
                "trigger_type": trigger_type,
                "keywords": keywords,
                "priority": priority,
                "cooldown_seconds": cooldown_seconds,
            },
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    def get_trigger_rules(self, app_id: str) -> list[dict]:
        """Get existing trigger rules for an app."""
        resp = self.client.get(f"/api/apps/{app_id}/trigger-rules", headers=self._headers())
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        return data.get("items", data.get("results", []))


# ---------------------------------------------------------------------------
# Seed logic
# ---------------------------------------------------------------------------


def find_org(client: NexoApiClient, slug: str) -> dict | None:
    """Find organization by slug."""
    orgs = client.get_organizations()
    for org in orgs:
        if org.get("slug") == slug:
            return org
    return None


def find_app_by_name(apps: list[dict], name: str) -> dict | None:
    """Find an app by name in a list of apps."""
    for app in apps:
        if app.get("name") == name:
            return app
    return None


def seed_demo_apps(
    config: dict,
    demo_data: dict,
    dry_run: bool = False,
    ci_safe: bool = False,
) -> bool:
    """Seed all demo apps via HTTP API. Returns True on success."""
    client = NexoApiClient(config["api_url"])

    try:
        # 1. Authenticate
        log(f"Connecting to {config['api_url']}...")
        if dry_run:
            log(f"[DRY RUN] Would login as {config['admin_email']}")
        else:
            if not client.login(config["admin_email"], config["admin_password"]):
                return False
            ok("Authenticated")

        # 2. Ensure demo org exists
        org_def = demo_data["organization"]
        if dry_run:
            log(f"[DRY RUN] Would ensure org '{org_def['slug']}' exists")
            org_id = "dry-run-org-id"
        else:
            org = find_org(client, org_def["slug"])
            if org is None:
                log(f"Creating organization '{org_def['name']}'...")
                org = client.create_organization(
                    slug=org_def["slug"],
                    name=org_def["name"],
                    description=org_def.get("description", ""),
                )
                ok(f"Created org: {org_def['name']}")
            else:
                ok(f"Org exists: {org_def['name']}")
            org_id = org["id"]

        # 3. Load existing apps for idempotent upsert
        existing_apps = [] if dry_run else client.get_apps(size=200)

        # 4. Seed each demo app
        seeded = []
        skipped = []
        for app_def in demo_data["apps"]:
            app_name = app_def["name"]
            integration_mode = app_def.get("config_json", {}).get("integration_mode", "simulator")

            if ci_safe and integration_mode == "webhook":
                skipped.append(app_name)
                log(f"  Skipping webhook app '{app_name}' (--ci-safe)")
                continue

            webhook_url = resolve_webhook_url(app_def)
            webhook_secret = resolve_webhook_secret(app_def)

            if dry_run:
                action = "create" if find_app_by_name(existing_apps, app_name) is None else "update"
                log(f"  [DRY RUN] Would {action} app '{app_name}' (mode={integration_mode})")
                if webhook_url:
                    log(f"    webhook_url: {webhook_url}")
                if webhook_secret:
                    log("    webhook_secret: [set]")
                rules = app_def.get("card_trigger_rules", [])
                if rules:
                    log(f"    card_trigger_rules: {len(rules)}")
                seeded.append(app_name)
                continue

            existing = find_app_by_name(existing_apps, app_name)
            if existing is None:
                # Create
                app = client.create_app(
                    org_id=org_id,
                    name=app_name,
                    description=app_def.get("description", ""),
                    config_json=app_def.get("config_json", {}),
                    webhook_url=webhook_url,
                    webhook_secret=webhook_secret,
                )
                ok(f"  Created: {app_name}")
            else:
                # Update
                update_fields: dict = {
                    "description": app_def.get("description", ""),
                    "config_json": app_def.get("config_json", {}),
                }
                if webhook_url is not None:
                    update_fields["webhook_url"] = webhook_url
                if webhook_secret:
                    update_fields["webhook_secret"] = webhook_secret
                app = client.update_app(existing["id"], **update_fields)
                ok(f"  Updated: {app_name}")

            app_id = app["id"]

            # Seed card trigger rules (idempotent: skip if rules already exist)
            rules = app_def.get("card_trigger_rules", [])
            if rules:
                existing_rules = client.get_trigger_rules(app_id)
                existing_types = {r.get("trigger_type") for r in existing_rules}
                for rule in rules:
                    if rule["trigger_type"] not in existing_types:
                        client.create_trigger_rule(
                            app_id=app_id,
                            trigger_type=rule["trigger_type"],
                            keywords=rule["keywords"],
                            priority=rule["priority"],
                            cooldown_seconds=rule["cooldown_seconds"],
                        )
                        log(f"    Added trigger rule: {rule['trigger_type']}")
                    else:
                        log(f"    Trigger rule exists: {rule['trigger_type']}")

            seeded.append(app_name)

        # 5. Optional Open CLAW app
        open_claw = demo_data.get("open_claw")
        if open_claw and os.environ.get("DEMO_OPENCLAW_ENABLED", "").lower() in ("true", "1", "yes"):
            oc_name = os.environ.get(open_claw["name_env"], open_claw["name_default"])
            oc_webhook_url = os.environ.get(open_claw["webhook_url_env"], open_claw["webhook_url_default"])
            oc_webhook_secret = os.environ.get(
                open_claw.get("webhook_secret_env", "DEMO_OPENCLAW_WEBHOOK_SECRET"),
                DEFAULT_OPENCLAW_WEBHOOK_SECRET,
            )

            if dry_run:
                log(f"  [DRY RUN] Would seed Open CLAW app '{oc_name}'")
            else:
                existing = find_app_by_name(existing_apps, oc_name)
                if existing is None:
                    client.create_app(
                        org_id=org_id,
                        name=oc_name,
                        description=open_claw.get("description", ""),
                        config_json=open_claw.get("config_json", {}),
                        webhook_url=oc_webhook_url,
                        webhook_secret=oc_webhook_secret,
                    )
                    ok(f"  Created: {oc_name}")
                else:
                    client.update_app(
                        existing["id"],
                        description=open_claw.get("description", ""),
                        config_json=open_claw.get("config_json", {}),
                        webhook_url=oc_webhook_url,
                        webhook_secret=oc_webhook_secret,
                    )
                    ok(f"  Updated: {oc_name}")
                seeded.append(oc_name)

        # Summary
        ok(f"Demo apps seeded: {len(seeded)} ({', '.join(seeded)})")
        if skipped:
            warn(f"Skipped (ci-safe): {', '.join(skipped)}")
        return True

    except httpx.HTTPStatusError as exc:
        err(f"HTTP error: {exc.response.status_code} {exc.response.text}")
        return False
    except httpx.ConnectError:
        err(f"Cannot connect to {config['api_url']} - is Nexo running?")
        return False
    except Exception as exc:
        err(f"Unexpected error: {exc}")
        return False
    finally:
        client.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed demo apps in Nexo via HTTP API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--env",
        default="local",
        help="Environment profile from seed-config.json (default: local)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would happen without making changes.",
    )
    parser.add_argument(
        "--ci-safe",
        action="store_true",
        dest="ci_safe",
        help="Skip webhook-mode apps that require external services.",
    )
    args = parser.parse_args()

    config = load_config(args.env)
    demo_data = load_demo_apps()

    log(f"Environment: {args.env}")
    log(f"API URL: {config['api_url']}")
    if args.dry_run:
        log("Mode: DRY RUN")
    if args.ci_safe:
        log("Mode: CI-SAFE (skipping webhook apps)")

    success = seed_demo_apps(
        config=config,
        demo_data=demo_data,
        dry_run=args.dry_run,
        ci_safe=args.ci_safe,
    )

    if success:
        ok("Done. Demo apps are ready.")
    else:
        err("Seed failed. Check errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
