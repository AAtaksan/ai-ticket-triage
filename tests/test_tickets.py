"""Ticket CRUD + auth-scoping + pagination."""
import pytest


async def test_create_ticket_returns_202(client, auth_headers):
    resp = await client.post(
        "/tickets",
        headers=auth_headers,
        json={"subject": "Charged twice!", "body": "Two $29 charges this month."},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "new"
    assert "id" in data


async def test_list_tickets_pagination(client, auth_headers):
    for i in range(3):
        await client.post(
            "/tickets",
            headers=auth_headers,
            json={"subject": f"subject {i}", "body": f"body number {i} here"},
        )
    resp = await client.get("/tickets?page=1&size=2", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert data["pages"] == 2
    assert len(data["items"]) == 2


async def test_get_single_ticket(client, auth_headers):
    created = await client.post(
        "/tickets",
        headers=auth_headers,
        json={"subject": "Login broken", "body": "cannot sign in at all"},
    )
    tid = created.json()["id"]
    resp = await client.get(f"/tickets/{tid}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == tid


async def test_customer_cannot_see_others_ticket(client, auth_headers):
    # customer A creates a ticket
    created = await client.post(
        "/tickets",
        headers=auth_headers,
        json={"subject": "private", "body": "customer A only content"},
    )
    tid = created.json()["id"]

    # customer B registers + logs in
    await client.post(
        "/auth/register",
        json={"email": "b2@example.com", "password": "password123"},
    )
    login = await client.post(
        "/auth/login",
        json={"email": "b2@example.com", "password": "password123"},
    )
    headers_b = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await client.get(f"/tickets/{tid}", headers=headers_b)
    assert resp.status_code == 404  # hidden from other customers


async def test_customer_cannot_patch(client, auth_headers):
    created = await client.post(
        "/tickets",
        headers=auth_headers,
        json={"subject": "x", "body": "some body content"},
    )
    tid = created.json()["id"]
    resp = await client.patch(
        f"/tickets/{tid}", headers=auth_headers, json={"category": "bug"}
    )
    assert resp.status_code == 403  # agents only
