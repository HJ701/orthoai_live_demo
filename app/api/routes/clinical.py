import csv
import datetime as dt
import io
import os
import sqlite3
from pathlib import Path
from typing import Iterator, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_dependency
from app.database import get_db
from app.models import Case, InferenceJob, InferenceResult, JobState, User


router = APIRouter()

DB_PATH = os.environ.get(
    "ORTHOAI_CLINICAL_DB",
    str(Path(__file__).resolve().parents[3] / "data" / "orthoai_clinical.db"),
)

MClass = Literal[
    "Class I", "Class II div 1", "Class II div 2", "Class III", "Unclassifiable"
]


class ClinicalCaseIn(BaseModel):
    site: str = Field(..., min_length=1, max_length=32, examples=["C-04"])
    case_id: str = Field(..., min_length=1, max_length=64, examples=["C04-0017"])
    assess_date: Optional[dt.date] = None
    clinician: Optional[str] = Field(None, max_length=32, examples=["AH"])
    age: Optional[int] = Field(None, ge=0, le=120)
    sex: Optional[Literal["Female", "Male", "Other", "Undisclosed"]] = None
    rec_opg: bool = False
    rec_photo: bool = False
    rec_other: bool = False

    m_class: MClass
    dhc: int = Field(..., ge=1, le=5, description="IOTN Dental Health Component")
    ac: Optional[int] = Field(None, ge=1, le=10, description="IOTN Aesthetic Component")
    t_manual: Optional[float] = Field(None, ge=0, description="Clinician time (min)")

    ai_class: Optional[MClass] = None
    ai_dhc: Optional[int] = Field(None, ge=1, le=5)
    ai_ac: Optional[int] = Field(None, ge=1, le=10)
    ai_conf: Optional[float] = Field(None, ge=0, le=100, description="AI confidence %")
    t_ai: Optional[float] = Field(None, ge=0, description="AI time-to-assessment (min)")
    calib: Optional[
        Literal["Well-calibrated", "Over-confident", "Under-confident", "N/A"]
    ] = None
    agree: Optional[Literal["Agree", "Partial", "Disagree"]] = None
    override: Optional[Literal["Yes", "No"]] = None
    override_reason: Optional[str] = Field(None, max_length=500)
    useful: Optional[int] = Field(None, ge=1, le=5)
    comment: Optional[str] = Field(None, max_length=4000)


class ClinicalCaseOut(ClinicalCaseIn):
    id: int
    orthoai_case_id: int
    created_at: str
    updated_at: str
    high_need: bool
    class_match: Optional[bool] = None
    dhc_delta: Optional[int] = None


class ClinicalCaseList(BaseModel):
    total: int
    items: list[ClinicalCaseOut]


class ClinicalStats(BaseModel):
    n: int
    sites: int
    high_need: int
    class_pairs: int
    class_agreement_pct: Optional[float] = None
    dhc_pairs: int
    dhc_exact_pct: Optional[float] = None
    mean_dhc_delta: Optional[float] = None
    mean_useful: Optional[float] = None
    override_rate_pct: Optional[float] = None
    mean_t_manual: Optional[float] = None
    mean_t_ai: Optional[float] = None


SCHEMA = """
CREATE TABLE IF NOT EXISTS clinical_cases (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    orthoai_case_id INTEGER NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    site            TEXT NOT NULL,
    case_id         TEXT NOT NULL,
    assess_date     TEXT,
    clinician       TEXT,
    age             INTEGER,
    sex             TEXT,
    rec_opg         INTEGER NOT NULL DEFAULT 0,
    rec_photo       INTEGER NOT NULL DEFAULT 0,
    rec_other       INTEGER NOT NULL DEFAULT 0,
    m_class         TEXT NOT NULL,
    dhc             INTEGER NOT NULL,
    ac              INTEGER,
    t_manual        REAL,
    ai_class        TEXT,
    ai_dhc          INTEGER,
    ai_ac           INTEGER,
    ai_conf         REAL,
    t_ai            REAL,
    calib           TEXT,
    agree           TEXT,
    override        TEXT,
    override_reason TEXT,
    useful          INTEGER,
    comment         TEXT,
    high_need       INTEGER NOT NULL,
    class_match     INTEGER,
    dhc_delta       INTEGER,
    UNIQUE (orthoai_case_id, site, case_id)
);
CREATE INDEX IF NOT EXISTS idx_clinical_cases_orthoai_case_id
    ON clinical_cases (orthoai_case_id);
CREATE INDEX IF NOT EXISTS idx_clinical_cases_site ON clinical_cases (site);
"""

FIELDS = [
    "site", "case_id", "assess_date", "clinician", "age", "sex",
    "rec_opg", "rec_photo", "rec_other",
    "m_class", "dhc", "ac", "t_manual",
    "ai_class", "ai_dhc", "ai_ac", "ai_conf", "t_ai",
    "calib", "agree", "override", "override_reason", "useful", "comment",
    "high_need", "class_match", "dhc_delta",
]
CSV_FIELDS = ["id", "orthoai_case_id", "created_at", "updated_at"] + FIELDS


