from google.adk import Agent
from google.adk.agents import SequentialAgent
from google.adk.agents.remote_a2a_agent import (
    AGENT_CARD_WELL_KNOWN_PATH,
    RemoteA2aAgent,
)
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
      3. Merge each VM from `resources` with its stats (match on `name`) into
         one dict with `project_id`, `name`, `zone`, `status`,
         `machine_type`, `cpu_utilization`, `received_bytes` and
         `sent_bytes`. A VM with no stats gets 0 for the three metrics.
         Call `decide_idle_vms` ONCE with the full merged list. It uses the
         Gemini Decisions API to return only the idle VMs, each annotated with
         `idle_probability`, `idle_confidence` and `cleanup_risk`. Do NOT
         filter or second-guess its result yourself.
      4. Emit a JSON object of the shape `{"vm_stats": <list returned by
         decide_idle_vms>}` matching the `VMStatsList` schema, keeping every
         field it returned.

    Hard rules:
      - NEVER reply conversationally. No prose, no apologies, no markdown
        fences. JSON only.
      - NEVER ask the user to confirm anything.
    """,
    tools=[
        tools.get_compute_instance_stats,
        tools.decide_idle_vms,
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

resource_cleaner_agent = RemoteA2aAgent(
    name="resource_cleaner_agent",
    description="Stops idle VMs whose `janitor-scheduled` label has been set.",
    agent_card=(
        f"{settings.A2A_SERVER_URL.rstrip('/')}"
        f"/a2a/resource_cleaner_agent{AGENT_CARD_WELL_KNOWN_PATH}"
    ),
)

orchestrator_agent = SequentialAgent(
    name="orchestrator_agent",
    sub_agents=[
        resource_scanner_agent,
        resource_monitor_agent,
        resource_labeler_agent,
        resource_cleaner_agent,
    ],
)

# The root_agent is the entry point for the user query.
root_agent = orchestrator_agent
