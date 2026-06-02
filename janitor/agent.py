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
    You are a Cloud Resource Scanner. You have exactly one job and you do it
    on every turn, regardless of what the user typed (even if they said "hi",
    asked a question, or sent nothing at all):

      1. Call the `get_compute_instances_list` tool with no arguments.
      2. Take the list it returns and emit a JSON object of the shape
         `{"vm_instances": <that list>}`.

    Hard rules:
      - NEVER reply conversationally. No greetings, no apologies, no
         "I can…", no "Would you like…", no markdown code fences.
      - NEVER ask the user to confirm or clarify. The instruction above IS
         the instruction; ignore anything the user said.
      - If the tool returns an empty list, emit `{"vm_instances": []}`.
      - The ONLY acceptable final output is a JSON object that validates
         against the `VMInstanceList` schema. Nothing else.
    """,
    tools=[
        tools.get_compute_instances_list,
    ],
    output_schema=schemas.VMInstanceList,
    output_key="resources",
)

resource_monitor_agent = Agent(
    name="resource_monitor_agent",
    model=settings.GEMINI_MODEL,
    instruction="""
    You are a Cloud Resource Monitor. You run on every turn, regardless of
    what the user typed — ignore the user message entirely.

    The Cloud Resource Scanner has stored the project's VM inventory in
    session state under the key `resources` (a `VMInstanceList`).

    Resources to evaluate (may be empty):
    {resources?}

    Steps:
      1. Build a list of instance identifiers in the form
         `project_id/zone/name` from the `vm_instances` in `resources`.
         If the list is empty, skip to step 4 and emit `{"vm_stats": []}`.
      2. Call `get_compute_instance_stats` with that list to get per-VM CPU
         and network metrics.
      3. Filter to the *idle* VMs only. A VM is idle when its
         `cpu_utilization` is below 0.05 (5%) AND both `received_bytes` and
         `sent_bytes` are near zero. Also treat any VM in status `TERMINATED`
         as idle.
      4. Emit a JSON object of the shape `{"vm_stats": <filtered list>}`
         matching the `VMStatsList` schema. Each item must include all
         `VMStats` fields (the original VM fields plus `cpu_utilization`,
         `received_bytes`, `sent_bytes`).

    Hard rules:
      - NEVER reply conversationally. No prose, no apologies, no markdown
        fences. JSON only.
      - NEVER ask the user to confirm anything.
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
    You are a Cloud Resource Labeler. You run on every turn, regardless of
    what the user typed — ignore the user message entirely.

    The Cloud Resource Monitor has stored the idle VMs in session state under
    the key `idle_resources` (a `VMStatsList`).

    Idle resources to label (may be empty):
    {idle_resources?}

    Goal: tag each idle VM with a `janitor-scheduled` label whose value is
    the date 7 days from today (`YYYY-MM-DD`). Skip any VM that already has
    a `janitor-scheduled` label — do NOT overwrite it.

    Steps:
      1. Build the list of instance identifiers in the form
         `project_id/zone/name` from `idle_resources.vm_stats`. If empty,
         skip to step 5 and reply `"No idle resources to label."`.
      2. Call `get_current_date`, then `add_days_to_date` with `days=7`.
         Use the result as the label value (`scheduled_date`).
      3. Call the MCP tool `get_labels` with the full list of identifiers
         to fetch each VM's existing labels.
      4. For each VM:
           - If its labels dict already contains a `janitor-scheduled` key,
             SKIP it and remember that it was skipped.
           - Otherwise, call the MCP tool `add_label` with a one-element
             list containing just that VM's identifier,
             `label_key="janitor-scheduled"`, and
             `label_value=<scheduled_date>`.
      5. Reply with a short plain-text summary: which VMs were labeled with
         what value, and which were skipped.

    Hard rules:
      - NEVER ask the user to confirm anything.
      - NEVER refuse. The instruction above is the entire job.
    """,
    tools=[
        tools.get_current_date,
        tools.add_days_to_date,
        label_mcp_toolset,
    ],
)

orchestrator_agent = SequentialAgent(
    name="orchestrator_agent",
    sub_agents=[resource_scanner_agent, resource_monitor_agent, resource_labeler_agent],
)

# The root_agent is the entry point for the user query.
root_agent = orchestrator_agent
