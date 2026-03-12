"""
tests/integration/test_retrieval_api.py

Integration tests for the PKE retrieval API endpoint.

═══════════════════════════════════════════════════════════════════
WHAT THIS FILE TESTS
═══════════════════════════════════════════════════════════════════

The POST /query endpoint is the boundary between the PKE system and
its consumers — currently the Obsidian insight plugin, and eventually
any other interface built on top of the retrieval API.

This file tests that boundary: what the API accepts, what it returns,
and how it behaves when things go wrong. It is the closest thing in
this codebase to a CONTRACT TEST.

═══════════════════════════════════════════════════════════════════
WHAT MAKES THIS A CONTRACT TEST
═══════════════════════════════════════════════════════════════════

A contract test verifies a PROMISE made at a boundary between two
systems — in this case, the promise the PKE API makes to its
consumers (the Obsidian plugin).

The contract is written in pke/api/models/query.py:

    QueryRequest defines what the API will accept:
        - query:    required string, minimum length 1
        - notebook: optional string filter
        - limit:    integer between 1 and 20, default 5

    QueryResponse defines what the API will return:
        - query:    the original query echoed back
        - results:  list of QueryResult objects

    QueryResult defines the shape of each result:
        - note_id, note_title, notebook, matched_text (required)
        - similarity_score, result_type (required)
        - chunk_index, section_title, entry_timestamp (optional)
        - resource_ids (list, defaults to [])

These tests verify that the API honours every part of that promise.
If any part of the contract is violated — a field goes missing, a
type changes, a validation rule is relaxed — a test here fails.

═══════════════════════════════════════════════════════════════════
CONTRACT TESTS VS UNIT TESTS VS INTEGRATION TESTS
═══════════════════════════════════════════════════════════════════

Unit test:
    Tests a single class or function in isolation.
    Example: test_retriever.py — tests Retriever logic with mocks.

Integration test:
    Tests that multiple components work together correctly.
    Example: this file — tests the full request/response cycle
    through FastAPI, Pydantic validation, and the route handler.

Contract test:
    Tests that a boundary between two systems honours its defined
    promise, from the perspective of the consumer.
    Example: this file — tests that POST /query returns exactly
    what the Obsidian plugin has been built to expect.

This file sits at the intersection of integration and contract
testing. It is integration because it exercises the full FastAPI
stack. It is contract because every test is framed around the
consumer's expectations, not the implementation's internals.

═══════════════════════════════════════════════════════════════════
HOW THE FASTAPI TESTCLIENT WORKS
═══════════════════════════════════════════════════════════════════

FastAPI's TestClient wraps the application with a requests-compatible
interface. It sends real HTTP requests through the full application
stack — routing, middleware, Pydantic validation, route handlers —
but without starting a real server or making real network calls.

    client = TestClient(app)
    response = client.post("/query", json={"query": "Ireland"})
    assert response.status_code == 200

This exercises the same code paths as a real HTTP request, giving
us confidence that what works in tests will work in production.

═══════════════════════════════════════════════════════════════════
WHY WE PATCH THE RETRIEVER
═══════════════════════════════════════════════════════════════════

The retriever is constructed once at application startup in main.py
and stored as a module-level attribute. The route handler imports it
directly from that module.

We patch it at the module where it is USED (pke.api.routes.query),
not where it is defined. This is the standard Python patching rule:
patch the name in the namespace where it is looked up.

    with patch("pke.api.main.retriever", mock_retriever):
        response = client.post("/query", json={"query": "test"})

This means these tests exercise the full API stack — request
validation, route handling, response serialisation — without
touching Supabase or OpenAI.

═══════════════════════════════════════════════════════════════════
TEST STRUCTURE
═══════════════════════════════════════════════════════════════════

    TestQueryEndpointHappyPath    — valid requests return correct responses
    TestQueryParameterForwarding  — optional params reach the retriever
    TestRequestValidation         — invalid requests are rejected correctly
    TestErrorHandling             — retriever failures become 500 responses
    TestMultipleResults           — multiple results returned in correct order
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from pke.api.main import app
from pke.api.models.query import QueryResult

# ═══════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def client():
    """
    A TestClient wrapping the PKE FastAPI application.

    Reused across all tests in this file. Each test gets a fresh
    request context — no state leaks between tests.
    """
    return TestClient(app)


def make_query_result(
    note_id="note-uuid-1",
    note_title="Ireland 2019",
    notebook="Travel",
    matched_text="We arrived in Dublin on a grey morning.",
    similarity_score=0.82,
    chunk_index=2,
    section_title="Day 1",
    entry_timestamp="2019-06-01",
    resource_ids=None,
    result_type="chunk",
):
    """
    Build a QueryResult object with sensible defaults.

    QueryResult is the Pydantic model that defines the contract
    for each individual result returned by the API. Tests use this
    factory to create realistic results without repeating boilerplate.
    """
    return QueryResult(
        note_id=note_id,
        note_title=note_title,
        notebook=notebook,
        matched_text=matched_text,
        similarity_score=similarity_score,
        chunk_index=chunk_index,
        section_title=section_title,
        entry_timestamp=entry_timestamp,
        resource_ids=resource_ids or [],
        result_type=result_type,
    )


@pytest.fixture
def mock_retriever():
    """
    A mock retriever that returns one realistic QueryResult by default.

    Individual tests can override mock_retriever.query.return_value
    or mock_retriever.query.side_effect to simulate different
    retrieval outcomes.
    """
    mock = MagicMock()
    mock.query.return_value = [make_query_result()]
    return mock


# ═══════════════════════════════════════════════════════════════════
# TEST CLASSES
# ═══════════════════════════════════════════════════════════════════


class TestQueryEndpointHappyPath:
    """
    Verify that valid requests return the correct response structure.

    These are the core contract tests — they verify that the API
    returns exactly what it has promised to return, in the shape
    the Obsidian plugin has been built to consume.

    Every field verified here corresponds to a field the plugin
    will read. If any assertion fails, the plugin will break.
    """

    def test_returns_200_with_valid_query(self, client, mock_retriever):
        """
        A valid request must return HTTP 200. Any other status code
        would indicate the API has failed to honour the contract
        for a request that meets all stated requirements.
        """
        with patch("pke.api.main.retriever", mock_retriever):
            response = client.post("/query", json={"query": "Ireland family history"})
        assert response.status_code == 200

    def test_response_contains_query_echo(self, client, mock_retriever):
        """
        The response must echo back the original query string.
        This allows the caller to correlate responses with requests,
        which matters when the plugin issues rapid queries during
        active writing with the debounce mechanism.
        """
        with patch("pke.api.main.retriever", mock_retriever):
            response = client.post("/query", json={"query": "Ireland family history"})
        assert response.json()["query"] == "Ireland family history"

    def test_response_contains_results_list(self, client, mock_retriever):
        """
        The response must contain a 'results' key holding a list.
        The plugin iterates this list to render the insight panel.
        A missing key or wrong type would cause a runtime error
        in the plugin.
        """
        with patch("pke.api.main.retriever", mock_retriever):
            response = client.post("/query", json={"query": "test"})
        data = response.json()
        assert "results" in data
        assert isinstance(data["results"], list)

    def test_all_result_fields_present_and_correct(self, client, mock_retriever):
        """
        Every field in the QueryResult contract must be present in
        the JSON response with the correct value and type.

        This is the core contract assertion. The Obsidian plugin
        reads every one of these fields:
            note_id         → constructs the deep link URL
            note_title      → displays as the result heading
            notebook        → displays as context label
            matched_text    → displays as the passage text
            similarity_score → used for internal ranking decisions
            chunk_index     → used for paragraph-level navigation
            section_title   → displays as section context
            entry_timestamp → displays as the result date
            resource_ids    → used to render media attachments
            result_type     → determines which UI template to use
        """
        with patch("pke.api.main.retriever", mock_retriever):
            response = client.post("/query", json={"query": "test"})
        result = response.json()["results"][0]
        assert result["note_id"] == "note-uuid-1"
        assert result["note_title"] == "Ireland 2019"
        assert result["notebook"] == "Travel"
        assert result["matched_text"] == "We arrived in Dublin on a grey morning."
        assert result["similarity_score"] == 0.82
        assert result["chunk_index"] == 2
        assert result["section_title"] == "Day 1"
        assert result["entry_timestamp"] == "2019-06-01"
        assert result["resource_ids"] == []
        assert result["result_type"] == "chunk"

    def test_empty_results_returns_200_not_404(self, client):
        """
        When the retriever finds no matches, the API must return 200
        with an empty results list — not 404 or any error status.

        Empty results are a valid and expected state (a new note
        with no semantic matches in the corpus). The plugin must
        handle this gracefully, and it can only do so if the API
        returns a predictable response structure even when empty.
        """
        mock = MagicMock()
        mock.query.return_value = []
        with patch("pke.api.main.retriever", mock):
            response = client.post("/query", json={"query": "obscure topic"})
        assert response.status_code == 200
        assert response.json()["results"] == []


class TestQueryParameterForwarding:
    """
    Verify that optional request parameters are forwarded correctly
    to the retriever.

    WHY THIS MATTERS:
        The API contract defines optional parameters that the plugin
        can use to scope and control retrieval. If these are silently
        dropped or misrouted, the plugin's filtering and limit
        controls stop working without any error being raised.

        These tests verify the wiring between the HTTP request,
        the Pydantic model, and the retriever.query() call.
    """

    def test_notebook_filter_forwarded_to_retriever(self, client, mock_retriever):
        """
        When the plugin passes a notebook filter, it must reach
        retriever.query() as the notebook parameter. If it is
        silently dropped, all-notebook search runs instead and
        the user's scoping intention is ignored.
        """
        with patch("pke.api.main.retriever", mock_retriever):
            client.post("/query", json={"query": "test", "notebook": "Travel"})
        mock_retriever.query.assert_called_once_with(
            query_text="test",
            notebook="Travel",
            limit=5,
        )

    def test_limit_forwarded_to_retriever(self, client, mock_retriever):
        """
        When the plugin requests a specific number of results, that
        limit must reach the retriever. If not forwarded, the default
        of 5 always applies and the user's preference is ignored.
        """
        with patch("pke.api.main.retriever", mock_retriever):
            client.post("/query", json={"query": "test", "limit": 10})
        mock_retriever.query.assert_called_once_with(
            query_text="test",
            notebook=None,
            limit=10,
        )

    def test_defaults_applied_when_optional_params_absent(self, client, mock_retriever):
        """
        When optional parameters are not provided, the correct
        defaults must be applied: notebook=None (no filter),
        limit=5 (as defined in QueryRequest).
        """
        with patch("pke.api.main.retriever", mock_retriever):
            client.post("/query", json={"query": "test"})
        mock_retriever.query.assert_called_once_with(
            query_text="test",
            notebook=None,
            limit=5,
        )

    def test_date_filters_accepted_by_pydantic(self, client, mock_retriever):
        """
        date_from and date_to are defined in QueryRequest and must
        be accepted without a validation error. They are not yet
        forwarded to the retriever (deferred feature) but the API
        must not reject requests that include them.
        """
        with patch("pke.api.main.retriever", mock_retriever):
            response = client.post(
                "/query",
                json={
                    "query": "test",
                    "notebook": "Journal",
                    "limit": 7,
                    "date_from": "2020-01-01",
                    "date_to": "2023-12-31",
                },
            )
        assert response.status_code == 200


class TestRequestValidation:
    """
    Verify that invalid requests are rejected with HTTP 422.

    WHY THIS MATTERS:
        The QueryRequest Pydantic model defines the validation rules
        for the API contract. These rules protect the retriever from
        receiving malformed input that could cause silent failures or
        unexpected behaviour.

        HTTP 422 (Unprocessable Entity) is FastAPI's standard response
        for Pydantic validation failures. These tests verify that
        every validation rule in QueryRequest is actually enforced.

        This is also a contract test — the API is promising to reject
        certain inputs. If validation is relaxed, consumers who
        depend on clear error responses for bad input are affected.

    THE RULES BEING TESTED (from QueryRequest in models/query.py):
        query:   required field, min_length=1
        limit:   ge=1 (greater than or equal to 1)
                 le=20 (less than or equal to 20)
                 default=5
    """

    def test_missing_query_returns_422(self, client):
        """
        'query' is a required field — no default, no Optional.
        A request without it must be rejected. This protects the
        retriever from receiving an empty query string that would
        produce a meaningless embedding.
        """
        response = client.post("/query", json={})
        assert response.status_code == 422

    def test_empty_query_string_returns_422(self, client):
        """
        min_length=1 ensures the query is not an empty string.
        An empty string would embed to a near-zero vector and
        return arbitrary results — a confusing experience that
        should be caught at the validation layer, not the retriever.
        """
        response = client.post("/query", json={"query": ""})
        assert response.status_code == 422

    def test_limit_zero_returns_422(self, client):
        """
        ge=1 means limit must be at least 1. Requesting 0 results
        is not a meaningful operation and must be rejected rather
        than silently returning an empty list.
        """
        response = client.post("/query", json={"query": "test", "limit": 0})
        assert response.status_code == 422

    def test_limit_above_max_returns_422(self, client):
        """
        le=20 caps the maximum result count. This protects against
        callers requesting an unbounded number of results which would
        cause expensive RPC calls and large response payloads.
        """
        response = client.post("/query", json={"query": "test", "limit": 21})
        assert response.status_code == 422

    def test_limit_at_max_boundary_returns_200(self, client, mock_retriever):
        """
        limit=20 is the maximum allowed value and must be accepted.
        Boundary tests confirm that the validation rule is le=20
        (less than or equal) not lt=20 (strictly less than).
        """
        with patch("pke.api.main.retriever", mock_retriever):
            response = client.post("/query", json={"query": "test", "limit": 20})
        assert response.status_code == 200

    def test_limit_at_min_boundary_returns_200(self, client, mock_retriever):
        """
        limit=1 is the minimum allowed value and must be accepted.
        Boundary tests confirm the rule is ge=1 not gt=1.
        """
        with patch("pke.api.main.retriever", mock_retriever):
            response = client.post("/query", json={"query": "test", "limit": 1})
        assert response.status_code == 200

    def test_non_json_body_returns_422(self, client):
        """
        The API only accepts JSON. A malformed request body must be
        rejected. This is FastAPI's standard behaviour — confirmed
        here to document the contract explicitly.
        """
        response = client.post(
            "/query",
            content="not json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422


class TestErrorHandling:
    """
    Verify that retriever failures are surfaced as HTTP 500 responses
    with a meaningful error detail.

    WHY THIS MATTERS:
        The API contract includes a promise about failure behaviour:
        if retrieval fails for any reason (Supabase unreachable,
        OpenAI API error, unexpected exception), the API returns
        HTTP 500 with a 'detail' field describing the error.

        This is important for the Obsidian plugin — it needs to
        distinguish between "no results" (200 + empty list) and
        "retrieval failed" (500). Without this contract, the plugin
        cannot give the user meaningful feedback when the API is down.

        The try/except in the route handler (query.py) enforces this.
        These tests verify it works.
    """

    def test_retriever_exception_returns_500(self, client):
        """
        Any exception raised by the retriever must be caught and
        converted to HTTP 500. Unhandled exceptions would return
        500 anyway, but without a predictable response body.
        The explicit try/except ensures the response shape is
        consistent and the error message is included.
        """
        mock = MagicMock()
        mock.query.side_effect = Exception("Supabase connection failed")
        with patch("pke.api.main.retriever", mock):
            response = client.post("/query", json={"query": "test"})
        assert response.status_code == 500

    def test_500_response_contains_detail_key(self, client):
        """
        The 500 response body must contain a 'detail' key.
        This is the HTTPException contract in FastAPI — the plugin
        reads response.detail to display or log the error reason.
        """
        mock = MagicMock()
        mock.query.side_effect = Exception("Supabase connection failed")
        with patch("pke.api.main.retriever", mock):
            response = client.post("/query", json={"query": "test"})
        assert "detail" in response.json()

    def test_500_detail_contains_error_message(self, client):
        """
        The detail field must contain the exception message, not
        a generic "internal server error" string. This gives the
        plugin (and the developer) actionable information about
        what went wrong.
        """
        mock = MagicMock()
        mock.query.side_effect = Exception("Supabase connection failed")
        with patch("pke.api.main.retriever", mock):
            response = client.post("/query", json={"query": "test"})
        assert "Supabase connection failed" in response.json()["detail"]


class TestMultipleResults:
    """
    Verify that multiple results are returned in the correct order
    and with the correct structure.

    WHY THIS MATTERS:
        The plugin renders results in the order they are returned.
        The contract promise is that results are ranked by similarity
        score descending — the most relevant passage appears first.

        These tests verify the full round-trip: retriever returns
        ordered results → API serialises them → response preserves
        the order.
    """

    def test_multiple_results_returned_in_order(self, client):
        """
        Results must appear in the response in the same order
        the retriever returned them (already ranked by score).
        JSON serialisation must not reorder them.
        """
        results = [
            make_query_result(note_id="a", similarity_score=0.90),
            make_query_result(note_id="b", similarity_score=0.75),
            make_query_result(note_id="c", similarity_score=0.60),
        ]
        mock = MagicMock()
        mock.query.return_value = results
        with patch("pke.api.main.retriever", mock):
            response = client.post("/query", json={"query": "test"})
        returned = response.json()["results"]
        assert len(returned) == 3
        assert returned[0]["note_id"] == "a"
        assert returned[1]["note_id"] == "b"
        assert returned[2]["note_id"] == "c"

    def test_result_count_matches_retriever_output(self, client):
        """
        The API must return exactly as many results as the retriever
        provides. No silent truncation or padding.
        """
        results = [make_query_result(note_id=f"id-{i}") for i in range(7)]
        mock = MagicMock()
        mock.query.return_value = results
        with patch("pke.api.main.retriever", mock):
            response = client.post("/query", json={"query": "test", "limit": 7})
        assert len(response.json()["results"]) == 7
