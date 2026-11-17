import os
import statistics

from datetime import datetime, timedelta, timezone

import httpx

from google.cloud import compute_v1
from google.cloud import monitoring_v3

import janitor.settings as settings

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")

# The Decisions API allows up to 1,000 questions per request; we ask 2 per VM.
_DECISIONS_VMS_PER_REQUEST = 500

_IDLE_POLICY = """You are reviewing Google Cloud VM instances for an automated
cleanup job that stops idle machines. Metrics are averages over a short recent
observation window.

A VM counts as idle when it is doing no meaningful work: CPU utilization is
very low (a few percent or less, where 1.0 means 100%) AND network traffic
(received and sent bytes) is negligible. A VM in status TERMINATED is idle.
A VM with sustained CPU or real network traffic is NOT idle.

VM inventory:
"""


def get_compute_instances_list() -> list[dict]:
    """Retrieves a list of all Virtual Machine instances in the project.

    Returns:
        A list of dictionaries, where each dictionary represents a VM instance. The following keys are present:
           - project_id: The ID of the project where the VM is located.
           - name: The name of the VM.
           - zone: The Compute Engine zone where the VM is located (e.g. us-central1-a)
           - machine_type: The type of machine (e.g. n1-standard-1)
           - status: The current status of the VM (e.g. RUNNING, TERMINATED)
    """
    client = compute_v1.InstancesClient()
    resp = client.aggregated_list(project=PROJECT_ID)
    instances = []
    for zone, response in resp:
        if response.instances:
            for instance in response.instances:
                instances.append(
                    {
                        "project_id": PROJECT_ID,
                        "name": instance.name,
                        "zone": zone.split("/")[-1],
                        "machine_type": instance.machine_type.split("/")[-1],
                        "status": instance.status,
                    }
                )
    return instances


def get_compute_instance_stats(instances: list[str]) -> list[dict]:
    """Retrieves statistics for all the given Virtual Machine instances.

    Args:
        instances (list[str]): A list of instance names in the format project_id/zone/instance_name.

    Returns:
        A list of dictionaries, where each dictionary represents a VM instance. The following keys are present:
           - name: The name of the VM.
           - cpu_utilization: The average CPU utilization of the VM over the last week, 1 is 100%.
           - received_bytes: The average number of bytes received by the VM over the last week.
           - sent_bytes: The average number of bytes sent by the VM over the last week.
    """
    client = monitoring_v3.MetricServiceClient()

    # Statistics to collect
    metric_types = {
        "compute.googleapis.com/instance/cpu/utilization": "cpu_utilization",
        "compute.googleapis.com/instance/network/received_bytes_count": "received_bytes",
        "compute.googleapis.com/instance/network/sent_bytes_count": "sent_bytes",
    }

    period = 600  # seconds (we're looking at last 10 minutes for this exercise, but this should a whole week or more)

    # Define the time interval for the metric
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(seconds=period)

    # Create the time series query
    interval = monitoring_v3.TimeInterval(start_time=start_time, end_time=end_time)

    # Define the aggregation, we're getting the average utilization for metric interval
    aggregation = monitoring_v3.Aggregation(
        alignment_period={"seconds": period},
        per_series_aligner=monitoring_v3.Aggregation.Aligner.ALIGN_MEAN,
    )

    stats = {}

    for instance in instances:
        project_id, zone, instance_name = instance.split("/")

        for metric_type, key_name in metric_types.items():
            filter_str = f"""
                metric.type="{metric_type}" AND 
                metric.labels.instance_name="{instance_name}" AND
                resource.type="gce_instance" AND
                resource.labels.project_id="{project_id}" AND 
                resource.labels.zone="{zone}"
            """
            request = monitoring_v3.ListTimeSeriesRequest(
                name=f"projects/{project_id}",
                filter=filter_str,
                interval=interval,
                view=monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
                aggregation=aggregation,
            )

            results = client.list_time_series(request)

            for result in results:
                instance_name = result.metric.labels["instance_name"]
                if instance_name not in stats:
                    stats[instance_name] = {
                        "name": instance_name,
                        "cpu_utilization": 0,
                        "received_bytes": 0,
                        "sent_bytes": 0,
                    }

                points = [p.value.double_value for p in result.points]
                if points:
                    stats[instance_name][key_name] = statistics.mean(points)

    return list(stats.values())