def init_clinical_db() -> None:
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(SCHEMA)


def get_clinical_db() -> Iterator[sqlite3.Connection]:
    init_clinical_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def require_completed_diagnosis(
    source_case_id: int,
    db: Session,
    current_user: User,
) -> Case:
    case = db.query(Case).filter(
        Case.id == source_case_id,
        Case.user_id == current_user.id,
    ).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source OrthoAI case not found",
        )

    completed_job = db.query(InferenceJob).filter(
        InferenceJob.case_id == source_case_id,
        InferenceJob.state == JobState.DONE,
    ).order_by(InferenceJob.completed_at.desc()).first()
    if not completed_job:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Complete the OrthoAI diagnosis before opening clinical validation",
        )

    result_exists = db.query(InferenceResult).filter(
        InferenceResult.job_id == completed_job.id,
    ).first()
    if not result_exists:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Completed diagnosis results are required before clinical validation",
        )
    return case


def derive(case: ClinicalCaseIn) -> dict:
    d = case.model_dump()
    d["assess_date"] = case.assess_date.isoformat() if case.assess_date else None
    d["rec_opg"] = int(case.rec_opg)
    d["rec_photo"] = int(case.rec_photo)
    d["rec_other"] = int(case.rec_other)
    d["high_need"] = int(case.dhc >= 4)
    d["class_match"] = (
        None if case.ai_class is None else int(case.m_class == case.ai_class)
    )
    d["dhc_delta"] = None if case.ai_dhc is None else abs(case.dhc - case.ai_dhc)
    return d


def row_to_out(row: sqlite3.Row) -> ClinicalCaseOut:
    d = dict(row)
    for b in ("rec_opg", "rec_photo", "rec_other", "high_need"):
        d[b] = bool(d[b])
    d["class_match"] = None if d["class_match"] is None else bool(d["class_match"])
    return ClinicalCaseOut(**d)


def get_row_or_404(case_pk: int, clinical_db: sqlite3.Connection) -> sqlite3.Row:
    row = clinical_db.execute(
        "SELECT * FROM clinical_cases WHERE id = ?", (case_pk,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    return row


@router.get("/health", tags=["clinical"])
def health(
    source_case_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dependency),
) -> dict:
    diagnosis_complete = False
    if source_case_id is not None:
        require_completed_diagnosis(source_case_id, db, current_user)
        diagnosis_complete = True
    return {
        "status": "ok",
        "authenticated": True,
        "diagnosis_required": True,
        "diagnosis_complete": diagnosis_complete,
    }


@router.post("/cases", response_model=ClinicalCaseOut, status_code=status.HTTP_201_CREATED)
def create_case(
    case: ClinicalCaseIn,
    source_case_id: int = Query(..., description="Completed OrthoAI diagnosis case ID"),
    db: Session = Depends(get_db),
    clinical_db: sqlite3.Connection = Depends(get_clinical_db),
    current_user: User = Depends(get_current_user_dependency),
) -> ClinicalCaseOut:
    require_completed_diagnosis(source_case_id, db, current_user)
    d = derive(case)
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    cols = ", ".join(FIELDS)
    ph = ", ".join("?" for _ in FIELDS)
    try:
        cur = clinical_db.execute(
            f"""
            INSERT INTO clinical_cases
                (orthoai_case_id, created_at, updated_at, {cols})
            VALUES (?, ?, ?, {ph})
            """,
            [source_case_id, now, now] + [d[f] for f in FIELDS],
        )
        clinical_db.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Case '{case.case_id}' already exists for site '{case.site}' "
                "on this OrthoAI diagnosis."
            ),
        )
    row = clinical_db.execute(
        "SELECT * FROM clinical_cases WHERE id = ?", (cur.lastrowid,)
    ).fetchone()
    return row_to_out(row)


