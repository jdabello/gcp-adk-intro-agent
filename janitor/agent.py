from google.adk import Agent
from google.adk.agents import SequentialAgent
from google.adk.tools.mcp_tool import MCPToolset, StreamableHTTPConnectionParams

import janitor.schemas as schemas
import janitor.settings as settings
import janitor.tools as tools

label_mcp_toolset = MCPToolset(
    connection_params=StreamableHTTPConnectionParams(
        url=settings.MCP_SERVER_URL,
    ),
)


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

resource_labeler_agent = Agent(
    name="resource_labeler_agent",
    model=settings.GEMINI_MODEL,
    instruction="""
    You are a Cloud Resource Labeler. The Cloud Resource Monitor has stored
    the idle VMs in session state under the key `idle_resources` (a
    `VMStatsList`).

    Idle resources to label:
    {idle_resources}

    Goal: tag each idle VM with a `janitor-scheduled` label whose value is the
    date 7 days from today (format `YYYY-MM-DD`). Skip any VM that already has
    a `janitor-scheduled` label — do NOT overwrite it.

    Steps:
    1. Build the list of instance identifiers in the form
       `project_id/zone/name` from `idle_resources.vm_stats`.
    2. Call `get_current_date`, then `add_days_to_date` with `days=7`. Use the
       result as the label value (call this `scheduled_date`).
    3. Call the MCP tool `get_labels` with the full list of identifiers to
       fetch each VM's existing labels.
    4. For each VM:
         - If its labels dict already contains a `janitor-scheduled` key,
           SKIP it and note that it was skipped.
         - Otherwise, call the MCP tool `add_label` with just that single VM's
           identifier (as a one-element list), `label_key="janitor-scheduled"`,
           and `label_value=scheduled_date`.
    5. Reply with a short summary: which VMs were labeled with what value,
       and which were skipped (and why).
    """,
    tools=[
        tools.get_current_date,
        tools.add_days_to_date,
        label_mcp_toolset,
    ],
)

orchestrator_agent = SequentialAgent(
    name="orchestrator_agent",
    sub_agents=[resource_scanner_agent, resource_monitor_agent],
)

# The root_agent is the entry point for the user query.
root_agent = orchestrator_agent
