"""Auth flow: register, duplicate, login, bad password, protected route."""
import pytest


async def test_register_returns_user(client):
    resp = await client.post(
        "/auth/register",
        json={"email": "a@example.com", "password": "password123"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "a@example.com"
    assert data["role"] == "customer"
    assert "id" in data


async def test_register_duplicate_conflicts(client):
    body = {"email": "dup@example.com", "password": "password123"}
    await client.post("/auth/register", json=body)
    resp = await client.post("/auth/register", json=body)
    assert resp.status_code == 409


async def test_login_success_returns_token(client):
    await client.post(
        "/auth/register",
        json={"email": "b@example.com", "password": "password123"},
    )
    resp = await client.post(
        "/auth/login",
        json={"email": "b@example.com", "password": "password123"},
    )
    assert resp.status_code == 200
    assert resp.json()["access_token"]
    assert resp.json()["token_type"] == "bearer"


async def test_login_wrong_password(client):
    await client.post(
        "/auth/register",
        json={"email": "c@example.com", "password": "password123"},
    )
    resp = await client.post(
        "/auth/login",
        json={"email": "c@example.com", "password": "wrongpass1"},
    )
    assert resp.status_code == 401


async def test_protected_route_requires_token(client):
    resp = await client.post(
        "/tickets", json={"subject": "hi", "body": "there is a problem"}
    )
    assert resp.status_code == 401
