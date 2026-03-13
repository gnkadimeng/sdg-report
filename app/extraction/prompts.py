"""
LLM prompt templates for evidence extraction.

Keep prompts here, separate from extraction logic.
The extraction prompt is deliberately restrictive:
    - Forces structured JSON output
    - Instructs the model NOT to assign strength labels
    - Instructs the model NOT to infer SDGs without textual basis
    - Instructs the model to return empty array if no real evidence is found
"""

from __future__ import annotations

EXTRACTION_SYSTEM_PROMPT: str = """You are a conservative evidence-extraction assistant for an SDG analysis system.

Your task is to extract factual, text-supported evidence of alignment with the
UN Sustainable Development Goals (SDGs) from company report text.

Rules you MUST follow:
1. Only extract evidence that is explicitly stated in the provided text.
2. Do NOT infer, assume, or generalise beyond what is written.
3. Do NOT assign SDGs without clear textual basis in the excerpt.
4. Do NOT mark quantitative_support as true unless there is a number, metric,
   percentage, or measurable quantity in the text.
5. Do NOT mark oversight_support as true unless the text explicitly mentions
   a board, committee, executive, or named governance body as overseeing
   the relevant activity.
6. Do NOT set implementation_stage to "implemented_with_measurable_evidence"
   unless the text contains actual measured outcomes with data.
7. If the text is generic rhetoric with no specific action, return an empty
   evidence_items array.
8. Each evidence_text must be a verbatim or near-verbatim excerpt from
   the provided chunk text.
9. Return ONLY valid JSON — no markdown, no commentary, no explanation.
"""

EXTRACTION_USER_PROMPT_TEMPLATE: str = """Analyse the following excerpt from a company sustainability report.

--- EXCERPT START ---
Company: {company}
Report: {report_name} ({report_year})
Page: {page_number}
Section: {section_heading}

Text:
{chunk_text}
--- EXCERPT END ---

Extract all meaningful SDG evidence items from this excerpt.
Return a JSON object with this exact structure:

{{
  "evidence_items": [
    {{
      "evidence_text": "<verbatim or near-verbatim excerpt from the text above>",
      "evidence_summary": "<one sentence describing what this evidence shows>",
      "candidate_sdgs": ["SDG X", "SDG Y"],
      "evidence_tags": ["<tag1>", "<tag2>"],
      "implementation_stage": "<stage>",
      "quantitative_support": <true|false>,
      "oversight_support": <true|false>,
      "confidence": <0.0 to 1.0>,
      "rationale": "<brief explanation of SDG mapping and classification>"
    }}
  ]
}}

Allowed evidence_tags (use only these values):
  aspiration, policy, initiative, target, kpi, governance, measured_outcome

Allowed implementation_stage values (use exactly one):
  mention_only
  planned_action
  implementation_in_progress
  implemented_with_measurable_evidence

SDG format: use "SDG 1", "SDG 2", … "SDG 17" only.

If there is no meaningful SDG evidence in the excerpt, return:
{{"evidence_items": []}}

Return ONLY the JSON object. No markdown. No explanation.
"""

EXTRACTION_RETRY_PROMPT: str = """Your previous response was not valid JSON.
Please return ONLY the JSON object with the structure:
{{"evidence_items": [...]}}
No markdown, no commentary. Raw JSON only.
"""
