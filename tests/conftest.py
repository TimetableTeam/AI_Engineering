import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import engine


@pytest.fixture()
def tables():
    return {name: frame.copy(deep=True) for name, frame in engine.tables.items()}


@pytest.fixture()
def readiness_tables(tables):
    return tables
