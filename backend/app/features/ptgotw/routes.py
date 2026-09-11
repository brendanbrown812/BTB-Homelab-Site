import uuid
from datetime import datetime
from html import escape
from html.parser import HTMLParser

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import admin_user, current_user
from app.database.session import get_db
from app.features.ptgotw.models import PTGWriteup
from app.models.user import User, UserRole

router = APIRouter(prefix="/ptgotw", tags=["PTGOTW"])
ALLOWED_TAGS = {"b", "strong", "i", "em", "u", "p", "div", "br", "ol", "ul", "li"}
VOID_TAGS = {"br"}


class _WriteupSanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.output: list[str] = []
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        if tag in ALLOWED_TAGS:
            self.output.append(f"<{tag}>")

    def handle_startendtag(self, tag: str, attrs):
        if tag in VOID_TAGS:
            self.output.append(f"<{tag}>")

    def handle_endtag(self, tag: str):
        if tag in ALLOWED_TAGS and tag not in VOID_TAGS:
            self.output.append(f"</{tag}>")

    def handle_data(self, data: str):
        self.output.append(escape(data))
        self.text.append(data)


class WriteupCreate(BaseModel):
    year: int = Field(ge=2000, le=2100)
    week: int = Field(ge=1, le=18)
    author_id: uuid.UUID
    submitted_by_author: bool = False
    content_html: str = Field(default="", max_length=120000)
    is_published: bool = False


class WriteupUpdate(BaseModel):
    content_html: str = Field(max_length=120000)
    year: int | None = Field(default=None, ge=2000, le=2100)
    week: int | None = Field(default=None, ge=1, le=18)
    author_id: uuid.UUID | None = None
    submitted_by_author: bool | None = None
    is_published: bool | None = None


def _clean_content(value: str) -> str:
    sanitizer = _WriteupSanitizer()
    sanitizer.feed(value.strip())
    sanitizer.close()
    plain_text = "".join(sanitizer.text)
    if len(plain_text) > 30000:
        raise HTTPException(status_code=422, detail="Writeups cannot exceed 30,000 characters")
    if not plain_text.strip():
        return ""
    return "".join(sanitizer.output).strip()


async def _validate_author(db: AsyncSession, author_id: uuid.UUID) -> str:
    name = await db.scalar(select(User.display_name).where(User.id == author_id, User.role == UserRole.user, User.is_active.is_(True)))
    if not name:
        raise HTTPException(status_code=400, detail="Choose an active non-admin author")
    return name


async def _author_name(db: AsyncSession, author_id: uuid.UUID) -> str:
    name = await db.scalar(select(User.display_name).where(User.id == author_id))
    if not name:
        raise HTTPException(status_code=404, detail="Writeup author not found")
    return name


def _payload(writeup: PTGWriteup, author_name: str, viewer: User, include_content: bool = True) -> dict:
    result = {
        "id": writeup.id,
        "year": writeup.year,
        "week": writeup.week,
        "author": {"id": writeup.author_id, "display_name": author_name},
        "updated_at": writeup.updated_at,
    }
    if include_content:
        result["content_html"] = writeup.content_html
    if viewer.role is UserRole.admin:
        result["submitted_by_author"] = writeup.submitted_by_author
        result["has_content"] = bool(writeup.content_html)
    if viewer.role is UserRole.admin or (viewer.id == writeup.author_id and writeup.submitted_by_author):
        result["is_published"] = writeup.is_published
    return result


