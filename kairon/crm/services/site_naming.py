"""
Names of a tenant's Bench site and database.

The site name is the tenant's real hostname: it is the Frappe site directory, the `Host` header the bench routes on and
the host in every link users open. So it must be a valid DNS name (hyphens, never underscores, labels of at most 63
characters) under `crm.bench.tenant_domain` (env BENCH_TENANT_DOMAIN, default `localhost` for a local stack). The database
name is derived from the whole site name by hash, so two long company names that share a prefix can never share a
database (a truncated readable name could, and `bench new-site --force` would then reuse the other tenant's data).
"""
import hashlib
import re
from typing import Text, Tuple

from kairon.exceptions import AppException
from kairon.shared.utils import Utility

DEFAULT_TENANT_DOMAIN = "localhost"
MAX_SLUG_LENGTH = 55            # a DNS label is at most 63 characters
DOMAIN_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*$")


def tenant_domain() -> Text:
    bench = (Utility.environment.get("crm") or {}).get("bench") or {}
    domain = str(bench.get("tenant_domain") or DEFAULT_TENANT_DOMAIN).strip().strip(".").lower()
    if len(domain) > 120 or not DOMAIN_PATTERN.match(domain):
        raise AppException("crm.bench.tenant_domain must be a valid DNS domain name (BENCH_TENANT_DOMAIN).")
    return domain


def clean_site_name(company_name: Text) -> Tuple[Text, Text]:
    """Returns (slug, site name) for a company name, e.g. ("acme-jewellers", "acme-jewellers.crm.kairon.ai")."""
    slug = re.sub(r"[^a-z0-9]+", "-", (company_name or "").lower()).strip("-")
    if not slug:
        raise AppException("The company name must contain letters or numbers.")
    if len(slug) > MAX_SLUG_LENGTH:
        # Keep distinct long names distinct: a hash of the whole slug follows the readable prefix.
        digest = hashlib.sha1(slug.encode()).hexdigest()[:8]  # nosec B324 - identifier, not security use
        slug = f"{slug[:MAX_SLUG_LENGTH - 9].strip('-')}-{digest}"
    return slug, f"{slug}.{tenant_domain()}"


def database_name(prefix: Text, site_name: Text) -> Text:
    """`<prefix>_<16 hex of sha1(site)>`: deterministic per site, unique across sites, well under PostgreSQL's 63 bytes."""
    return f"{prefix}_{hashlib.sha1(site_name.encode()).hexdigest()[:16]}"  # nosec B324 - identifier, not security use
