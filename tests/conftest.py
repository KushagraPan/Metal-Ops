import pytest
from app.main import app
from app.models.user import User
from app.routers.auth import require_session


@pytest.fixture(autouse=True)
def bypass_auth_for_unit_tests(request: pytest.FixtureRequest):
    # Do not bypass authentication when testing auth itself or running integration tests
    if (
        "test_auth" in request.module.__name__
        or "integration" in request.module.__name__
        or request.node.get_closest_marker("integration") is not None
    ):
        yield
        return

    dummy_user = User(id=1, email="unit-test@workshop.local", password_hash="dummy_hash")
    app.dependency_overrides[require_session] = lambda: dummy_user
    try:
        yield
    finally:
        app.dependency_overrides.pop(require_session, None)
