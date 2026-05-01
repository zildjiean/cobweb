async def test_register_login_me(client):
    # register
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "alice@example.com",
            "password": "Sup3rSecretPassw0rd!",
            "full_name": "Alice",
            "org_name": "Acme",
        },
    )
    assert r.status_code == 201, r.text
    tokens = r.json()
    assert tokens["access_token"]

    # me
    r = await client.get(
        "/api/v1/auth/me",
        headers={"authorization": f"Bearer {tokens['access_token']}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["email"] == "alice@example.com"
    assert body["role"] == "admin"

    # login
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "Sup3rSecretPassw0rd!"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["access_token"]


async def test_register_duplicate(client):
    payload = {
        "email": "dup@example.com",
        "password": "Sup3rSecretPassw0rd!",
        "full_name": "Dup",
        "org_name": "DupCo",
    }
    r1 = await client.post("/api/v1/auth/register", json=payload)
    assert r1.status_code == 201
    r2 = await client.post("/api/v1/auth/register", json=payload)
    assert r2.status_code == 409


async def test_project_crud_rbac(client):
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "bob@example.com",
            "password": "Sup3rSecretPassw0rd!",
            "full_name": "Bob",
            "org_name": "BobCo",
        },
    )
    token = r.json()["access_token"]
    headers = {"authorization": f"Bearer {token}"}

    # create
    r = await client.post(
        "/api/v1/projects",
        json={"name": "Web App", "slug": "web-app", "description": "main"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    pid = r.json()["id"]

    # list
    r = await client.get("/api/v1/projects", headers=headers)
    assert r.status_code == 200
    assert len(r.json()) == 1

    # add target
    r = await client.post(
        f"/api/v1/projects/{pid}/targets",
        json={"name": "prod", "base_url": "https://example.com/"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "pending_verification"
