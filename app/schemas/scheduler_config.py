from pydantic import BaseModel


class SchedulerConfigOut(BaseModel):
    key: str
    value: int
    label: str
    description: str | None

    class Config:
        from_attributes = True


class SchedulerConfigUpdateItem(BaseModel):
    key: str
    value: int


class SchedulerConfigBatchUpdate(BaseModel):
    configs: list[SchedulerConfigUpdateItem]
