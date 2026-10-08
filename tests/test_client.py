import pytest

from pihole_client import PiholeClient, PiholeError


class FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload if payload is not None else {}
        self.content = b"x" if payload is not None else b""
        self.text = ""

    def json(self):
        return self._payload


def make_client(responses):
    client = PiholeClient("http://pihole.test", password="pw")
    calls = []

    def fake_request(method, url, headers=None, timeout=None, **kwargs):
        calls.append((method, url, headers, kwargs))
        return responses.pop(0)

    client.session.request = fake_request
    return client, calls


def test_login_sets_sid_and_sends_it_afterwards():
    client, calls = make_client(
        [
            FakeResponse(200, {"session": {"valid": True, "sid": "abc"}}),
            FakeResponse(200, {"queries": {"total": 1}}),
        ]
    )
    client.login()
    client.summary()
    assert calls[1][2]["sid"] == "abc"
    assert calls[1][1] == "http://pihole.test/api/stats/summary"


def test_bad_password_raises():
    client, _ = make_client([FakeResponse(200, {"session": {"valid": False, "message": "nope"}})])
    with pytest.raises(PiholeError, match="Login rejected"):
        client.login()


def test_missing_password_raises(monkeypatch):
    monkeypatch.delenv("PIHOLE_PASSWORD", raising=False)
    with pytest.raises(PiholeError, match="PIHOLE_PASSWORD"):
        PiholeClient("http://pihole.test").login()


def test_get_hosts_parses_entries():
    client, _ = make_client(
        [FakeResponse(200, {"config": {"dns": {"hosts": ["10.0.0.1 a.lab", "10.0.0.2 b.lab"]}}})]
    )
    assert client.get_hosts() == {"a.lab": "10.0.0.1", "b.lab": "10.0.0.2"}


def test_add_host_url_encodes_entry():
    client, calls = make_client([FakeResponse(201, {})])
    client.add_host("a.lab", "10.0.0.1")
    assert calls[0][0] == "PUT"
    assert calls[0][1].endswith("/api/config/dns/hosts/10.0.0.1%20a.lab")


def test_update_gravity_accepts_plain_text_response():
    class TextResponse(FakeResponse):
        def json(self):
            raise ValueError("not json")

    resp = TextResponse(200, {})
    resp.content = b"[i] Neutrino emissions detected..."
    resp.text = "[i] Neutrino emissions detected..."
    client, calls = make_client([resp])
    client.update_gravity()  # must not raise
    assert calls[0][1].endswith("/api/action/gravity")


def test_http_error_message():
    client, _ = make_client([FakeResponse(400, {"error": {"message": "bad request"}})])
    with pytest.raises(PiholeError, match="bad request"):
        client.get_lists()
