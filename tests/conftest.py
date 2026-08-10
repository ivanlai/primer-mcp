from pathlib import Path

import pytest

from primer_mcp.project import init_project


@pytest.fixture
def project(tmp_path: Path) -> Path:
    init_project(tmp_path, "demo")
    return tmp_path
