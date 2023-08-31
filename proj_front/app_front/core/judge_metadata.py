import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConstrainedStr

from app_front.core.common.regex_helper import to_compiled_fullmatch_regex
from app_front.core.types import PATTERN_StringUrl64
from extension.pydantic_strict import StrictBaseModel


class ExerciseName(ConstrainedStr):
    max_length = 64
    regex = to_compiled_fullmatch_regex(PATTERN_StringUrl64)


class ExerciseTitle(ConstrainedStr):
    max_length = 64


class ExerciseVersion(ConstrainedStr):
    max_length = 64


class PlagsJudgeMasterNotebookMetadataDeadlines(BaseModel):
    begin: Optional[datetime.datetime] = None
    open: Optional[datetime.datetime] = None
    check: Optional[datetime.datetime] = None
    close: Optional[datetime.datetime] = None
    end: Optional[datetime.datetime] = None


class PlagsJudgeMasterNotebookMetadataTrialEditor(BaseModel):
    name: str
    options: Optional[Dict[str, Any]]


class PlagsJudgeMasterNotebookMetadataTrial(BaseModel):
    initial_source: str
    editor: PlagsJudgeMasterNotebookMetadataTrialEditor


class PlagsJudgeMasterNotebookMetadataConfidentiality(BaseModel):
    score: Optional[Literal["student", "assistant", "lecturer"]] = None
    remarks: Optional[Literal["assistant", "lecturer"]] = None


class PlagsJudgeMasterNotebookMetadata(StrictBaseModel):
    type: Literal["master"]
    name: ExerciseName
    title: ExerciseTitle
    version: ExerciseVersion
    evaluation: bool
    confidentiality: PlagsJudgeMasterNotebookMetadataConfidentiality
    deadlines: PlagsJudgeMasterNotebookMetadataDeadlines
    drive: Optional[str]
    shared_after_confirmed: Optional[bool]
    trial: Optional[PlagsJudgeMasterNotebookMetadataTrial] = None


class PlagsJudgeSubmissionNotebookMetadata(StrictBaseModel):
    type: Literal["submission"]
    exercises: Dict[ExerciseName, Optional[ExerciseVersion]]
    extraction: bool

