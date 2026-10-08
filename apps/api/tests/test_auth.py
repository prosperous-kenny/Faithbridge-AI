"""Authentication flows: registration, login, token refresh, expiry (PRD §10)."""

from __future__ import annotations

import pytest

from app.core.security import (
    PasswordPolicyError,
    create_token,
    hash_password,
    verify_password,
)

API = "/api/v1/auth"


# --- password hashing ------------------------------------------------------


def test_password_hash_round_trip():
    encoded = hash_password("correct-horse-1")
    assert encoded != "correct-horse-1"
    assert encoded.startswith("pbkdf2_sha256$")
    assert verify_password("correct-horse-1", encoded) is True
    assert verify_password("correct-horse-2", encoded) is False


def test_password_hash_is_salted():
    # Two hashes of the same password must differ, or the stored value is a
    # rainbow-table target.
    assert hash_password("correct-horse-1") != hash_password("correct-horse-1")


def test_password_policy_rejects_short_and_oversized():
    with pytest.raises(PasswordPolicyError):
        hash_password("short7")
    with pytest.raises(PasswordPolicyError):
        hash_password("x" * 200)


def test_verify_password_rejects_malformed_and_missing_hashes():
    assert verify_password("whatever", None) is False
    assert verify_password("whatever", "not-a-hash") is False
    assert verify_password("whatever", "bcrypt$10$abc$def") is False


# --- registration ----------------------------------------------------------


