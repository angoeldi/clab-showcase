from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class Confidence(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class Hypothesis(BaseModel):
    text: str = Field(..., min_length=1, description="Non-factive inference; must be labelled as hypothesis.")
    confidence: Confidence = Field(..., description="Subjective confidence, not probability.")
    ask_confirmation: bool = Field(True, description="Whether the bot should ask the user to confirm/deny.")
    confirmed: Optional[bool] = Field(None, description="If user has confirmed or denied previously.")


class AnalysisSignals(BaseModel):
    goal_clarity: int = Field(0, ge=0, le=5)
    motivation: int = Field(0, ge=0, le=5)
    risk: int = Field(0, ge=0, le=5)


class AnalysisResult(BaseModel):
    stage: str = Field(..., description="Current domain stage (id from domain.yaml if possible).")
    user_intent: str = Field(..., description="Short intent label, e.g., 'set_goal', 'ask_for_help', 'resist', 'reflect'.")
    goal: Optional[str] = Field(None, description="User goal if stated or confidently inferred (ask to confirm if inferred).")
    constraints: List[str] = Field(default_factory=list, description="Constraints explicitly stated by the user.")
    facts: List[str] = Field(default_factory=list, description="Factual statements attributed to the user.")
    hypotheses: List[Hypothesis] = Field(default_factory=list, description="Non-factive reasoning; must be labelled.")
    open_questions: List[str] = Field(default_factory=list, description="Missing info; phrased as questions.")
    signals: AnalysisSignals = Field(default_factory=AnalysisSignals)
    risk_flags: List[str] = Field(default_factory=list, description="Matched red-flag ids from domain safety policy.")
    safety_mode: Optional[str] = Field(None, description="If set, composer must follow safety policy.")


class ActionPlan(BaseModel):
    action: str = Field(..., description="Intervention id, e.g., PROBE, REFLECT, INSTRUCT, REDIRECT, SUMMARISE, SAFETY.")
    rationale: str = Field(..., description="Why this action is selected, grounded in domain theory and analysis.")
    params: Dict[str, Any] = Field(default_factory=dict, description="Action parameters. Must be JSON-serializable.")


class BotMemory(BaseModel):
    goal: Optional[str] = None
    stage: Optional[str] = None
    constraints: List[str] = Field(default_factory=list)
    commitments: List[str] = Field(default_factory=list)
    facts: List[str] = Field(default_factory=list)
    hypotheses: List[Hypothesis] = Field(default_factory=list)
    signals: AnalysisSignals = Field(default_factory=AnalysisSignals)
    open_questions: List[str] = Field(default_factory=list)
    next_step: Optional[str] = None
    last_updated_utc: str = Field(..., description="ISO timestamp.")


class StatusState(BaseModel):
    user_card_md: str = Field(..., description="Short status card appended to user-visible message.")
    bot_memory: BotMemory = Field(..., description="Machine-readable memory object for next turn.")
