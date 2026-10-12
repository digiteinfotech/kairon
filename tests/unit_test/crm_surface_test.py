import os

os.environ["system_file"] = "./tests/testing_data/system.yaml"

from kairon.shared.utils import Utility
Utility.load_system_metadata()

from kairon.crm.processor import CRMProcessor
from kairon.crm.routes import router
from kairon.crm.services.bench_executor import BenchExecutor


class TestRawTenantTablesAreNotExposed:
    """The raw tenant database browser (`/crm/tables`, `/crm/tables/{table_name}`) let any bot admin read internal
    Frappe tables of the tenant database (for example `__Auth`, which holds password hashes and API secrets).
    It had no Admin UI consumer, so it was removed rather than filtered."""

    def test_no_route_exposes_tables(self):
        paths = [route.path for route in router.routes]
        assert not [p for p in paths if "tables" in p], paths

    def test_no_processor_or_executor_entry_point(self):
        for name in ("get_db_tables", "get_table_content"):
            assert not hasattr(CRMProcessor, name)
            assert not hasattr(BenchExecutor, name)

    def test_expected_routes_remain(self):
        paths = {route.path for route in router.routes}
        for expected in ("/onboard", "/validate", "/status", "/details", "/login-link", "/project", "/users"):
            assert expected in paths, expected


class TestMatrixLoadedFromSharedMetadata:

    def test_matrix_comes_from_system_metadata(self):
        from kairon.crm.services.feature_resolver import FeatureAppResolver
        FeatureAppResolver._matrix_cache = None
        matrix = FeatureAppResolver.load_matrix()
        assert matrix is Utility.system_metadata["provisioning_matrix"]
        assert matrix["crm"]["required_apps"] == ["crm"]
        assert os.path.exists("metadata/provisioning_matrix.yml")
