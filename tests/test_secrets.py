import base64
import hashlib
import json
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "bakery"

HEX32 = "0123456789abcdef0123456789abcdef"
RANDOM_B64 = base64.urlsafe_b64encode(hashlib.sha256(b"x").digest() * 2).decode()


def secrets_in(am, *strings, allow=None):
    meta = {}
    if allow is not None:
        meta["secret_allow"] = allow
    return am.find_secrets({"$schema": "archmap/1", "meta": meta, "gotchas": list(strings)})


@pytest.mark.parametrize(
    "text,rule",
    [
        ("postgres://u:p@h/db", "connection-string"),
        ("redis://:s3cretpass@cache:6379/0", "connection-string"),
        ("password = hunter2hunter2", "assignment"),
        ("password=Tr0ub4dor&3", "assignment"),
        ("API_KEY: abcdef1", "assignment"),
        ("api-key=zzzzzz1", "assignment"),
        ("DB_PASSWORD=hunter2hunter2", "assignment"),
        ("GITHUB_TOKEN=abcdef123456", "assignment"),
        ("client_secret: 9f8e7d6c5b4a", "assignment"),
        ("access_token=abcdef123456", "assignment"),
        ("STRIPE_API_KEY=sk_test_abc123", "assignment"),
        ("AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMIK7MDENGbPxRfiCY", "assignment"),
        ("SECRET_KEY = 'django-insecure-abc'", "assignment"),
        (HEX32, "hex-token"),
        ("(0123456789ABCDEF0123456789ABCDEF0)", "hex-token"),
        ("`" + HEX32 + "`", "hex-token"),
        ("<" + HEX32 + ">", "hex-token"),
        ("the id is " + HEX32 + ".", "hex-token"),
        ("https://example.com/cb?key=" + HEX32, "hex-token"),
        ("https://example.com/cb?a=1&x=" + HEX32 + "&b=2", "hex-token"),
        (RANDOM_B64, "base64-token"),
        ("**" + RANDOM_B64 + "**", "base64-token"),
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


def test_random_samples_clear_the_entropy_floor(am):
    from archmap import secrets

    assert secrets.entropy(RANDOM_B64) >= 4.4


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
        "AKIA is a prefix of AWS key ids",
        "OAuth2CallbackControllerIntegrationTestCase",
        "AwsS3StorageAdapterServiceProviderInterface",
        "App_Http_Controllers_Auth_OAuth2CallbackController",
        "test_OAuth2CallbackController_handles_expired_tokens",
        "Order-Service-V2-Handles-Payment-Callbacks",
        "ThisIsALongCamelCaseIdentifierWithoutAnyDigitsAtAllInIt",
        "token: ok",
        "token: refresh",
        "password: required",
        "Secret: rotated monthly",
        "the token: issued by Keycloak",
        "password: ${DB_PASSWORD}",
        "password: $DB_PASSWORD",
        "token=<redacted>",
        "api_key: {{ api_key }}",
        "password = %(password)s",
        "password: ********",
        "password: xxxxxxxx",
        "SET password = :password",
        "WHERE token = :token",
        "password reset flow",
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
    data = {"$schema": HEX32, "meta": {HEX32: "fine"}, "sections": {HEX32: {"title": "t"}}}
    assert am.find_secrets(data) == []


def test_nested_values_get_a_json_path(am):
    data = {
        "nodes": [{"id": "api", "summary": HEX32}],
        "flows": [{"id": "f", "steps": [{"note": HEX32}]}],
        "sections": {"x": {"body": {"k": [HEX32]}}},
    }
    wheres = sorted(p.where for p in am.find_secrets(data))
    assert wheres == ["flows[f].steps[0].note", "nodes[api].summary", "sections.x.body.k[0]"]


def test_allow_suppresses_and_is_used(am):
    problems = secrets_in(am, "password = devpass123", allow=[{"match": "password = devpass123", "why": "s"}])
    assert problems == []


def test_allow_covers_only_the_matched_span(am):
    key = "AKIA" + "ABCDEFGHIJKLMNOP"
    text = "postgres://u:p@localhost/db; prod key " + key
    problems = secrets_in(am, text, allow=[{"match": "postgres://u:p@localhost", "why": "dev sample"}])
    assert [p.code for p in problems] == ["secret-suspect"]
    assert "key-prefix" in problems[0].message


def test_short_allow_match_does_not_suppress(am):
    problems = secrets_in(am, "password = devpass123", allow=[{"match": "e", "why": "x"}])
    assert [p.code for p in problems] == ["secret-suspect"]


def test_short_allow_match_is_a_field_error(am):
    data = json.loads((FIXTURE / "docs" / "architecture-map.json").read_text(encoding="utf-8"))
    data["meta"]["secret_allow"].append({"match": "short", "why": "x"})
    problems = am.check_map(data, FIXTURE)
    assert [(p.code, p.where) for p in problems] == [("field-invalid", "meta.secret_allow[1].match")]


def test_allow_without_why(am):
    problems = secrets_in(am, "password = devpass123", allow=[{"match": "password = devpass123"}])
    assert [p.code for p in problems] == ["secret-allow-no-why"]
    assert problems[0].where == "meta.secret_allow[0].why"


def test_unused_allow(am):
    problems = secrets_in(am, "plain", allow=[{"match": "nothing-here", "why": "x"}])
    assert [p.code for p in problems] == ["secret-allow-unused"]


def test_secret_allow_subtree_is_not_scanned(am):
    assert secrets_in(am, HEX32, allow=[{"match": HEX32, "why": "x"}]) == []


def test_find_secrets_never_raises_on_garbage(am):
    for value in [None, 5, "x", [], [1], {"meta": 1}, {"meta": {"secret_allow": [1, {}, {"match": 3}]}}]:
        assert isinstance(am.find_secrets(value), list)


def test_deep_nesting_is_scanned_without_a_cap(am):
    deep = cur = []
    for _ in range(500):
        nxt = []
        cur.append(nxt)
        cur = nxt
    cur.append(HEX32)
    problems = am.find_secrets({"x": deep})
    assert [p.code for p in problems] == ["secret-suspect"]


def test_check_map_reports_secrets(am):
    data = json.loads((FIXTURE / "docs" / "architecture-map.json").read_text(encoding="utf-8"))
    data["gotchas"].append("postgres://u:p@h/db")
    assert [p.code for p in am.check_map(data, FIXTURE)] == ["secret-suspect"]