def test_register_creates_account_without_leaking_password(client, clean_db):
    response = client.post(
        f"{API}/register",
        json={
            "email": "New.User@Example.org",
            "password": "correct-horse-1",
            "full_name": "New User",
            "role": "community_member",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == "new.user@example.org"  # normalized on the way in
    assert body["role"] == "community_member"
    assert "password" not in body and "password_hash" not in body


def test_register_rejects_unknown_role(client, clean_db):
    response = client.post(
        f"{API}/register",
        json={
            "email": "x@example.org",
            "password": "correct-horse-1",
            "full_name": "X",
            "role": "superuser",
        },
    )
    assert response.status_code == 422


def test_register_rejects_short_password(client, clean_db):
    response = client.post(
        f"{API}/register",
        json={
            "email": "x@example.org",
            "password": "short7",
            "full_name": "X",
            "role": "community_member",
        },
    )
    assert response.status_code == 422


def test_register_refuses_self_granted_admin(client, clean_db):
    """Privilege escalation: nobody may sign up as an administrator."""
    response = client.post(
        f"{API}/register",
        json={
            "email": "attacker@example.org",
            "password": "correct-horse-1",
            "full_name": "Not Admin",
            "role": "admin",
        },
    )
    assert response.status_code == 403
    assert "administrator" in response.json()["detail"].lower()


def test_register_refuses_self_granted_faith_leader(client, clean_db):
    response = client.post(
        f"{API}/register",
        json={
            "email": "leader@example.org",
            "password": "correct-horse-1",
            "full_name": "Would Be Leader",
            "role": "faith_leader",
        },
    )
    assert response.status_code == 403


async def test_admin_can_create_faith_leader(client, make_user, login):
    admin = await make_user("admin")
    response = client.post(
        f"{API}/register",
        json={
            "email": "leader@example.org",
            "password": "correct-horse-1",
            "full_name": "Parish Leader",
            "role": "faith_leader",
        },
        headers=login(admin),
    )
    assert response.status_code == 201, response.text
    assert response.json()["role"] == "faith_leader"


async def test_register_rejects_duplicate_email(client, clean_db):
    first = client.post(
        f"{API}/register",
        json={
            "email": "dup@example.org",
            "password": "correct-horse-1",
            "full_name": "First",
            "role": "community_member",
        },
    )
    assert first.status_code == 201

    # Email matching is case-insensitive, so this is the same address.
    second = client.post(
        f"{API}/register",
        json={
            "email": "DUP@example.org",
            "password": "correct-horse-1",
            "full_name": "Second",
            "role": "community_member",
        },
    )
    assert second.status_code == 409


# --- login -----------------------------------------------------------------


async def test_login_returns_token_pair(client, make_user):
    user = await make_user("donor")
    response = client.post(
        f"{API}/login", json={"email": user.email, "password": "correct-horse-1"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0
    assert body["access_token"] != body["refresh_token"]


async def test_me_returns_profile(client, make_user, login):
    user = await make_user("faith_leader")
    response = client.get(f"{API}/me", headers=login(user))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["email"] == user.email
    assert body["role"] == "faith_leader"
    assert body["is_active"] is True


async def test_login_wrong_password_and_unknown_email_are_indistinguishable(
    client, make_user
):
    user = await make_user("donor")

    wrong_password = client.post(
        f"{API}/login", json={"email": user.email, "password": "not-the-password"}
    )
    unknown_email = client.post(
        f"{API}/login", json={"email": "nobody@example.org", "password": "whatever-1"}
    )

    assert wrong_password.status_code == 401
    assert unknown_email.status_code == 401
    # Same message on both paths: no user-enumeration oracle.
    assert wrong_password.json()["detail"] == unknown_email.json()["detail"]


async def test_login_rejects_disabled_account(client, make_user):
    user = await make_user("donor", is_active=False)
    response = client.post(
        f"{API}/login", json={"email": user.email, "password": "correct-horse-1"}
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Account disabled"


# --- token verification ----------------------------------------------------


async def test_me_requires_a_bearer_token(client, make_user):
    await make_user("donor")
    response = client.get(f"{API}/me")
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"


async def test_me_rejects_malformed_token(client, make_user):
    await make_user("donor")
    response = client.get(f"{API}/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert response.status_code == 401


async def test_me_rejects_expired_token(client, make_user):
    user = await make_user("donor")
    expired = create_token(
        user_id=user.id, role=user.role, token_type="access", ttl_seconds=-5
    )
    response = client.get(f"{API}/me", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401


async def test_me_rejects_a_refresh_token_used_as_access(client, make_user):
    """A refresh token must not authenticate a request."""
    user = await make_user("donor")
    from app.core.security import create_refresh_token

    refresh = create_refresh_token(user.id, user.role)
    response = client.get(f"{API}/me", headers={"Authorization": f"Bearer {refresh}"})
    assert response.status_code == 401


async def test_me_rejects_token_for_deleted_user(client, make_user):
    user = await make_user("donor")
    from app.core.security import create_access_token

    orphan = create_access_token(user.id, user.role)
    # Remove the account the token points at; the token must stop working
    # immediately rather than at expiry.
    from app.db.session import SessionFactory

    async with SessionFactory() as session:
        from sqlalchemy import delete

        from app.db.models import User

        await session.execute(delete(User).where(User.id == user.id))
        await session.commit()

    response = client.get(f"{API}/me", headers={"Authorization": f"Bearer {orphan}"})
    assert response.status_code == 401


async def test_me_is_denied_once_the_account_is_disabled(client, make_user, login):
    user = await make_user("donor")
    headers = login(user)

    assert client.get(f"{API}/me", headers=headers).status_code == 200

    from app.db.session import SessionFactory

    async with SessionFactory() as session:
        from app.repositories import users as users_repo

        row = await users_repo.get_by_id(session, user.id)
        row.is_active = False
        await session.commit()

    # The still-valid bearer token is no longer enough: authority comes from
    # the database, not from the token.
    assert client.get(f"{API}/me", headers=headers).status_code == 403


async def test_me_reflects_a_role_change_without_reissue(client, make_user, login):
    user = await make_user("donor")
    headers = login(user)

    from app.db.session import SessionFactory

    async with SessionFactory() as session:
        from app.repositories import users as users_repo

        row = await users_repo.get_by_id(session, user.id)
        await users_repo.set_role(session, row, "community_member")
        await session.commit()

    body = client.get(f"{API}/me", headers=headers).json()
    assert body["role"] == "community_member"


# --- refresh ---------------------------------------------------------------


async def test_refresh_rotates_both_tokens(client, make_user, login):
    user = await make_user("donor")
    login_response = client.post(
        f"{API}/login", json={"email": user.email, "password": "correct-horse-1"}
    ).json()

    refreshed = client.post(
        f"{API}/refresh", json={"refresh_token": login_response["refresh_token"]}
    )
    assert refreshed.status_code == 200, refreshed.text
    body = refreshed.json()
    assert body["access_token"] != login_response["access_token"]
    assert body["refresh_token"] != login_response["refresh_token"]

    # The new access token is usable.
    assert (
        client.get(f"{API}/me", headers={"Authorization": f"Bearer {body['access_token']}"}).status_code
        == 200
    )


async def test_refresh_rejects_an_access_token(client, make_user, login):
    user = await make_user("donor")
    headers = login(user)
    access = headers["Authorization"].split(" ", 1)[1]

    response = client.post(f"{API}/refresh", json={"refresh_token": access})
    assert response.status_code == 401


async def test_refresh_rejects_garbage(client, clean_db):
    response = client.post(f"{API}/refresh", json={"refresh_token": "nonsense"})
    assert response.status_code == 401


async def test_refresh_rejects_expired_token(client, make_user):
    user = await make_user("donor")
    expired = create_token(
        user_id=user.id, role=user.role, token_type="refresh", ttl_seconds=-5
    )
    response = client.post(f"{API}/refresh", json={"refresh_token": expired})
    assert response.status_code == 401
