import requests
import urllib3

from kairon.shared.utils import Utility


def build_bench_session(host_header: str) -> requests.Session:
    """
    HTTP session for a tenant site on the Bench: routes by Host header and asks for JSON.

    Defaults to verifying certs; only disabled when the operator explicitly opts out via
    crm.bench.ssl_verify (e.g. a self-signed local bench). A hardcoded `verify = False` would
    silently accept any certificate on a remote HTTPS deployment, exposing credentials to an
    active attacker.
    """
    session = requests.Session()
    ssl_verify = Utility.environment.get("crm", {}).get("bench", {}).get("ssl_verify", True)
    session.verify = ssl_verify
    if not ssl_verify:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    session.headers.update({"Host": host_header, "Accept": "application/json"})
    return session
