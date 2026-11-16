from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import janitor.tools as tools


# --- Date helpers -----------------------------------------------------------


def test_get_current_date_is_today_in_iso_format():
    assert tools.get_current_date() == datetime.today().strftime("%Y-%m-%d")


@pytest.mark.parametrize(
    "start, days, expected",
    [
        ("2026-01-01", 7, "2026-01-08"),
        ("2026-01-28", 7, "2026-02-04"),  # month rollover
        ("2026-12-29", 7, "2027-01-05"),  # year rollover
        ("2028-02-28", 1, "2028-02-29"),  # leap day
        ("2026-03-10", -7, "2026-03-03"),  # negative days subtract
        ("2026-03-10", 0, "2026-03-10"),
    ],
)
def test_add_days_to_date(start, days, expected):
    assert tools.add_days_to_date(start, days) == expected


def test_add_days_to_date_rejects_bad_format():
    with pytest.raises(ValueError):
        tools.add_days_to_date("03/10/2026", 7)


# --- get_compute_instance_stats ---------------------------------------------


def _series(instance_name, values):
    """Fake a Cloud Monitoring TimeSeries with the fields the tool reads."""
    return SimpleNamespace(
        metric=SimpleNamespace(labels={"instance_name": instance_name}),
        points=[SimpleNamespace(value=SimpleNamespace(double_value=v)) for v in values],
    )


def _metric_from_filter(filter_str):
    for metric in (
        "cpu/utilization",
        "network/received_bytes_count",
        "network/sent_bytes_count",
    ):
        if metric in filter_str:
            return metric
    raise AssertionError(f"unexpected filter: {filter_str}")


@patch("janitor.tools.monitoring_v3.MetricServiceClient")
def test_instance_stats_parses_ids_and_averages_points(mock_client_cls):
    fake = {
        ("vm-a", "cpu/utilization"): [0.01, 0.03],
        ("vm-a", "network/received_bytes_count"): [100.0, 300.0],
        ("vm-a", "network/sent_bytes_count"): [10.0],
        ("vm-b", "cpu/utilization"): [0.5],
    }
    requests = []

    def list_time_series(request):
        requests.append(request)
        name = request.filter.split('instance_name="')[1].split('"')[0]
        values = fake.get((name, _metric_from_filter(request.filter)))
        return [_series(name, values)] if values else []

    mock_client_cls.return_value = MagicMock(list_time_series=list_time_series)

    stats = tools.get_compute_instance_stats(
        ["proj-1/us-central1-a/vm-a", "proj-2/europe-west1-b/vm-b"]
    )

    by_name = {s["name"]: s for s in stats}
    assert by_name["vm-a"] == {
        "name": "vm-a",
        "cpu_utilization": pytest.approx(0.02),
        "received_bytes": pytest.approx(200.0),
        "sent_bytes": pytest.approx(10.0),
    }
    # Metrics with no data default to 0.
    assert by_name["vm-b"] == {
        "name": "vm-b",
        "cpu_utilization": pytest.approx(0.5),
        "received_bytes": 0,
        "sent_bytes": 0,
    }

    # Three metric queries per instance, scoped to the right project and zone.
    assert len(requests) == 6
    vm_b_requests = [r for r in requests if 'instance_name="vm-b"' in r.filter]
    assert all(r.name == "projects/proj-2" for r in vm_b_requests)
    assert all('resource.labels.zone="europe-west1-b"' in r.filter for r in vm_b_requests)


@patch("janitor.tools.monitoring_v3.MetricServiceClient")
def test_instance_stats_omits_vms_without_metrics(mock_client_cls):
    mock_client_cls.return_value = MagicMock(list_time_series=lambda request: [])
    assert tools.get_compute_instance_stats(["p/z/silent-vm"]) == []


def test_instance_stats_rejects_malformed_id():
    with patch("janitor.tools.monitoring_v3.MetricServiceClient"):
        with pytest.raises(ValueError):
            tools.get_compute_instance_stats(["missing-zone"])
