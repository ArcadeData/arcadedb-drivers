import httpx
import pytest
import respx
from arcadedb_driver import ArcadeDBError, ArcadeDBServer, AsyncArcadeDBServer

BASE_URL = "http://db.test"


@respx.mock
def test_promql_labels_returns_the_generated_model() -> None:
    respx.get(f"{BASE_URL}/api/v1/ts/mydb/prom/api/v1/labels").mock(
        return_value=httpx.Response(200, json={"status": "success", "data": ["__name__", "host"]})
    )
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        result = srv.db("mydb").promql.labels()

    assert result.data == ["__name__", "host"]


@respx.mock
def test_grafana_query_reaches_the_right_route() -> None:
    # `grafana.query` is hand-written for the same reason as `db.ts.query`/`db.ts.latest`
    # (see facade/timeseries.py's module docstring): the contract types
    # `GrafanaQueryResponse`'s per-element DataFrame values as `"type": "object"`, so
    # it returns the parsed JSON body directly instead of the generated model.
    route = respx.post(f"{BASE_URL}/api/v1/ts/mydb/grafana/query").mock(
        return_value=httpx.Response(200, json={"results": {}})
    )
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        result = srv.db("mydb").grafana.query(body={"targets": []})

    assert route.called
    assert result == {"results": {}}


@respx.mock
def test_grafana_query_raises_on_a_non_2xx() -> None:
    respx.post(f"{BASE_URL}/api/v1/ts/mydb/grafana/query").mock(
        return_value=httpx.Response(400, json={"error": "unknown time-series type"})
    )
    with ArcadeDBServer(base_url=BASE_URL) as srv, pytest.raises(ArcadeDBError) as caught:
        srv.db("mydb").grafana.query(body={"targets": [{"type": "does-not-exist"}]})

    assert caught.value.error == "unknown time-series type"


@respx.mock
def test_promql_query_sends_exactly_the_generated_operations_parameters() -> None:
    # `promql.query` used to accept `**kwargs: Any` and forward every one of them
    # straight into `prom_ql_query.sync_detailed`, which opted this call site out
    # of mypy --strict. Now it names `query`/`time`/`lookback_delta` explicitly,
    # matching the generated operation; this pins the query string it sends.
    route = respx.get(f"{BASE_URL}/api/v1/ts/mydb/prom/api/v1/query").mock(
        return_value=httpx.Response(200, json={"status": "success", "data": {"resultType": "vector", "result": []}})
    )
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        srv.db("mydb").promql.query(query="up", time="2024-01-01T00:00:00Z")

    params = dict(route.calls.last.request.url.params)
    assert params == {"query": "up", "time": "2024-01-01T00:00:00Z"}


def test_promql_query_rejects_an_unknown_keyword_at_call_time() -> None:
    with ArcadeDBServer(base_url=BASE_URL) as srv, pytest.raises(TypeError):
        srv.db("mydb").promql.query(query="up", timestamp="2024-01-01T00:00:00Z")  # type: ignore[call-arg]


@respx.mock
def test_promql_query_range_sends_exactly_the_generated_operations_parameters() -> None:
    route = respx.get(f"{BASE_URL}/api/v1/ts/mydb/prom/api/v1/query_range").mock(
        return_value=httpx.Response(200, json={"status": "success", "data": {"resultType": "vector", "result": []}})
    )
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        srv.db("mydb").promql.query_range(query="up", start="0", end="60", step="15")

    params = dict(route.calls.last.request.url.params)
    assert params == {"query": "up", "start": "0", "end": "60", "step": "15"}


@respx.mock
def test_promql_series_sends_exactly_the_generated_operations_parameters() -> None:
    route = respx.get(f"{BASE_URL}/api/v1/ts/mydb/prom/api/v1/series").mock(
        return_value=httpx.Response(200, json={"status": "success", "data": []})
    )
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        srv.db("mydb").promql.series(match=["up", "down"])

    params = route.calls.last.request.url.params
    assert params.get_list("match[]") == ["up", "down"]
    assert "start" not in params
    assert "end" not in params


@pytest.mark.asyncio
@respx.mock
async def test_async_promql_query_sends_exactly_the_generated_operations_parameters() -> None:
    route = respx.get(f"{BASE_URL}/api/v1/ts/mydb/prom/api/v1/query").mock(
        return_value=httpx.Response(200, json={"status": "success", "data": {"resultType": "vector", "result": []}})
    )
    async with AsyncArcadeDBServer(base_url=BASE_URL) as srv:
        await srv.db("mydb").promql.query(query="up")

    params = dict(route.calls.last.request.url.params)
    assert params == {"query": "up"}


@pytest.mark.asyncio
async def test_async_promql_query_rejects_an_unknown_keyword_at_call_time() -> None:
    async with AsyncArcadeDBServer(base_url=BASE_URL) as srv:
        with pytest.raises(TypeError):
            await srv.db("mydb").promql.query(query="up", timestamp="now")  # type: ignore[call-arg]


@respx.mock
def test_the_namespaces_are_cached_per_database_handle() -> None:
    with ArcadeDBServer(base_url=BASE_URL) as srv:
        db = srv.db("mydb")
        assert db.ts is db.ts
        assert db.grafana is db.grafana
        assert db.promql is db.promql
