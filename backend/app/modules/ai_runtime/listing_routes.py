"""Non-publishing Listing draft generation from saved keyword runs."""
from __future__ import annotations
import json
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter,Depends,Request
from pydantic import BaseModel,Field
from sqlalchemy import text
from app.core.api import ApiError,ErrorCode,SuccessEnvelope,success_response
from app.core.auth import PREVIEW_PRINCIPAL_ID,Principal
from app.core.permissions import require_permission
from app.db.session import get_session_factory
from app.modules.integration_sync.dependencies import require_source_account_scope
from .provider import AIUnavailable,invoke

router=APIRouter(prefix="/api/ai-runtime",tags=["AI Listing drafts"])
class ListingDraftRequest(BaseModel):
    source_account_ref:str=Field(min_length=1,max_length=128)
    run_id:UUID
class ListingDraftRead(BaseModel):
    title:str
    features:str
    description:str

@router.post("/listing/draft",response_model=SuccessEnvelope[ListingDraftRead,None])
async def draft(request:Request,body:ListingDraftRequest,
    accounts:Annotated[frozenset[str],Depends(require_source_account_scope)],
    principal:Annotated[Principal,Depends(require_permission("action:ai-center:keyword-launch:manage"))]):
    if principal.user_id==PREVIEW_PRINCIPAL_ID or body.source_account_ref not in accounts:
        raise ApiError(code=ErrorCode.DATA_SCOPE_DENIED,status_code=403)
    with get_session_factory()() as session:
        row=session.execute(text("""SELECT r.id,r.status,f.facts_with_sources_json AS facts FROM ai_kw_analysis_run r
          JOIN ai_kw_product_fact_snapshot f ON f.id=r.product_fact_snapshot_id AND f.source_account_ref=r.source_account_ref
          WHERE r.id=:id AND r.source_account_ref=:account AND f.status='confirmed'"""),
          {"id":body.run_id,"account":body.source_account_ref}).mappings().first()
        if row is None or row["status"]!="succeeded":
            raise ApiError(code=ErrorCode.INVALID_REQUEST,status_code=409)
        terms=session.execute(text("""SELECT d.normalized_keyword AS keyword
          FROM ai_kw_run_keyword k JOIN dim_kw_term d ON d.id=k.term_id
          WHERE k.run_id=:run AND k.source_account_ref=:account
            AND (k.exact_selected OR k.broad_selected) ORDER BY k.rank_index NULLS LAST LIMIT 30"""),
          {"run":body.run_id,"account":body.source_account_ref}).scalars().all()
        facts={k:v.get("value","") for k,v in (row["facts"] or {}).items() if isinstance(v,dict)
          and k in ("title","item_type","material","color","pack","size","structure","use")}
        skill=session.execute(text("""SELECT id FROM ai_runtime_skill_versions
          WHERE scene='listing_optimization' AND status='published'
          ORDER BY created_at DESC LIMIT 1""")).scalar_one_or_none()
    prompt=("You write ONE Walmart US listing draft. Only confirmed product facts are reliable. "
      "Competitor products are not evidence of this item's specifications. "
      "Use relevant keywords naturally, never make unsupported claims. "
      "No brand in the listing unless the operator separately approves it. "
      "Return only a JSON object: {\"title\":string,\"features\":[exactly 5 strings],\"description\":string}.\n"
      "Confirmed facts: "+json.dumps(facts,ensure_ascii=False)[:2800]+"\n"
      "Candidate keywords: "+json.dumps(terms,ensure_ascii=False)[:1800])
    try:
        raw,_,_=await invoke(scene="listing_optimization",prompt=prompt,
           actor=principal.user_id,prompt_version="listing-v1",skill_version_id=str(skill) if skill else None)
        parsed=json.loads(raw)
        features=parsed.get("features")
        if (not isinstance(parsed.get("title"),str) or
          not isinstance(parsed.get("description"),str) or
          not isinstance(features,list) or len(features)!=5 or
          not all(isinstance(x,str) and x.strip() for x in features)):
            raise ValueError("AI_LISTING_SCHEMA_INVALID")
    except AIUnavailable as exc:
        raise ApiError(code=exc.code,status_code=503) from None
    except (ValueError,TypeError,KeyError):
        raise ApiError(code=ErrorCode.INVALID_REQUEST,status_code=502) from None
    return success_response(request,data=ListingDraftRead(title=parsed["title"],features="\n".join(features),description=parsed["description"]))
