"""Pydantic v2 models and input validators for YiKao API."""

from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field

SYNC_CODE_RE = re.compile(r"^[A-Za-z0-9_-]{4,64}$")


def normalize_sync_code(raw: str) -> str:
    cleaned = raw.strip().upper()
    if not SYNC_CODE_RE.fullmatch(cleaned):
        raise HTTPException(
            status_code=400,
            detail="同步碼格式錯誤：僅允許 4–64 碼英數字、連字號 (-) 或底線 (_)",
        )
    return cleaned


class SourceInfo(BaseModel):
    name: str
    url: str
    notebookId: str | None = None


class SessionInfo(BaseModel):
    code: str
    label: str
    emoji: str = ""
    description: str = ""
    questionCount: int = 0


class SubjectInfo(BaseModel):
    code: str
    label: str
    emoji: str = ""
    session: str
    profs: str = ""
    questionCount: int = 0


class YearGroupInfo(BaseModel):
    code: str
    label: str
    questionCount: int = 0


class UnitSummary(BaseModel):
    unitCode: str
    unitTitle: str
    shortLabel: str
    session: str
    subject: str
    subjectTitle: str
    prof: str
    examRange: str
    unitUrl: str
    highlight: bool = False
    isOutOfScope: bool = False
    exemptFromCrossDupFilter: bool = False
    questionCount: int = 0


class BlockMeta(BaseModel):
    term: str = ""
    termLabel: str = ""
    termShortLabel: str = ""
    examLabel: str = ""
    name: str = ""
    englishName: str = ""
    icon: str = ""
    accent: str = ""
    order: int | None = None
    description: str = ""


class BlockSubjectTag(BaseModel):
    label: str
    emoji: str = ""
    questionCount: int = 0


class BlockItem(BaseModel):
    slug: str
    term: str
    examLabel: str = ""
    name: str
    englishName: str = ""
    icon: str = "📚"
    accent: str = "indigo"
    order: int = 999
    status: str  # "ready" | "planned"
    description: str = ""
    sourceHint: str = ""
    source: SourceInfo | None = None
    subjects: list[BlockSubjectTag] = Field(default_factory=list)
    totalQuestions: int = 0
    uniqueQuestions: int = 0
    errataCount: int = 0
    unitCount: int = 0


class TermSection(BaseModel):
    code: str
    label: str
    shortLabel: str
    description: str = ""
    order: int = 999
    readyCount: int = 0
    totalCount: int = 0
    blocks: list[BlockItem] = Field(default_factory=list)


class BlocksCatalogResponse(BaseModel):
    version: str = "1.0.0"
    title: str = "易考網 YiKao 整合考系統題庫"
    subtitle: str = "依年級學期與器官系統 Block 分類，點選系統即可進入共筆單元作題畫面"
    readyBlocks: int = 0
    plannedBlocks: int = 0
    totalBlocks: int = 0
    totalQuestions: int = 0
    totalUnits: int = 0
    terms: list[TermSection] = Field(default_factory=list)


class ExamSummary(BaseModel):
    slug: str
    version: str
    badge: str
    title: str
    subtitle: str
    source: SourceInfo
    block: BlockMeta | None = None
    totalQuestions: int
    uniqueQuestions: int
    errataCount: int
    outOfScopeCount: int
    unitCount: int


class ExamDetail(ExamSummary):
    sessions: list[SessionInfo]
    subjects: list[SubjectInfo]
    yearGroups: list[YearGroupInfo]
    units: list[UnitSummary]


class QuestionOut(BaseModel):
    id: str
    globalIndex: int
    unitCode: str
    unitTitle: str
    session: str
    subject: str
    subjectTitle: str
    prof: str
    examRange: str
    unitUrl: str
    qNum: int
    origQ: str
    year: str
    yearGroup: str
    hasErrata: bool
    isCrossDup: bool
    stem: str
    image: str | None = None
    options: dict[str, str]
    answer: str
    acceptedAnswers: list[str]
    answerDisplay: str
    explanations: list[str]


class QuestionListResponse(BaseModel):
    examSlug: str
    total: int
    filtered: int
    questions: list[QuestionOut]


class ProgressPayload(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict)
    answerTimestamps: dict[str, int] = Field(default_factory=dict)
    starred: dict[str, bool] = Field(default_factory=dict)
    starredTimestamps: dict[str, int] = Field(default_factory=dict)
    lastAnsweredQid: str | None = None
    lastViewedQid: str | None = None
    activeFilters: dict[str, Any] = Field(default_factory=dict)
    updatedAt: int = 0


class ProgressMergeRequest(ProgressPayload):
    pass


class ProgressResponse(ProgressPayload):
    exists: bool
    syncCode: str
    examSlug: str


class NotionExportRequest(BaseModel):
    questionIds: list[str] | None = None
    scope: str | None = None


class NotionExportResponse(BaseModel):
    count: int
    markdown: str