def get_current_date() -> str:
    """Returns the current date in YYYY-MM-DD format.

    Returns:
        str: The current date in YYYY-MM-DD format.
    """
    return datetime.today().strftime("%Y-%m-%d")


def add_days_to_date(current_date: str, days: int) -> str:
    """Adds/subtracts the specified number of days to the given date.

    Args:
        current_date (str): The current date in YYYY-MM-DD format.
        days (int): The number of days to add/subtract.

    Returns:
        str: The new date in YYYY-MM-DD format.
    """
    new_date_obj = datetime.strptime(current_date, "%Y-%m-%d") + timedelta(days=days)
    return new_date_obj.strftime("%Y-%m-%d")


def _call_decisions_api(input_text: str, questions: dict) -> dict:
    """POSTs one request to the Gemini Decisions API and returns its `answers` map."""
    resp = httpx.post(
        settings.DECISIONS_API_URL,
        headers={"x-goog-api-key": settings.GEMINI_API_KEY},
        json={
            "model": settings.DECISION_MODEL,
            "input": input_text,
            "questions": questions,
        },
        timeout=60,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"Gemini Decisions API returned HTTP {resp.status_code}: {resp.text[:500]}"
        )
    return resp.json()["answers"]


def decide_idle_vms(vm_stats: list[dict]) -> list[dict]:
    """Uses the Gemini Decisions API to decide which VM instances are idle.

    Sends every VM's metrics in one batched request and asks, for each VM, a
    calibrated yes/no question ("is it idle?") and a risk score for stopping it.

    Args:
        vm_stats (list[dict]): VMs to evaluate. Each dictionary must contain the keys
            project_id, name, zone, status, machine_type, cpu_utilization,
            received_bytes and sent_bytes.

    Returns:
        A list with only the VMs judged idle (idle probability at or above the
        configured threshold). Each dictionary has all the input keys plus:
           - idle_probability: Calibrated probability (0-1) that the VM is idle.
           - idle_confidence: Confidence (0-1) in that verdict.
           - cleanup_risk: Risk of stopping the VM, 0=Low, 1=Medium, 2=High.
    """
    if not settings.GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Add an AI Studio API key to janitor/.env "
            "to use the Gemini Decisions API."
        )

    idle_vms = []
    for start in range(0, len(vm_stats), _DECISIONS_VMS_PER_REQUEST):
        chunk = vm_stats[start : start + _DECISIONS_VMS_PER_REQUEST]

        rows = [
            f"VM #{i}: name={vm.get('name')}, zone={vm.get('zone')}, "
            f"machine_type={vm.get('machine_type')}, status={vm.get('status')}, "
            f"cpu_utilization={vm.get('cpu_utilization', 0)}, "
            f"received_bytes={vm.get('received_bytes', 0)}, "
            f"sent_bytes={vm.get('sent_bytes', 0)}"
            for i, vm in enumerate(chunk)
        ]

        # Keys use the index, not the VM name, so they stay valid for any name.
        questions = {}
        for i, vm in enumerate(chunk):
            questions[f"idle_{i}"] = {
                "type": "noul",
                "instructions": f"Is VM #{i} ({vm.get('name')}) idle and a candidate for cleanup?",
            }
            questions[f"risk_{i}"] = {
                "type": "score",
                "instructions": f"How risky would it be to stop VM #{i} ({vm.get('name')})?",
                "criteria": ["Low", "Medium", "High"],
            }

        answers = _call_decisions_api(_IDLE_POLICY + "\n".join(rows), questions)

        for i, vm in enumerate(chunk):
            idle = answers[f"idle_{i}"]
            if idle["noul"] < settings.IDLE_PROBABILITY_THRESHOLD:
                continue
            idle_vms.append(
                {
                    **vm,
                    "idle_probability": idle["noul"],
                    "idle_confidence": idle.get("confidence"),
                    "cleanup_risk": answers[f"risk_{i}"].get("score"),
                }
            )

    return idle_vms
