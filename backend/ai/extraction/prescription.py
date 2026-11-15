"""Prescription photo -> DRAFT medication list (vision model + strict validation).

What this module guarantees (docs/rule.md):
  * The model only READS the image. Its output is a draft: nothing here resolves, confirms or analyses anything.
  * The raw model text is never stored. Only a validated, whitelisted, length-capped, PII-redacted draft leaves
    this module (`parse_model_output`), so a patient name the model copied by mistake does not reach the database.
  * Anything that is not the expected JSON shape fails with a clear `ExtractionError(code)` instead of guessing.
  * No model name, key or URL lives here: the call goes through ai/llm/router.py (`vision_complete`).

Limits (say them in the pitch): handwriting is hard; the human confirmation step exists for exactly that reason.
"""
import json
import re
from dataclasses import dataclass, field

from django.conf import settings

from ..guardrails.pii import redact
from ..llm.router import vision_complete

MAX_DRAFTS = 30
MAX_LEN = {"raw_text": 200, "brand_name": 120, "strength": 40, "frequency": 60}
LEGIBILITY = {"clear", "partial", "poor"}

SYSTEM_PROMPT = (
    "You read photographs of medical prescriptions for a medication-safety tool used by clinicians in Bangladesh. "
    "You only transcribe. You never give medical advice, never suggest doses, never correct or guess a medicine name."
)

USER_PROMPT = """Read this prescription image and list ONLY the medicines written on it.

Rules:
- Copy each medicine name exactly as written, in the original script and spelling. Do not correct it. Do not translate it.
- Do not guess. If a word is unreadable, write only what you can see and set "legibility" to "partial" or "poor".
- Ignore everything that is not a medicine line: patient name, doctor name, age, address, phone, registration or ID
  numbers, dates, hospital name, diagnosis, advice. Never copy them into the output.
- "strength" is the strength as written (for example "500 mg"), or "" if not written.
- "frequency" is the schedule exactly as written (for example "1+0+1"), or "" if not written. Do not interpret it.
- If the image is not a prescription, return "is_prescription": false and an empty list.

Return ONLY one JSON object, no other text, in exactly this shape:
{"is_prescription": true, "legibility": "clear" | "partial" | "poor",
 "medications": [{"raw_text": "<the whole line as written>", "brand_name": "<medicine name as written>",
                  "strength": "", "frequency": ""}]}"""


class ExtractionError(Exception):
    """A scan that cannot become a draft list. `code` is a stable machine code stored on the scan."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass
class ExtractionResult:
    drafts: list[dict] = field(default_factory=list)
    legibility: str = "unknown"
    truncated: bool = False
    redactions: dict = field(default_factory=dict)  # label -> count only, never the redacted text
    provider: str = ""  # cloud | local
    model: str = ""


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")


def _clean(value, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    text = re.sub(r"\s+", " ", _CONTROL.sub(" ", value)).strip()
    return text[:limit]


def _load_json(text: str) -> dict:
    body = _FENCE.sub("", (text or "").strip())
    start, end = body.find("{"), body.rfind("}")
    if start == -1 or end <= start:
        raise ExtractionError("invalid_model_output")
    try:
        data = json.loads(body[start : end + 1])
    except ValueError as exc:
        raise ExtractionError("invalid_model_output") from exc
    if not isinstance(data, dict):
        raise ExtractionError("invalid_model_output")
    return data


def parse_model_output(text: str) -> ExtractionResult:
    """Pure function: model text -> validated draft. Everything the model returns is untrusted input."""
    data = _load_json(text)
    if data.get("is_prescription") is False:
        raise ExtractionError("not_a_prescription")
    items = data.get("medications")
    if not isinstance(items, list):
        raise ExtractionError("invalid_model_output")

    result = ExtractionResult(legibility=data.get("legibility") if data.get("legibility") in LEGIBILITY else "unknown")
    for item in items:
        if not isinstance(item, dict):
            continue
        draft = {key: _clean(item.get(key), limit) for key, limit in MAX_LEN.items()}
        if not draft["raw_text"]:
            draft["raw_text"] = draft["brand_name"]
        if not draft["raw_text"]:
            continue
        found_pii = False
        for key in ("raw_text", "brand_name"):  # defence in depth: a name/phone the model copied is removed here
            cleaned = redact(draft[key])
            draft[key] = cleaned.text
            found_pii = found_pii or bool(cleaned.counts)
            for label, n in cleaned.counts.items():
                result.redactions[label] = result.redactions.get(label, 0) + n
        if found_pii and not draft["brand_name"]:
            continue  # a line that was personal data, not a medicine: dropped instead of becoming a junk row
        if len(result.drafts) >= MAX_DRAFTS:
            result.truncated = True
            break
        result.drafts.append(draft)

    if not result.drafts:
        raise ExtractionError("no_medications_found")
    return result


def extract_from_image(image: bytes, media_type: str) -> ExtractionResult:
    """Send the image to the vision model (cloud, or local Ollama when configured) and validate what comes back."""
    reply = vision_complete(USER_PROMPT, image=image, media_type=media_type, system=SYSTEM_PROMPT, max_tokens=1500)
    result = parse_model_output(reply.text)
    result.provider = reply.provider
    result.model = reply.model
    return result