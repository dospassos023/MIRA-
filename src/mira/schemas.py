from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

Unit = Annotated[float, Field(ge=0, le=1)]
Key = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_.-]{0,79}$")]
Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=256)]
Value = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PersonalityParameters(Schema):
    academic_collaboration: Unit
    initiative: Unit
    artistic_expression: Unit
    humor: Unit
    emotional_attunement: Unit
    strategic_awareness: Unit
    contextual_adaptation: Unit
    independent_judgment: Unit
    spontaneity: Unit


class Personality(Schema):
    version: Short
    parameters: PersonalityParameters
    guidance: list[Short]


class Persona(Schema):
    version: Short
    fictional_age: int = Field(ge=18, le=100)
    identity: Short
    principles: list[Short] = Field(min_length=1, max_length=30)


class Context(Schema):
    urgency: Unit | None = None
    deadline_hours: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None
    workload: Unit | None = None
    available_resources: list[Short] | None = Field(default=None, max_length=30)
    reported_fatigue: Unit | None = None
    risk: Unit | None = None
    reversible: bool | None = None
    strategic_relevance: Unit | None = None
    preferred_style: Literal["concise", "standard", "detailed"] | None = None


class Action(StrEnum):
    ANALYZE = "analyze"
    RESEARCH = "research"
    PLAN = "plan"
    COMPARE = "compare"
    RECOMMEND = "recommend"
    DRAFT = "draft"
    CALCULATE = "calculate"
    SEND = "send"
    PURCHASE = "purchase"
    MODIFY_RECORD = "modify_record"
    DELETE_RECORD = "delete_record"
    PUBLISH = "publish"
    CHANGE_PERMISSIONS = "change_permissions"
    EXTERNAL = "external"
    OTHER = "other"


class Operation(Schema):
    id: Short
    action: Action
    target: Short


class Approval(Schema):
    operation: Operation
    expires_at: AwareDatetime


class Evidence(Schema):
    kind: Literal["user_statement", "observed_pattern", "profile_import"]
    reference: Short


class MemoryInput(Schema):
    key: Key
    value: Value
    kind: Literal["explicit", "hypothesis"]
    evidence: list[Evidence] = Field(min_length=1, max_length=30)
    confidence: Unit
    sensitive: bool = False
    valid_from: AwareDatetime | None = None
    valid_until: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_evidence(self):
        if self.kind == "explicit" and not any(
            entry.kind == "user_statement" for entry in self.evidence
        ):
            raise ValueError("Explicit entries require a user statement")
        if self.valid_from and self.valid_until and self.valid_until <= self.valid_from:
            raise ValueError("valid_until must follow valid_from")
        return self


class Observation(Schema):
    key: Key
    value: Value
    reference: Short


class ProfileImport(Schema):
    schema_version: Literal[1]
    profile_version: Short
    consent_reference: Short
    entries: list[MemoryInput] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_keys(self):
        if len({entry.key for entry in self.entries}) != len(self.entries):
            raise ValueError("Profile entries must have distinct keys")
        return self


class Review(Schema):
    version: int = Field(ge=1)
    evidence_reference: Short
    corrected_value: Value | None = None
