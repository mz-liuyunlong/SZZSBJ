"""Independent, versioned Skill library and connector bindings.

All mutations require super-admin. Imports never execute uploaded source code.
Published versions are immutable; pinned history survives unbind/soft deletion.
"""

from __future__ import annotations

import base64
import binascii
import io
import re
from pathlib import PurePosixPath
from typing import Annotated
from uuid import UUID, uuid4
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.core.api import ApiError, ErrorCode, success_response
from app.core.auth import Principal
from app.core.permissions import require_super_admin
from app.db.session import get_session_factory
from app.modules.ai_runtime.attachment_extraction import (
    AttachmentBody,
    AttachmentError,
    extract_attachments,
)
from app.modules.ai_runtime.provider import SCENES, AIUnavailable, resolve_runtime_instructions

router = APIRouter(prefix="/api/ai-runtime/skill-library", tags=["AI Skill Library"])
admin = Annotated[Principal, Depends(require_super_admin)]
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_SKILL_TEXT = 150000


class SkillDraft(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    slug: str = Field(pattern=r"^[a-z][a-z0-9-]{1,62}$")
    scene: str
    description: str = Field(min_length=8, max_length=1000)
    instructions: str = Field(min_length=1, max_length=MAX_SKILL_TEXT)
    runtime_instructions: str | None = Field(default=None, max_length=3000)


class RevisionDraft(BaseModel):
    instructions: str = Field(min_length=1, max_length=MAX_SKILL_TEXT)
    runtime_instructions: str | None = Field(default=None, max_length=3000)
    description: str | None = Field(default=None, max_length=1000)


class UploadBody(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    content_base64: str = Field(min_length=1, max_length=2_900_000)


class BindingsWrite(BaseModel):
    bindings: dict[str, UUID | None]


def _check_scene(scene: str) -> None:
    if scene not in SCENES:
        raise ApiError(
            code=ErrorCode.INVALID_REQUEST, status_code=422, message="不支持的 Skill 使用场景"
        )


def _decode_file(body: UploadBody) -> tuple[str, str, bytes]:
    filename = PurePosixPath(body.name.replace("\\", "/")).name
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix not in {".md", ".txt", ".csv", ".docx", ".xlsx", ".pdf", ".zip"}:
        raise ApiError(code=ErrorCode.INVALID_REQUEST, status_code=422, message="不支持的文件类型")
    try:
        raw = base64.b64decode(body.content_base64, validate=True)
    except binascii.Error:
        raise ApiError(
            code=ErrorCode.INVALID_REQUEST, status_code=422, message="文件内容无效"
        ) from None
    if not raw or len(raw) > MAX_UPLOAD_BYTES:
        raise ApiError(
            code=ErrorCode.INVALID_REQUEST, status_code=422, message="单个文件必须小于 2MB"
        )
    return filename, suffix, raw


def _extract_document(filename: str, suffix: str, raw: bytes) -> str:
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(raw), strict=True)
            if reader.is_encrypted or not 1 <= len(reader.pages) <= 30:
                raise ValueError("invalid PDF")
            output = "\n".join(page.extract_text() or "" for page in reader.pages)[:30000]
            if not output.strip():
                raise ValueError("PDF has no extractable text")
            return output
        except Exception:
            raise ApiError(
                code=ErrorCode.INVALID_REQUEST,
                status_code=422,
                message="PDF 无法提取文字；扫描件请先转换为可检索 PDF",
            ) from None
    try:
        # Reuse bounded, read-only Word / Excel / text parser. Never execute macros.
        return extract_attachments(
            [AttachmentBody(name=filename, content_base64=base64.b64encode(raw).decode("ascii"))]
        )[:30000]
    except AttachmentError:
        raise ApiError(
            code=ErrorCode.INVALID_REQUEST, status_code=422, message="无法读取文档内容"
        ) from None


def _extract_zip(raw: bytes) -> tuple[str, str, str]:
    try:
        with ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            if len(infos) > 60 or sum(i.file_size for i in infos) > 4 * 1024 * 1024:
                raise ValueError("oversized archive")
            for info in infos:
                path = PurePosixPath(info.filename)
                if path.is_absolute() or ".." in path.parts or info.file_size > MAX_UPLOAD_BYTES:
                    raise ValueError("unsafe archive path")
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("symlink is not allowed")
            candidates = [
                i
                for i in infos
                if i.filename.split("/")[-1] == "SKILL.md"
                and len(PurePosixPath(i.filename).parts) <= 2
            ]
            if len(candidates) != 1:
                raise ValueError("zip must contain exactly one SKILL.md")
            content = archive.read(candidates[0]).decode("utf-8-sig")
            root_path = PurePosixPath(candidates[0].filename).parent
            extras = []
            for info in infos:
                path = PurePosixPath(info.filename)
                # Keep text references, not scripts or binary assets. Do not execute any source.
                if path == PurePosixPath(candidates[0].filename) or info.is_dir():
                    continue
                if path.suffix.lower() not in (".md", ".txt") or info.file_size > 50000:
                    continue
                if root_path != PurePosixPath(".") and path.parts[0] != root_path.parts[0]:
                    continue
                if "references" not in path.parts:
                    continue
                try:
                    reference = archive.read(info).decode("utf-8-sig")[:10000]
                except UnicodeDecodeError:
                    continue
                extras.append("\n\n## Imported reference: " + path.name + "\n" + reference)
            content = (content + "".join(extras))[:MAX_SKILL_TEXT]
    except (BadZipFile, ValueError, UnicodeDecodeError, RuntimeError, OSError):
        raise ApiError(
            code=ErrorCode.INVALID_REQUEST,
            status_code=422,
            message="ZIP 必须包含一份安全、可读取的 SKILL.md",
        ) from None
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n", content, re.S)
    if not match:
        raise ApiError(
            code=ErrorCode.INVALID_REQUEST, status_code=422, message="SKILL.md 缺少 YAML 元信息"
        )
    front = match.group(1)
    name = re.search(r"(?m)^name:\s*['\"]?([a-z][a-z0-9-]{1,62})['\"]?\s*$", front)
    desc = re.search(r"(?m)^description:\s*(.+)$", front)
    if not name or not desc or not desc.group(1).strip():
        raise ApiError(
            code=ErrorCode.INVALID_REQUEST,
            status_code=422,
            message="SKILL.md 需要 name 与 description",
        )
    return name.group(1), desc.group(1).strip().strip("'\""), content[:MAX_SKILL_TEXT]


def _current_skill(session, skill_id: UUID, lock: bool = False):
    suffix = " FOR UPDATE" if lock else ""
    return (
        session.execute(
            text(
                "SELECT id,name,slug,scene,description FROM ai_skill_library WHERE id=:id AND deleted_at IS NULL"
                + suffix
            ),
            {"id": skill_id},
        )
        .mappings()
        .first()
    )


def _rows(session, query: str, **values):
    return [dict(x) for x in session.execute(text(query), values).mappings().all()]


@router.get("")
def list_skills(request: Request, principal: admin):
    with get_session_factory()() as session:
        rows = _rows(
            session,
            """SELECT s.id,s.slug,s.name,s.scene,s.description,s.updated_at,
          (SELECT max(version) FROM ai_skill_revisions v WHERE v.skill_id=s.id) AS latest_version,
          (SELECT max(version) FROM ai_skill_revisions v WHERE v.skill_id=s.id AND v.status='published') AS published_version
          FROM ai_skill_library s WHERE s.deleted_at IS NULL ORDER BY s.updated_at DESC,s.name""",
        )
    return success_response(request, data=rows)


@router.get("/published")
def published_skills(request: Request, principal: admin):
    with get_session_factory()() as session:
        rows = _rows(
            session,
            """SELECT s.id AS skill_id,s.name,s.scene,v.id AS revision_id,v.version
          FROM ai_skill_library s JOIN ai_skill_revisions v ON v.skill_id=s.id
          WHERE s.deleted_at IS NULL AND v.status='published'
          ORDER BY s.name,v.version DESC""",
        )
    return success_response(request, data=rows)


@router.get("/bindings")
def get_bindings(request: Request, connector_id: UUID, principal: admin):
    with get_session_factory()() as session:
        rows = _rows(
            session,
            """SELECT scene, revision_id FROM ai_skill_bindings
          WHERE connector_id=:connector""",
            connector=connector_id,
        )
    return success_response(request, data=rows)


@router.put("/bindings/{connector_id}")
def save_bindings(connector_id: UUID, body: BindingsWrite, request: Request, principal: admin):
    if not set(body.bindings).issubset(SCENES):
        raise ApiError(code=ErrorCode.INVALID_REQUEST, status_code=422)
    with get_session_factory()() as session:
        c = (
            session.execute(
                text("SELECT kind, config FROM biz_connectors WHERE id=:id FOR UPDATE"),
                {"id": connector_id},
            )
            .mappings()
            .first()
        )
        if not c or c["kind"] != "openai":
            raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
        for scene, revision in body.bindings.items():
            if revision is not None:
                matched = session.execute(
                    text("""SELECT 1 FROM ai_skill_revisions v
                  JOIN ai_skill_library s ON s.id=v.skill_id
                  WHERE v.id=:version AND v.status='published' AND s.deleted_at IS NULL AND s.scene=:scene"""),
                    {"version": revision, "scene": scene},
                ).scalar_one_or_none()
                if not matched:
                    raise ApiError(
                        code=ErrorCode.INVALID_REQUEST,
                        status_code=422,
                        message="绑定必须选择该场景已发布的 Skill",
                    )
                session.execute(
                    text("""INSERT INTO ai_skill_revision_grants(revision_id,connector_id)
                  VALUES (:revision,:connector) ON CONFLICT DO NOTHING"""),
                    {"revision": revision, "connector": connector_id},
                )
            session.execute(
                text("""INSERT INTO ai_skill_bindings(connector_id,scene,revision_id)
              VALUES (:connector,:scene,:revision)
              ON CONFLICT(connector_id,scene) DO UPDATE SET revision_id=EXCLUDED.revision_id"""),
                {"connector": connector_id, "scene": scene, "revision": revision},
            )
        session.commit()
    return success_response(request, data={"ok": True})


@router.post("")
def create_skill(body: SkillDraft, request: Request, principal: admin):
    _check_scene(body.scene)
    sid, revision = uuid4(), uuid4()
    with get_session_factory()() as session:
        if session.execute(
            text("SELECT 1 FROM ai_skill_library WHERE slug=:slug"), {"slug": body.slug}
        ).scalar_one_or_none():
            raise ApiError(
                code=ErrorCode.INVALID_REQUEST, status_code=409, message="Skill 标识已存在"
            )
        session.execute(
            text("""INSERT INTO ai_skill_library(id,slug,name,scene,description,created_by)
            VALUES (:id,:slug,:name,:scene,:desc,:actor)"""),
            {
                "id": sid,
                "slug": body.slug,
                "name": body.name,
                "scene": body.scene,
                "desc": body.description,
                "actor": str(principal.user_id),
            },
        )
        session.execute(
            text("""INSERT INTO ai_skill_revisions(id,skill_id,version,status,instructions,runtime_instructions,created_by)
            VALUES (:id,:sid,1,'draft',:instructions,:runtime,:actor)"""),
            {
                "id": revision,
                "sid": sid,
                "instructions": body.instructions,
                "runtime": body.runtime_instructions,
                "actor": str(principal.user_id),
            },
        )
        session.commit()
    return success_response(request, data={"id": sid, "revision_id": revision, "version": 1})


@router.post("/import")
def import_skill(body: UploadBody, request: Request, principal: admin):
    _filename, suffix, raw = _decode_file(body)
    if suffix != ".zip":
        raise ApiError(
            code=ErrorCode.INVALID_REQUEST, status_code=422, message="请上传 ZIP 格式 Skill 包"
        )
    slug, description, content = _extract_zip(raw)
    if len(description.strip()) < 8:
        raise ApiError(
            code=ErrorCode.INVALID_REQUEST,
            status_code=422,
            message="Skill description 至少需要 8 个字符",
        )
    new = SkillDraft(
        name=slug.replace("-", " ").title(),
        slug=slug,
        scene="ai_assistant",
        description=description[:1000],
        instructions=content,
        runtime_instructions=content[:3000] if len(content) <= 3000 else None,
    )
    return create_skill(new, request, principal)


@router.get("/{skill_id}/versions")
def list_versions(skill_id: UUID, request: Request, principal: admin):
    with get_session_factory()() as session:
        if not _current_skill(session, skill_id):
            raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
        rows = _rows(
            session,
            """SELECT id,version,status,instructions,runtime_instructions,created_at
          FROM ai_skill_revisions WHERE skill_id=:sid ORDER BY version DESC""",
            sid=skill_id,
        )
    return success_response(request, data=rows)


@router.post("/{skill_id}/drafts")
def new_draft(skill_id: UUID, body: RevisionDraft, request: Request, principal: admin):
    with get_session_factory()() as session:
        skill = _current_skill(session, skill_id, lock=True)
        if not skill:
            raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
        rev = uuid4()
        latest = session.execute(
            text("SELECT coalesce(max(version),0)+1 FROM ai_skill_revisions WHERE skill_id=:id"),
            {"id": skill_id},
        ).scalar_one()
        session.execute(
            text("""INSERT INTO ai_skill_revisions(id,skill_id,version,status,instructions,runtime_instructions,created_by)
          VALUES (:id,:sid,:version,'draft',:instructions,:runtime,:actor)"""),
            {
                "id": rev,
                "sid": skill_id,
                "version": latest,
                "instructions": body.instructions,
                "runtime": body.runtime_instructions,
                "actor": str(principal.user_id),
            },
        )
        if body.description is not None:
            session.execute(
                text("UPDATE ai_skill_library SET description=:d,updated_at=now() WHERE id=:id"),
                {"d": body.description, "id": skill_id},
            )
        session.commit()
    return success_response(request, data={"id": rev, "version": latest})


@router.post("/{skill_id}/versions/{revision_id}/publish")
def publish(skill_id: UUID, revision_id: UUID, request: Request, principal: admin):
    with get_session_factory()() as session:
        skill = _current_skill(session, skill_id, lock=True)
        row = (
            session.execute(
                text("SELECT * FROM ai_skill_revisions WHERE id=:rev AND skill_id=:sid FOR UPDATE"),
                {"rev": revision_id, "sid": skill_id},
            )
            .mappings()
            .first()
        )
        if not skill or not row:
            raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
        if row["status"] != "draft":
            raise ApiError(
                code=ErrorCode.INVALID_REQUEST, status_code=409, message="只能发布草稿版本"
            )
        try:
            resolve_runtime_instructions(row["instructions"], row["runtime_instructions"])
        except AIUnavailable:
            raise ApiError(
                code=ErrorCode.INVALID_REQUEST,
                status_code=422,
                message="请填写最多 3000 字的精简运行指令",
            ) from None
        # Preserve the connector grant for queued jobs pinned to retired revisions.
        # Only connectors explicitly bound to the prior published revision inherit.
        session.execute(
            text("""INSERT INTO ai_skill_revision_grants(revision_id,connector_id)
              SELECT :new_rev, connector_id FROM ai_skill_bindings
              WHERE revision_id IN (SELECT id FROM ai_skill_revisions
                WHERE skill_id=:sid AND status='published')
              ON CONFLICT DO NOTHING"""),
            {"new_rev": revision_id, "sid": skill_id},
        )
        # Atomic upgrade: bound scenes track the latest published revision,
        # while previously pinned jobs keep their immutable old revision ID.
        session.execute(
            text("""UPDATE ai_skill_bindings SET revision_id=:new_rev
          WHERE revision_id IN (SELECT id FROM ai_skill_revisions
            WHERE skill_id=:sid AND status='published')"""),
            {"new_rev": revision_id, "sid": skill_id},
        )
        session.execute(
            text(
                "UPDATE ai_skill_revisions SET status='retired' WHERE skill_id=:sid AND status='published'"
            ),
            {"sid": skill_id},
        )
        session.execute(
            text("UPDATE ai_skill_revisions SET status='published' WHERE id=:rev"),
            {"rev": revision_id},
        )
        session.execute(
            text("UPDATE ai_skill_library SET updated_at=now() WHERE id=:sid"), {"sid": skill_id}
        )
        session.commit()
    return success_response(request, data={"ok": True})


@router.delete("/{skill_id}")
def remove_skill(skill_id: UUID, request: Request, principal: admin):
    with get_session_factory()() as session:
        if not _current_skill(session, skill_id, lock=True):
            raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
        session.execute(
            text(
                "DELETE FROM ai_skill_bindings WHERE revision_id IN (SELECT id FROM ai_skill_revisions WHERE skill_id=:sid)"
            ),
            {"sid": skill_id},
        )
        session.execute(
            text("UPDATE ai_skill_library SET deleted_at=now() WHERE id=:sid"), {"sid": skill_id}
        )
        session.execute(
            text(
                "UPDATE ai_skill_revisions SET status='retired' WHERE skill_id=:sid AND status='published'"
            ),
            {"sid": skill_id},
        )
        session.commit()
    return success_response(request, data={"ok": True})


@router.post("/{skill_id}/versions/{revision_id}/documents")
def upload_document(
    skill_id: UUID, revision_id: UUID, body: UploadBody, request: Request, principal: admin
):
    filename, suffix, raw = _decode_file(body)
    if suffix == ".zip":
        raise ApiError(
            code=ErrorCode.INVALID_REQUEST, status_code=422, message="标准 Skill ZIP 请使用导入入口"
        )
    extracted = _extract_document(filename, suffix, raw)
    if not extracted.strip():
        raise ApiError(
            code=ErrorCode.INVALID_REQUEST, status_code=422, message="未提取到可用文档文本"
        )
    with get_session_factory()() as session:
        skill = _current_skill(session, skill_id, lock=True)
        rev = (
            session.execute(
                text(
                    "SELECT status,instructions FROM ai_skill_revisions WHERE id=:rev AND skill_id=:sid FOR UPDATE"
                ),
                {"rev": revision_id, "sid": skill_id},
            )
            .mappings()
            .first()
        )
        if not skill or not rev:
            raise ApiError(code=ErrorCode.NOT_FOUND, status_code=404)
        if rev["status"] != "draft":
            raise ApiError(
                code=ErrorCode.INVALID_REQUEST, status_code=409, message="请先保存新草稿版本再上传"
            )
        total = session.execute(
            text("SELECT count(*) FROM ai_skill_documents WHERE revision_id=:rev"),
            {"rev": revision_id},
        ).scalar_one()
        if total >= 5:
            raise ApiError(
                code=ErrorCode.INVALID_REQUEST, status_code=422, message="每个版本最多五份资料"
            )
        append = "\n\n## 上传参考资料：" + filename + "\n" + extracted[:20000]
        if len(rev["instructions"] + append) > MAX_SKILL_TEXT:
            raise ApiError(
                code=ErrorCode.INVALID_REQUEST,
                status_code=422,
                message="上传后 Skill 正文超出长度上限",
            )
        session.execute(
            text("""INSERT INTO ai_skill_documents(id,revision_id,filename,size_bytes,content,extracted_text)
          VALUES (:id,:rev,:name,:size,:content,:text)"""),
            {
                "id": uuid4(),
                "rev": revision_id,
                "name": filename,
                "size": len(raw),
                "content": raw,
                "text": extracted[:20000],
            },
        )
        session.execute(
            text(
                "UPDATE ai_skill_revisions SET instructions=instructions || :append WHERE id=:rev"
            ),
            {"append": append, "rev": revision_id},
        )
        session.commit()
    return success_response(request, data={"ok": True, "name": filename, "chars": len(extracted)})