@router.get("")
async def list_writeups(year: int | None = None, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    selected_year = year or datetime.now().year
    years_query = select(PTGWriteup.year)
    rows_query = (
        select(PTGWriteup, User.display_name)
        .join(User, User.id == PTGWriteup.author_id)
        .where(PTGWriteup.year == selected_year)
    )
    if user.role is not UserRole.admin:
        years_query = years_query.where(PTGWriteup.is_published.is_(True))
        rows_query = rows_query.where(PTGWriteup.is_published.is_(True))
    available = list((await db.scalars(years_query.distinct().order_by(PTGWriteup.year.desc()))).all())
    if selected_year not in available:
        available.append(selected_year)
        available.sort(reverse=True)
    rows = (await db.execute(rows_query.order_by(PTGWriteup.week.desc()))).all()
    return {
        "year": selected_year,
        "is_admin_view": user.role is UserRole.admin,
        "available_years": available,
        "writeups": [_payload(writeup, author_name, user, include_content=False) for writeup, author_name in rows],
    }


@router.get("/editable")
async def editable_writeups(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    query = select(PTGWriteup, User.display_name).join(User, User.id == PTGWriteup.author_id)
    if user.role is not UserRole.admin:
        query = query.where(PTGWriteup.author_id == user.id, PTGWriteup.submitted_by_author.is_(True))
    rows = (await db.execute(query.order_by(PTGWriteup.year.desc(), PTGWriteup.week.desc()))).all()
    return [_payload(writeup, author_name, user) for writeup, author_name in rows]


@router.get("/authors", dependencies=[Depends(admin_user)])
async def list_authors(db: AsyncSession = Depends(get_db)):
    users = (await db.scalars(select(User).where(User.role == UserRole.user, User.is_active.is_(True)).order_by(User.display_name))).all()
    return [{"id": user.id, "display_name": user.display_name} for user in users]


@router.post("", status_code=201)
async def create_writeup(body: WriteupCreate, admin: User = Depends(admin_user), db: AsyncSession = Depends(get_db)):
    author_name = await _validate_author(db, body.author_id)
    content_html = _clean_content(body.content_html)
    if body.is_published and not content_html:
        raise HTTPException(status_code=422, detail="Add the writeup before publishing it")
    writeup = PTGWriteup(
        year=body.year,
        week=body.week,
        author_id=body.author_id,
        submitted_by_author=body.submitted_by_author,
        content_html=content_html,
        is_published=body.is_published,
        created_by_user_id=admin.id,
    )
    db.add(writeup)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail=f"A Week {body.week} writeup already exists for {body.year}") from None
    await db.refresh(writeup)
    return _payload(writeup, author_name, admin)


@router.delete("/{writeup_id}", status_code=204)
async def delete_writeup(writeup_id: uuid.UUID, _: User = Depends(admin_user), db: AsyncSession = Depends(get_db)):
    writeup = await db.get(PTGWriteup, writeup_id)
    if not writeup:
        raise HTTPException(status_code=404, detail="Writeup not found")
    await db.delete(writeup)
    await db.commit()


@router.get("/{writeup_id}")
async def get_writeup(writeup_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    writeup = await db.get(PTGWriteup, writeup_id)
    if not writeup or (not writeup.is_published and user.role is not UserRole.admin and not (writeup.author_id == user.id and writeup.submitted_by_author)):
        raise HTTPException(status_code=404, detail="Writeup not found")
    return _payload(writeup, await _author_name(db, writeup.author_id), user)


@router.put("/{writeup_id}")
async def update_writeup(writeup_id: uuid.UUID, body: WriteupUpdate, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    writeup = await db.get(PTGWriteup, writeup_id)
    if not writeup:
        raise HTTPException(status_code=404, detail="Writeup not found")
    is_admin = user.role is UserRole.admin
    if not is_admin and not (writeup.author_id == user.id and writeup.submitted_by_author):
        raise HTTPException(status_code=403, detail="You do not have permission to edit this writeup")
    if is_admin:
        if body.year is not None:
            writeup.year = body.year
        if body.week is not None:
            writeup.week = body.week
        if body.author_id is not None and body.author_id != writeup.author_id:
            await _validate_author(db, body.author_id)
            writeup.author_id = body.author_id
        if body.submitted_by_author is not None:
            writeup.submitted_by_author = body.submitted_by_author
    content_html = _clean_content(body.content_html)
    next_published = body.is_published if body.is_published is not None else writeup.is_published
    if next_published and not content_html:
        raise HTTPException(status_code=422, detail="Add the writeup before publishing it")
    writeup.content_html = content_html
    writeup.is_published = next_published
    conflict_year, conflict_week = writeup.year, writeup.week
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail=f"A Week {conflict_week} writeup already exists for {conflict_year}") from None
    await db.refresh(writeup)
    return _payload(writeup, await _author_name(db, writeup.author_id), user)
