import json
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "bakery"


def secrets_in(am, *strings, allow=None):
    meta = {}
    if allow is not None:
        meta["secret_allow"] = allow
    return am.find_secrets({"$schema": "archmap/1", "meta": meta, "gotchas": list(strings)})


@pytest.mark.parametrize(
    "text,rule",
    [
        ("postgres://u:p@h/db", "connection-string"),
        ("password = hunter2hunter2", "assignment"),
        ("API_KEY: abcdef1", "assignment"),
        ("api-key=zzzzzz", "assignment"),
        ("0123456789abcdef0123456789abcdef", "hex-token"),
        ("(0123456789ABCDEF0123456789ABCDEF0)", "hex-token"),
        ("Zm9vQmFyMTIzNDU2Nzg5MEFiQ2RFZkdoSWpLbE1uT3A=", "base64-token"),
        ("sk-" + "abcdefghij" * 3, "key-prefix"),
        ("ghp_" + "a1" * 20, "key-prefix"),
        ("github_pat_" + "A1b2" * 10, "key-prefix"),
        ("AKIAABCDEFGHIJKLMNOP", "key-prefix"),
        ("xoxb-1234567890-abcdef", "key-prefix"),
        ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0", "key-prefix"),
    ],
)
def test_detected(am, text, rule):
    problems = secrets_in(am, text)
    assert {p.code for p in problems} == {"secret-suspect"}
    assert any(rule in p.message for p in problems)  # a value may trip more than one rule
    assert {p.where for p in problems} == {"gotchas[0]"}


@pytest.mark.parametrize(
    "text",
    [
        "0123456789abcdef0123456789abcdef01234567",  # 40 hex: a commit id
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",  # 64 hex
        "123e4567-e89b-12d3-a456-426614174000",  # UUID
        "app/Http/Controllers/Auth/OAuth2CallbackController.php",
        "src/Billing/InvoiceRepositoryFactory2Interface/ExtraLongDirectoryName1/File.php",
        "task-queue",
        "disk-cache",
        "risk-assessment-and-task-scheduling-notes",
        "https://example.com/path",
        "https://user@example.com/path",
        "The order service keeps the cart until the customer pays.",
        "Сервис хранит корзину до оплаты, затем создаёт заказ.",
        "token: ok",
        "AKIA is a prefix of AWS key ids",
        "ThisIsALongCamelCaseIdentifierWithoutAnyDigitsAtAllInIt",
    ],
)
def test_not_detected(am, text):
    assert secrets_in(am, text) == []


def test_message_never_echoes_the_whole_value(am):
    value = "sk-" + "abcdefghij" * 3
    problem = secrets_in(am, value)[0]
    assert value not in problem.message
    assert problem.message.endswith("sk-a…")


def test_only_values_are_scanned_not_keys_or_schema(am):
    secret = "0123456789abcdef0123456789abcdef"
    data = {"$schema": secret, "meta": {secret: "fine"}, "sections": {secret: {"title": "t"}}}
    assert am.find_secrets(data) == []


def test_nested_values_get_a_json_path(am):
    secret = "0123456789abcdef0123456789abcdef"
    data = {
        "nodes": [{"id": "api", "summary": secret}],
        "flows": [{"id": "f", "steps": [{"note": secret}]}],
        "sections": {"x": {"body": {"k": [secret]}}},
    }
    wheres = sorted(p.where for p in am.find_secrets(data))
    assert wheres == ["flows[f].steps[0].note", "nodes[api].summary", "sections.x.body.k[0]"]


def test_allow_suppresses_and_is_used(am):
    text = "password = devpassword"
    problems = secrets_in(am, text, allow=[{"match": "password = devpassword", "why": "sample"}])
    assert problems == []


def test_allow_without_why(am):
    text = "password = devpassword"
    problems = secrets_in(am, text, allow=[{"match": "devpassword"}])
    assert [p.code for p in problems] == ["secret-allow-no-why"]
    assert problems[0].where == "meta.secret_allow[0].why"


def test_unused_allow(am):
    problems = secrets_in(am, "plain", allow=[{"match": "nothing", "why": "x"}])
    assert [p.code for p in problems] == ["secret-allow-unused"]


def test_secret_allow_subtree_is_not_scanned(am):
    secret = "0123456789abcdef0123456789abcdef"
    problems = secrets_in(am, secret, allow=[{"match": secret, "why": "x"}])
    assert problems == []


def test_find_secrets_never_raises_on_garbage(am):
    for value in [None, 5, "x", [], [1], {"meta": 1}, {"meta": {"secret_allow": [1, {}, {"match": 3}]}}]:
        assert isinstance(am.find_secrets(value), list)
    deep = cur = []
    for _ in range(500):
        nxt = []
        cur.append(nxt)
        cur = nxt
    assert isinstance(am.find_secrets({"x": deep}), list)


def test_check_map_reports_secrets(am):
    data = json.loads((FIXTURE / "docs" / "architecture-map.json").read_text(encoding="utf-8"))
    data["gotchas"].append("postgres://u:p@h/db")
    codes = [p.code for p in am.check_map(data, FIXTURE)]
    assert codes == ["secret-suspect"]
