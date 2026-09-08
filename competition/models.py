"""Strict, metre/kg contracts. Unknown fields and nonfinite numbers are rejected."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field

Positive = Annotated[float, Field(gt=0, le=100000, allow_inf_nan=False)]
Coordinate = Annotated[float, Field(ge=-100, le=100, allow_inf_nan=False)]
Identifier = Annotated[str, Field(min_length=1, max_length=120, pattern=r'^[A-Za-z0-9_.:-]+$')]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, str_strip_whitespace=True)


class Dimensions(StrictModel):
    width: Positive
    depth: Positive
    height: Positive


class Position(StrictModel):
    x: Coordinate
    y: Coordinate
    z: Coordinate


class Placement(StrictModel):
    id: Identifier
    sku_id: Identifier
    position: Position
    rotation: Literal[0, 90] = 0


class Pack(StrictModel):
    order_id: Identifier
    boxes: list[Placement] = Field(max_length=1000)


class StrategyCreate(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default='', max_length=3000)


class RevisionCreate(StrictModel):
    benchmark_id: Identifier
    parent_id: Identifier | None = None
    notes: str = Field(min_length=1, max_length=4000)
    code_revision: str = Field(min_length=1, max_length=200)
    model_revision: str = Field(default='not-applicable', max_length=200)
    config: dict = Field(default_factory=dict)


class Batch(StrictModel):
    packs: list[Pack] = Field(min_length=1, max_length=25)


class EmailRequest(StrictModel):
    email: str = Field(min_length=3, max_length=254)


class TokenRequest(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    scopes: list[Literal['submit', 'publish']] = Field(default_factory=lambda: ['submit'])
    days: int = Field(default=30, ge=1, le=90)
