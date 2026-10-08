import blocklists
import dns_records
import stats


def test_dns_plan_add_update_unchanged():
    desired = {"a.lab": "10.0.0.1", "b.lab": "10.0.0.2", "c.lab": "10.0.0.3"}
    current = {"a.lab": "10.0.0.1", "b.lab": "10.0.0.99"}
    add, update, remove, same = dns_records.plan_changes(desired, current)
    assert add == {"c.lab": "10.0.0.3"}
    assert update == {"b.lab": ("10.0.0.99", "10.0.0.2")}
    assert remove == {}
    assert same == ["a.lab"]


def test_dns_plan_prune_only_when_asked():
    desired = {"a.lab": "10.0.0.1"}
    current = {"a.lab": "10.0.0.1", "old.lab": "10.0.0.9"}
    assert dns_records.plan_changes(desired, current)[2] == {}
    assert dns_records.plan_changes(desired, current, prune=True)[2] == {"old.lab": "10.0.0.9"}


def test_dns_plan_is_idempotent():
    state = {"a.lab": "10.0.0.1"}
    add, update, remove, same = dns_records.plan_changes(state, state, prune=True)
    assert not add and not update and not remove and same == ["a.lab"]


def test_blocklist_plan():
    add, remove = blocklists.plan_changes(["u1", "u2"], ["u2", "u3"])
    assert add == ["u1"] and remove == []
    add, remove = blocklists.plan_changes(["u1", "u2"], ["u2", "u3"], prune=True)
    assert add == ["u1"] and remove == ["u3"]


def test_format_report():
    out = stats.format_report(
        {
            "queries_total": 14382,
            "queries_blocked": 3901,
            "percent_blocked": 27.1,
            "unique_domains": 800,
            "active_clients": 9,
            "top_blocked": [("ads.example.com", 412)],
            "top_permitted": [],
            "top_clients": [("laptop", 4108)],
        }
    )
    assert "14,382" in out and "27.1%" in out and "ads.example.com (412)" in out
    assert "Top permitted:  none" in out
