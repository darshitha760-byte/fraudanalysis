from app.core.permissions import UserRole
from app.core.security import verify_password
from app.models import User


def test_registration_creates_viewer_with_hashed_password(test_client, test_session):
    response = test_client.post(
        "/api/auth/register",
        json={
            "email": "new.viewer@example.com",
            "full_name": "New Viewer",
            "password": "SecurePass123",
        },
    )

    assert response.status_code == 201
    assert response.json()["email"] == "new.viewer@example.com"
    assert response.json()["role"] == UserRole.VIEWER.value

    user = User.model_validate(test_session["users"].find_one({"email": "new.viewer@example.com"}))
    assert user.role == UserRole.VIEWER
    assert user.is_active is True
    assert user.password_hash != "SecurePass123"
    assert verify_password("SecurePass123", user.password_hash)

    login_response = test_client.post(
        "/api/auth/login",
        json={"email": "NEW.VIEWER@example.com", "password": "SecurePass123"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    profile_response = test_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert profile_response.status_code == 200
    assert profile_response.json()["role"] == UserRole.VIEWER.value


def test_registration_rejects_duplicate_email(test_client):
    payload = {
        "email": "duplicate@example.com",
        "full_name": "First User",
        "password": "SecurePass123",
    }
    assert test_client.post("/api/auth/register", json=payload).status_code == 201

    response = test_client.post(
        "/api/auth/register",
        json={**payload, "full_name": "Second User"},
    )

    assert response.status_code == 409


def test_registration_does_not_allow_role_assignment(test_client):
    response = test_client.post(
        "/api/auth/register",
        json={
            "email": "role.attempt@example.com",
            "full_name": "Role Attempt",
            "password": "SecurePass123",
            "role": "admin",
        },
    )

    assert response.status_code == 422


def test_legacy_auth_route_remains_available(test_client):
    response = test_client.post(
        "/auth/register",
        json={
            "email": "legacy.route@example.com",
            "full_name": "Legacy Route",
            "password": "SecurePass123",
        },
    )

    assert response.status_code == 201


def test_registration_rejects_short_password_and_blank_name(test_client):
    short_password = test_client.post(
        "/api/auth/register",
        json={
            "email": "short.password@example.com",
            "full_name": "Short Password",
            "password": "short",
        },
    )
    blank_name = test_client.post(
        "/api/auth/register",
        json={
            "email": "blank.name@example.com",
            "full_name": "  ",
            "password": "SecurePass123",
        },
    )

    assert short_password.status_code == 422
    assert blank_name.status_code == 422
