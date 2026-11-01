from typing import Literal

from pydantic import BaseModel, Field

Section = Literal["S", "O", "A", "P"]


class Turn(BaseModel):
    id: int
    speaker: str  # e.g. "Doctor" or "Patient"
    text: str


class Support(BaseModel):
    turn_id: int
    quote: str = Field(description="Short excerpt copied exactly from the cited turn")


# What the LLM is allowed to produce. It cannot set validation flags.
class RawSentence(BaseModel):
    text: str
    section: Section
    support: list[Support] = Field(default_factory=list)


class RawNote(BaseModel):
    sentences: list[RawSentence]


# What the pipeline returns after validation.
class NoteSentence(RawSentence):
    flagged: bool = False
    flag_reasons: list[str] = Field(default_factory=list)
    hard_flags: list[str] = Field(default_factory=list)
    soft_flags: list[str] = Field(default_factory=list)


class SOAPNote(BaseModel):
    sentences: list[NoteSentence]
