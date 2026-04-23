"""LLM summarization stage: per-cluster extraction of pain points or content ideas."""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

from painscope.adapters import RawPost
from painscope.llm.client import complete_structured

logger = logging.getLogger(__name__)


class Quote(BaseModel):
    text: str = Field(description="Verbatim quote from a post, <= 200 chars")
    url: str = Field(description="Source URL for this quote")


class PainPoint(BaseModel):
    title: str = Field(description="Short (5-10 words) title of the pain point")
    summary: str = Field(description="Two-sentence description in the user's language")
    severity: int = Field(ge=1, le=5, description="1=mild, 5=severe")
    content_angle: str = Field(
        description="One-sentence suggestion for a blog post or video addressing this pain"
    )
    quotes: list[Quote] = Field(description="1-3 representative verbatim quotes")
    source_distribution: dict[str, int] = Field(
        default_factory=dict,
        description="How many posts per source label contributed to this cluster. Set by orchestrator, not LLM.",
    )


class ContentIdea(BaseModel):
    title: str = Field(description="Compelling article or video title")
    angle: str = Field(description="One-sentence description of the hook / angle")
    target_questions: list[str] = Field(
        description="2-3 real questions from users this content would answer"
    )
    quotes: list[Quote] = Field(description="1-3 representative verbatim quotes")
    source_distribution: dict[str, int] = Field(
        default_factory=dict,
        description="How many posts per source label contributed to this cluster. Set by orchestrator, not LLM.",
    )


ScanType = Literal["pain_points", "content_ideas"]


PROMPT_PAIN_TR = """Aşağıda bir Reddit/YouTube/forum/kullanıcı yorumu kümesinden alıntılar var.
Bunlar aynı temanın farklı ifadeleri. Bu kümedeki ortak "sorun/pain point"i çıkar.

Kullanıcı alıntıları:
{quotes}

Çıktı olarak sadece geçerli bir JSON döndür. Türkçe yaz.
- title: 5-10 kelimelik başlık
- summary: iki cümle
- severity: 1-5 arası tam sayı (5 = çok şiddetli şikayet)
- content_angle: bu sorunu ele alacak bir içeriğin açısı (tek cümle)
- quotes: 1-3 alıntı (her biri: text, url)
"""

PROMPT_PAIN_EN = """Below are quotes from a cluster of Reddit/YouTube/forum/user comments.
They express the same theme from different angles. Extract the shared pain point.

User quotes:
{quotes}

Return only a valid JSON object. Write in English.
- title: 5-10 word title
- summary: two sentences
- severity: integer 1-5 (5 = severe frustration)
- content_angle: one-sentence angle for a piece of content addressing this pain
- quotes: 1-3 quotes (each: text, url)
"""

PROMPT_IDEA_TR = """Aşağıda bir Reddit/YouTube/forum/kullanıcı yorumu kümesinden alıntılar var.
İçinde sorular, merak edilen konular, öğrenme istekleri var. Bir içerik fikri çıkar
(blog yazısı, video, ya da sosyal medya paylaşımı).

Kullanıcı alıntıları:
{quotes}

Çıktı olarak sadece geçerli bir JSON döndür. Türkçe yaz.
- title: ilgi çekici içerik başlığı
- angle: içeriğin açısı/kancası (tek cümle)
- target_questions: bu içeriğin cevaplayacağı 2-3 gerçek kullanıcı sorusu
- quotes: 1-3 alıntı (her biri: text, url)
"""

PROMPT_IDEA_EN = """Below are quotes from a cluster of Reddit/YouTube/forum/user comments.
They include questions, curiosities, or learning requests. Extract a content idea
(blog post, video, or social post).

User quotes:
{quotes}

Return only a valid JSON object. Write in English.
- title: compelling content title
- angle: one-sentence hook for the content
- target_questions: 2-3 real user questions the content would answer
- quotes: 1-3 quotes (each: text, url)
"""


def _format_quotes(posts: list[RawPost]) -> str:
    lines = []
    for p in posts[:20]:  # cap at 20 quotes per cluster for token budget
        content = p.content[:400]
        lines.append(f'- "{content}" ({p.url})')
    return "\n".join(lines)


def summarize_cluster(
    cluster_posts: list[RawPost],
    *,
    scan_type: ScanType,
    language: str = "tr",
    model: str | None = None,
) -> PainPoint | ContentIdea:
    """Summarize a single cluster of posts into a pain point or content idea."""
    quotes_text = _format_quotes(cluster_posts)

    if scan_type == "pain_points":
        template = PROMPT_PAIN_TR if language == "tr" else PROMPT_PAIN_EN
        schema = PainPoint
    else:
        template = PROMPT_IDEA_TR if language == "tr" else PROMPT_IDEA_EN
        schema = ContentIdea

    prompt = template.format(quotes=quotes_text)
    return complete_structured(
        prompt, schema, model=model, language=language, temperature=0.2
    )
