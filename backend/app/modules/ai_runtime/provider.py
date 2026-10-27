"""One audited OpenAI usage boundary shared across AI scenes.

Usage is reserved before outbound calls. Successful calls reconcile to measured
tokens; indeterminate failures retain a conservative reservation, never claimed
as the provider invoice. No secrets or prompts are logged.
"""

from __future__ import annotations

import time
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import text

from app.db.session import get_session_factory
from app.integrations.llm.openai_provider import failed_call_reservation, generate_text

MODEL = "gpt-6-luna"
MAX_SKILL_INSTRUCTIONS = 150000
MAX_SKILL_RUNTIME_INSTRUCTIONS = 3000
MAX_COMBINED_PROMPT_CHARS = 14000
SCENES = frozenset(
    {
        "ai_assistant",
        "keyword_launch",
        "listing_optimization",
        "ads_optimization",
        "product_research",
    }
)


class AIUnavailable(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def resolve_runtime_instructions(instructions: str, runtime_instructions: str | None) -> str:
    """Use compact instructions; never inject a long reference document."""
    runtime = (runtime_instructions or "").strip()
    if runtime:
        if len(runtime) > MAX_SKILL_RUNTIME_INSTRUCTIONS:
            raise AIUnavailable("AI_SKILL_RUNTIME_INSTRUCTIONS_TOO_LONG")
        return runtime
    if len(instructions) <= MAX_SKILL_RUNTIME_INSTRUCTIONS:
        return instructions
    raise AIUnavailable("AI_SKILL_RUNTIME_INSTRUCTIONS_REQUIRED")


def _config(row):
    cfg = row["config"]
    return cfg if isinstance(cfg, dict) else __import__("json").loads(cfg)


def select_active_connector(session, scene: str, connector_id: UUID | None = None):
    """Select an enabled OpenAI service that supports the requested scene.

    A pinned connector is validated exactly. Without a pin, skip earlier
    services that do not enable this scene rather than failing on the first row.
    """
    if scene not in SCENES:
        raise AIUnavailable("AI_SCENE_INVALID")
    if connector_id is not None:
        row = (
            session.execute(
                text("""SELECT * FROM biz_connectors
                WHERE id=:connector AND kind='openai' AND enabled"""),
                {"connector": connector_id},
            )
            .mappings()
            .first()
        )
        if row is None:
            raise AIUnavailable("AI_CONNECTOR_NOT_CONFIGURED")
        cfg = _config(row)
        if cfg.get("default_model") != MODEL or MODEL not in cfg.get("model_allowlist", []):
            raise AIUnavailable("AI_MODEL_NOT_CONFIGURED")
        if scene not in cfg.get("application_scenes", []):
            raise AIUnavailable("AI_SCENE_DISABLED")
        return row

    rows = (
        session.execute(
            text("""SELECT * FROM biz_connectors
            WHERE kind='openai' AND enabled ORDER BY created_at, id""")
        )
        .mappings()
        .all()
    )
    if not rows:
        raise AIUnavailable("AI_CONNECTOR_NOT_CONFIGURED")

    model_compatible = False
    scene_compatible = False
    for row in rows:
        cfg = _config(row)
        model_ok = cfg.get("default_model") == MODEL and MODEL in cfg.get("model_allowlist", [])
        scene_ok = scene in cfg.get("application_scenes", [])
        model_compatible = model_compatible or model_ok
        scene_compatible = scene_compatible or scene_ok
        if model_ok and scene_ok:
            return row

    if scene_compatible:
        raise AIUnavailable("AI_MODEL_NOT_CONFIGURED")
    if model_compatible:
        raise AIUnavailable("AI_SCENE_DISABLED")
    raise AIUnavailable("AI_MODEL_NOT_CONFIGURED")


def select_published_skill(session, connector_id: UUID, scene: str):
    """Only load a published Skill belonging to the selected OpenAI connector."""
    return (
        session.execute(
            text("""SELECT id, instructions, runtime_instructions FROM ai_runtime_skill_versions
            WHERE connector_id=:connector AND scene=:scene AND status='published'
            ORDER BY version DESC LIMIT 1"""),
            {"connector": connector_id, "scene": scene},
        )
        .mappings()
        .first()
    )


async def invoke(
    *,
    scene: str,
    prompt: str,
    actor: str,
    prompt_version: str,
    skill_version_id: str | None = None,
    connector_id: UUID | None = None,
    visual_parts: list[dict[str, str]] | None = None,
    visual_token_reserve: int = 0,
) -> tuple[str, int, int]:
    if scene not in SCENES or not prompt.strip() or len(prompt) > 10000:
        raise AIUnavailable("AI_REQUEST_INVALID")
    started = time.monotonic()
    charge_id = uuid4()
    with get_session_factory()() as session:
        row = select_active_connector(session, scene, connector_id)
        cfg = _config(row)
        # A queued keyword job pins its service and Skill version at enqueue time.
        # Other interactive scenes select the published Skill for this same service.
        if skill_version_id is not None:
            skill = (
                session.execute(
                    text("""SELECT instructions, runtime_instructions, scene, connector_id, status
                  FROM ai_runtime_skill_versions WHERE id=CAST(:id AS uuid)"""),
                    {"id": skill_version_id},
                )
                .mappings()
                .first()
            )
            if (
                skill is None
                or skill["scene"] != scene
                or skill["connector_id"] != row["id"]
                or skill["status"] not in ("published", "retired")
            ):
                raise AIUnavailable("AI_SKILL_VERSION_INVALID")
        elif connector_id is None:
            skill = select_published_skill(session, row["id"], scene)
        else:
            skill = None
        if skill is not None:
            instructions = resolve_runtime_instructions(
                skill["instructions"], skill.get("runtime_instructions")
            )
            prompt = (
                "Skill runtime instructions (administrator approved):\n"
                + instructions
                + "\n\n"
                + prompt
            )
        if len(prompt) > MAX_COMBINED_PROMPT_CHARS:
            raise AIUnavailable("AI_CONTEXT_TOO_LONG")
        from app.modules.business_connectors.router import _decrypt

        credential = _decrypt(row["ciphertext"])
        session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:id))"), {"id": str(row["id"])})
        daily = session.execute(
            text("""SELECT count(*) FROM biz_ai_usage
          WHERE connector_id=:id AND created_at>=date_trunc('day',now())"""),
            {"id": row["id"]},
        ).scalar_one()
        if daily >= int(cfg.get("daily_limit", 100)):
            raise AIUnavailable("AI_DAILY_LIMIT")
        in_rate = Decimal(str(cfg.get("input_price_per_million", 0)))
        out_rate = Decimal(str(cfg.get("output_price_per_million", 0)))
        budget = Decimal(str(cfg.get("monthly_budget_usd", 0)))
        if min(in_rate, out_rate, budget) <= 0:
            raise AIUnavailable("AI_BILLING_NOT_CONFIGURED")
        max_out = int(cfg.get("max_output_tokens", 1024))
        if len(prompt) > 10000:
            raise AIUnavailable("AI_CONTEXT_TOO_LONG")
        reservation = (
            Decimal(len(prompt.encode("utf8")) + visual_token_reserve) * in_rate
            + Decimal(max_out) * out_rate
        ) / Decimal(1000000)
        spent = Decimal(
            str(
                session.execute(
                    text("""SELECT coalesce(sum(cost_usd),0) FROM biz_ai_usage
          WHERE connector_id=:id AND created_at>=date_trunc('month',now())"""),
                    {"id": row["id"]},
                ).scalar_one()
            )
        )
        if spent + reservation > budget:
            raise AIUnavailable("AI_MONTHLY_LIMIT")
        session.execute(
            text("""INSERT INTO biz_ai_usage
          (id,connector_id,model,prompt_version,input_tokens,output_tokens,cost_usd,status,created_by)
          VALUES (:id,:connector,:model,:version,0,0,:cost,'pending',:actor)"""),
            {
                "id": charge_id,
                "connector": row["id"],
                "model": MODEL,
                "version": prompt_version,
                "cost": reservation,
                "actor": actor,
            },
        )
        session.commit()
    try:
        result, inp, out = await generate_text(
            api_key=credential,
            model=MODEL,
            prompt=prompt,
            max_output_tokens=max_out,
            visual_parts=visual_parts,
        )
    except Exception as exc:
        failed_cost, failure_code = failed_call_reservation(
            reservation, getattr(exc, "status_code", None)
        )
        with get_session_factory()() as session:
            session.execute(
                text("""UPDATE biz_ai_usage SET status='failed',cost_usd=:cost,
              error_code=:error,duration_ms=:duration WHERE id=:id"""),
                {
                    "id": charge_id,
                    "cost": failed_cost,
                    "error": failure_code,
                    "duration": int((time.monotonic() - started) * 1000),
                },
            )
            session.commit()
        raise AIUnavailable(failure_code) from None
    actual = (Decimal(inp) * in_rate + Decimal(out) * out_rate) / Decimal(1000000)
    with get_session_factory()() as session:
        session.execute(
            text("""UPDATE biz_ai_usage SET status='success',input_tokens=:input,
          output_tokens=:output,cost_usd=:cost,duration_ms=:duration WHERE id=:id"""),
            {
                "id": charge_id,
                "input": inp,
                "output": out,
                "cost": actual,
                "duration": int((time.monotonic() - started) * 1000),
            },
        )
        session.commit()
    return result, inp, out