@router.get("/cases", response_model=ClinicalCaseList)
def list_cases(
    source_case_id: int = Query(..., description="Completed OrthoAI diagnosis case ID"),
    site: Optional[str] = Query(None, description="Filter by site code"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    clinical_db: sqlite3.Connection = Depends(get_clinical_db),
    current_user: User = Depends(get_current_user_dependency),
) -> ClinicalCaseList:
    require_completed_diagnosis(source_case_id, db, current_user)
    where = "WHERE orthoai_case_id = ?"
    args: list = [source_case_id]
    if site:
        where += " AND site = ?"
        args.append(site)
    total = clinical_db.execute(
        f"SELECT COUNT(*) FROM clinical_cases {where}", args
    ).fetchone()[0]
    rows = clinical_db.execute(
        f"SELECT * FROM clinical_cases {where} ORDER BY id DESC LIMIT ? OFFSET ?",
        args + [limit, offset],
    ).fetchall()
    return ClinicalCaseList(total=total, items=[row_to_out(r) for r in rows])


@router.get("/cases/{case_pk}", response_model=ClinicalCaseOut)
def get_case(
    case_pk: int,
    db: Session = Depends(get_db),
    clinical_db: sqlite3.Connection = Depends(get_clinical_db),
    current_user: User = Depends(get_current_user_dependency),
) -> ClinicalCaseOut:
    row = get_row_or_404(case_pk, clinical_db)
    require_completed_diagnosis(row["orthoai_case_id"], db, current_user)
    return row_to_out(row)


@router.put("/cases/{case_pk}", response_model=ClinicalCaseOut)
def update_case(
    case_pk: int,
    case: ClinicalCaseIn,
    db: Session = Depends(get_db),
    clinical_db: sqlite3.Connection = Depends(get_clinical_db),
    current_user: User = Depends(get_current_user_dependency),
) -> ClinicalCaseOut:
    row = get_row_or_404(case_pk, clinical_db)
    require_completed_diagnosis(row["orthoai_case_id"], db, current_user)
    d = derive(case)
    sets = ", ".join(f"{f} = ?" for f in FIELDS)
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    try:
        clinical_db.execute(
            f"UPDATE clinical_cases SET updated_at = ?, {sets} WHERE id = ?",
            [now] + [d[f] for f in FIELDS] + [case_pk],
        )
        clinical_db.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another clinical case with this site and case ID exists.",
        )
    row = clinical_db.execute(
        "SELECT * FROM clinical_cases WHERE id = ?", (case_pk,)
    ).fetchone()
    return row_to_out(row)


@router.delete("/cases/{case_pk}", status_code=status.HTTP_204_NO_CONTENT)
def delete_case(
    case_pk: int,
    db: Session = Depends(get_db),
    clinical_db: sqlite3.Connection = Depends(get_clinical_db),
    current_user: User = Depends(get_current_user_dependency),
) -> None:
    row = get_row_or_404(case_pk, clinical_db)
    require_completed_diagnosis(row["orthoai_case_id"], db, current_user)
    clinical_db.execute("DELETE FROM clinical_cases WHERE id = ?", (case_pk,))
    clinical_db.commit()


@router.get("/stats", response_model=ClinicalStats)
def stats(
    source_case_id: int = Query(..., description="Completed OrthoAI diagnosis case ID"),
    site: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    clinical_db: sqlite3.Connection = Depends(get_clinical_db),
    current_user: User = Depends(get_current_user_dependency),
) -> ClinicalStats:
    require_completed_diagnosis(source_case_id, db, current_user)
    where = "WHERE orthoai_case_id = ?"
    args: list = [source_case_id]
    if site:
        where += " AND site = ?"
        args.append(site)
    rows = [
        dict(r)
        for r in clinical_db.execute(f"SELECT * FROM clinical_cases {where}", args)
    ]

    def mean(vals: list) -> Optional[float]:
        vals = [v for v in vals if v is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    class_pairs = [r for r in rows if r["class_match"] is not None]
    dhc_pairs = [r for r in rows if r["dhc_delta"] is not None]
    overrides = [r["override"] for r in rows if r["override"]]
    return ClinicalStats(
        n=len(rows),
        sites=len({r["site"] for r in rows}),
        high_need=sum(r["high_need"] for r in rows),
        class_pairs=len(class_pairs),
        class_agreement_pct=(
            round(100 * sum(r["class_match"] for r in class_pairs) / len(class_pairs), 1)
            if class_pairs else None
        ),
        dhc_pairs=len(dhc_pairs),
        dhc_exact_pct=(
            round(100 * sum(r["dhc_delta"] == 0 for r in dhc_pairs) / len(dhc_pairs), 1)
            if dhc_pairs else None
        ),
        mean_dhc_delta=mean([r["dhc_delta"] for r in dhc_pairs]),
        mean_useful=mean([r["useful"] for r in rows]),
        override_rate_pct=(
            round(100 * overrides.count("Yes") / len(overrides), 1) if overrides else None
        ),
        mean_t_manual=mean([r["t_manual"] for r in rows]),
        mean_t_ai=mean([r["t_ai"] for r in rows]),
    )


@router.get("/export.csv")
def export_csv(
    source_case_id: int = Query(..., description="Completed OrthoAI diagnosis case ID"),
    site: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    clinical_db: sqlite3.Connection = Depends(get_clinical_db),
    current_user: User = Depends(get_current_user_dependency),
) -> StreamingResponse:
    require_completed_diagnosis(source_case_id, db, current_user)
    where = "WHERE orthoai_case_id = ?"
    args: list = [source_case_id]
    if site:
        where += " AND site = ?"
        args.append(site)
    rows = clinical_db.execute(
        f"SELECT * FROM clinical_cases {where} ORDER BY id", args
    ).fetchall()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_FIELDS)
    for r in rows:
        writer.writerow([r[f] for f in CSV_FIELDS])
    buf.seek(0)
    stamp = dt.date.today().isoformat()
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="orthoai_clinical_{stamp}.csv"'
        },
    )
