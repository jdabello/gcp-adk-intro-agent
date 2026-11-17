from pydantic import BaseModel, Field


class VMInstance(BaseModel):
    project_id: str = Field(description="The project ID of the VM.")
    name: str = Field(description="The name of the VM.")
    zone: str = Field(description="The zone where the VM is located.")
    status: str = Field(description="The status of the VM (TERMINATED, RUNNING, etc)")
    machine_type: str = Field(description="The type of machine (e.g. n1-standard-1)")


class VMInstanceList(BaseModel):
    vm_instances: list[VMInstance] = Field(description="The list of VM instances.")


class VMStats(VMInstance):
    cpu_utilization: float = Field(
        description="The average CPU usage of the VM instance, 1 is 100%."
    )
    received_bytes: float = Field(
        description="The average number of bytes received by the VM instance."
    )
    sent_bytes: float = Field(
        description="The average number of bytes sent by the VM instance."
    )
    idle_probability: float | None = Field(
        default=None,
        description="Calibrated probability (0-1) from the Gemini Decisions API that the VM is idle.",
    )
    idle_confidence: float | None = Field(
        default=None,
        description="Decisions API confidence (0-1) in the idle verdict.",
    )
    cleanup_risk: float | None = Field(
        default=None,
        description="Decisions API risk score for stopping the VM: 0=Low, 1=Medium, 2=High.",
    )


class VMStatsList(BaseModel):
    vm_stats: list[VMStats] = Field(description="The list of VM stats.")
