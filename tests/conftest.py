import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from fastapi.testclient import TestClient
import pytest

# Shared fixture for server.app — reuse across specs per GAP_REPORT reuse R1
@pytest.fixture(scope="session")
def client():
    import server
    return TestClient(server.app)

@pytest.fixture
def html_content():
    return pathlib.Path("static/index.html").read_text(encoding="utf-8")
