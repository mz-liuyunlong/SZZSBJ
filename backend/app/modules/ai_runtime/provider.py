"""One audited OpenAI usage boundary shared across AI scenes.

Usage is reserved before outbound calls. Successful calls reconcile to measured
tokens; indeterminate failures retain a conservative reservation, never claimed
as the provider invoice. No secrets or prompts are logged.
"""
from __future__ import annotations
import time
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import text
from app.db.session import get_session_factory
from app.integrations.llm.openai_provider import generate_text

MODEL = "gpt-6-luna"
SCENES = frozenset({"ai_assistant","keyword_launch","listing_optimization","ads_optimization","product_research"})

class AIUnavailable(Exception):
    def __init__(self, code:str):
        self.code=code
        super().__init__(code)

def _config(row):
    cfg=row["config"]
    return cfg if isinstance(cfg,dict) else __import__("json").loads(cfg)

async def invoke(*, scene:str, prompt:str, actor:str, prompt_version:str, skill_version_id:str|None=None) -> tuple[str,int,int]:
    if scene not in SCENES or not prompt.strip() or len(prompt)>10000:
        raise AIUnavailable("AI_REQUEST_INVALID")
    started=time.monotonic()
    charge_id=uuid4()
    with get_session_factory()() as session:
        # Prefer the oldest active connector for stable billing and model selection.
        row=session.execute(text("""SELECT * FROM biz_connectors WHERE kind='openai' AND enabled
          ORDER BY created_at LIMIT 1""")).mappings().first()
        if row is None:
            raise AIUnavailable("AI_CONNECTOR_NOT_CONFIGURED")
        cfg=_config(row)
        if cfg.get("default_model")!=MODEL or MODEL not in cfg.get("model_allowlist",[]):
            raise AIUnavailable("AI_MODEL_NOT_CONFIGURED")
        if scene not in cfg.get("application_scenes",[]):
            raise AIUnavailable("AI_SCENE_DISABLED")
        if skill_version_id is not None:
            skill=session.execute(text("""SELECT instructions, scene, connector_id
                FROM ai_runtime_skill_versions WHERE id=CAST(:id AS uuid)"""),{"id":skill_version_id}).mappings().first()
            if skill is None or skill["scene"]!=scene or skill["connector_id"]!=row["id"]:
                raise AIUnavailable("AI_SKILL_VERSION_INVALID")
            prompt="Skill instructions (administrator approved):\n"+skill["instructions"][:3000]+"\n\n"+prompt
        from app.modules.business_connectors.router import _decrypt
        credential=_decrypt(row["ciphertext"])
        session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:id))"),{"id":str(row["id"])})
        daily=session.execute(text("""SELECT count(*) FROM biz_ai_usage
          WHERE connector_id=:id AND created_at>=date_trunc('day',now())"""),{"id":row["id"]}).scalar_one()
        if daily>=int(cfg.get("daily_limit",100)):
            raise AIUnavailable("AI_DAILY_LIMIT")
        in_rate=Decimal(str(cfg.get("input_price_per_million",0)))
        out_rate=Decimal(str(cfg.get("output_price_per_million",0)))
        budget=Decimal(str(cfg.get("monthly_budget_usd",0)))
        if min(in_rate,out_rate,budget)<=0:
            raise AIUnavailable("AI_BILLING_NOT_CONFIGURED")
        max_out=int(cfg.get("max_output_tokens",1024))
        if len(prompt)>10000:
            raise AIUnavailable("AI_CONTEXT_TOO_LONG")
        reservation=(Decimal(len(prompt.encode("utf8")))*in_rate+Decimal(max_out)*out_rate)/Decimal(1000000)
        spent=Decimal(str(session.execute(text("""SELECT coalesce(sum(cost_usd),0) FROM biz_ai_usage
          WHERE connector_id=:id AND created_at>=date_trunc('month',now())"""),{"id":row["id"]}).scalar_one()))
        if spent+reservation>budget:
            raise AIUnavailable("AI_MONTHLY_LIMIT")
        session.execute(text("""INSERT INTO biz_ai_usage
          (id,connector_id,model,prompt_version,input_tokens,output_tokens,cost_usd,status,created_by)
          VALUES (:id,:connector,:model,:version,0,0,:cost,'pending',:actor)"""),
          {"id":charge_id,"connector":row["id"],"model":MODEL,"version":prompt_version,"cost":reservation,"actor":actor})
        session.commit()
    try:
        result, inp, out=await generate_text(api_key=credential,model=MODEL,prompt=prompt,max_output_tokens=max_out)
    except Exception:
        with get_session_factory()() as session:
            session.execute(text("""UPDATE biz_ai_usage SET status='failed',
              error_code='AI_PROVIDER_FAILURE',duration_ms=:duration WHERE id=:id"""),
              {"id":charge_id,"duration":int((time.monotonic()-started)*1000)})
            session.commit()
        raise AIUnavailable("AI_PROVIDER_FAILURE") from None
    actual=(Decimal(inp)*in_rate+Decimal(out)*out_rate)/Decimal(1000000)
    with get_session_factory()() as session:
        session.execute(text("""UPDATE biz_ai_usage SET status='success',input_tokens=:input,
          output_tokens=:output,cost_usd=:cost,duration_ms=:duration WHERE id=:id"""),
          {"id":charge_id,"input":inp,"output":out,"cost":actual,"duration":int((time.monotonic()-started)*1000)})
        session.commit()
    return result,inp,out
