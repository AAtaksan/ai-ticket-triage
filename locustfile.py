"""Load test for ticket creation.

Run (after `pip install locust` and with the API up):
    locust -f locustfile.py --host http://localhost:8000

Then open http://localhost:8089, set users + spawn rate, and watch p95 latency.
Record the numbers for your README (e.g. "sustained 200 req/s, p95 85ms").
"""
import random
import string

from locust import HttpUser, between, task


def rand(n=8):
    return "".join(random.choices(string.ascii_lowercase, k=n))


class TicketUser(HttpUser):
    wait_time = between(0.1, 0.5)

    def on_start(self):
        email = f"{rand()}@load.test"
        self.client.post("/auth/register", json={"email": email, "password": "password123"})
        r = self.client.post("/auth/login", json={"email": email, "password": "password123"})
        self.headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    @task
    def create_ticket(self):
        self.client.post(
            "/tickets",
            headers=self.headers,
            json={"subject": f"Issue {rand()}", "body": f"Something is wrong: {rand(20)}"},
        )
