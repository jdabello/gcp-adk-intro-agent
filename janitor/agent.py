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

# The root_agent is the entry point for the user query.
root_agent = resource_scanner_agent
