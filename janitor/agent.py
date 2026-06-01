from google.adk import Agent

import janitor.schemas as schemas
import janitor.settings as settings
import janitor.tools as tools


resource_scanner_agent = Agent(
    name="resource_scanner_agent",
    model=settings.GEMINI_MODEL,
    instruction="""
    You are a Cloud Resource Scanner.
    Call `get_compute_instances_list` to fetch every VM in the project, then
    return the result as a JSON object matching the `VMInstanceList` schema
    (a single key `vm_instances` whose value is the list of VMs).
    """,
    tools=[
        tools.get_compute_instances_list,
        tools.get_compute_instance_stats,
        tools.get_current_date,
        tools.add_days_to_date,
    ],
    output_schema=schemas.VMInstanceList,
    output_key="resources",
)

resource_monitor_agent = Agent(
    name="resource_monitor_agent",
    model=settings.GEMINI_MODEL,
    instruction="""
    You are a Cloud Resource Monitor. The Cloud Resource Scanner has stored
    the project's VM inventory in session state under the key `resources`
    (a `VMInstanceList`).

    Resources to evaluate:
    {resources}

    Steps:
    1. Build a list of instance identifiers in the form `project_id/zone/name`
       from the `vm_instances` in `resources`.
    2. Call `get_compute_instance_stats` with that list to get per-VM CPU and
       network metrics.
    3. Decide which VMs are *idle*. Treat a VM as idle when its
       `cpu_utilization` is below 0.05 (5%) AND both `received_bytes` and
       `sent_bytes` are near zero. Also treat any VM in status `TERMINATED`
       as idle.
    4. Return ONLY the idle VMs as a JSON object matching the `VMStatsList`
       schema (a single key `vm_stats` whose value is the filtered list,
       each item including the stats fields).
    """,
    tools=[
        tools.get_compute_instance_stats,
    ],
    output_schema=schemas.VMStatsList,
    output_key="idle_resources",
)

# The root_agent is the entry point for the user query.
root_agent = resource_scanner_agent
