from pydantic import BaseModel, ConfigDict, Field


class PricedLineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: str
    sku_id: str
    component: str
    unit_price: float
    unit: str
    qty: float
    usage_hours: float
    monthly_cost: float


class UnpricedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: str
    reason: str


class Estimate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    currency: str = "USD"
    pricing_snapshot: str
    disclaimer: str = "List price only. SUD/CUD/negotiated discounts NOT applied."
    line_items: list[PricedLineItem]
    monthly_total: float
    unpriced: list[UnpricedItem] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
