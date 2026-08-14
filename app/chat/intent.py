"""
Intent classification, before retrieval.

WHY THIS EXISTS (FR-15, decision D-030, ERROR_LOG E-021)
--------------------------------------------------------
A user said "Hello, hello, hello." and the system answered the PREVIOUS
question, presenting it as verified with a citation. The claims were
genuinely grounded — but the question had been fabricated by the follow-up
rewriter, which treats any short input as a reference needing resolution.

That is the most dangerous failure this system can have. Every other
hallucination control checks whether the ANSWER is supported by the sources.
None of them check whether the QUESTION was the one the user asked. A
recruiter typing "hi" would have received a confident, cited answer to
something they never asked.

The fix is to classify before doing anything else, following the pattern used
in TravelMaster: greetings and meta questions are answered directly and
never enter the retrieval pipeline.

Two design points carried over from that system:
  * Non-question turns DO NOT CONSUME QUOTA. Saying hello should not cost a
    visitor one of their eight questions.
  * Classification is rule-based first. Greetings are a small, closed set of
    phrasings; spending an LLM call to recognise "hi" would add latency and
    burn the very budget the classifier protects.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Intent(str, Enum):
    GREETING = "GREETING"            # hello, thanks, bye
    META = "META"                    # what can you do, what do you know
    SPEC_QUESTION = "SPEC_QUESTION"  # full retrieval pipeline
    FOLLOW_UP = "FOLLOW_UP"          # depends on prior turn; needs rewriting
    UNCLEAR = "UNCLEAR"              # too short/vague to act on safely
    AMBIGUOUS = "AMBIGUOUS"          # rules undecided; resolve with an LLM call


GREETING_RE = re.compile(
    r"^\s*(hi|hey|hello|yo|hola|namaste|good\s+(morning|afternoon|evening)|"
    r"thanks?|thank\s+you|thx|ty|ok(ay)?|cool|nice|great|got\s+it|"
    r"bye|goodbye|see\s+you|cheers)"
    r"[\s!.,?]*(hi|hey|hello|there|thanks?|again|everyone)?[\s!.,?]*$",
    re.I,
)

# Repeated single word: "hello hello hello", "test test", common with voice input.
REPEATED_RE = re.compile(r"^\s*(\b[\w']+\b)([\s,.!?]+\1\b)+[\s.!?]*$", re.I)

META_RE = re.compile(
    r"\b(what can you do|what do you know|who are you|what are you|"
    r"how do you work|what is this|help me|what specs?|which specs?|"
    r"what documents?|what corpus|your capabilities|what can i ask|"
    r"your name|who made you|who built you|what.s your name|call you|"
    r"how are you|are you (an? )?(ai|bot|human|real)|what model|"
    r"are you chatgpt|what do you use|how were you (built|made|trained))\b",
    re.I,
)

# Telecom vocabulary. If a question contains NONE of this and no other
# domain-looking token, it is probably not a specification question - which
# is the signal used to decide whether an LLM fallback classification is
# worth a call (E-024).
TELECOM_RE = re.compile(
    r"\b(3gpp|ts\s?\d{2}\.\d{3}|clause|spec(ification)?s?|measurement|counter|"
    r"kpis?|alarms?|gnb|amf|smf|upf|pcf|udm|nef|nrf|ausf|nssf|ue|"
    r"5g|5gs|5gc|nr|lte|ran|oam|mns|qos|5qi|pdu|drb|pdcp|rrc|"
    r"handovers?|registrations?|sessions?|subscribe|notifications?|granularity|"
    r"throughput|latency|severity|provisioning|itf-n|nrcells?|"
    r"parameters?|attributes?|fields?|values?|types?|procedures?|interfaces?|"
    r"counters?|measurements?|cells?|bearers?|slices?|networks?)\b",
    re.I,
)

# Signals a turn depends on earlier context.
DEPENDENT_RE = re.compile(
    r"^\s*(what about|how about|and (for|the|what)|what if|why|and\?|"
    r"same for|for (the )?[A-Z]{2,6}\??$)|"
    r"\b(it|its|that|those|these|they|them|this one|the same)\b",
    re.I,
)

# A real question usually has one of these.
QUESTION_SIGNAL = re.compile(
    r"\?|^\s*(what|which|how|when|where|why|who|does|do|is|are|can|"
    r"list|define|explain|describe|tell me)\b",
    re.I,
)


@dataclass
class Classification:
    intent: Intent
    reason: str
    billable: bool          # does this consume a question from the quota?


def classify(text: str, has_history: bool) -> Classification:
    t = (text or "").strip()

    if not t or len(t) < 2:
        return Classification(Intent.UNCLEAR, "empty", billable=False)

    if GREETING_RE.match(t):
        return Classification(Intent.GREETING, "greeting phrase", billable=False)

    if REPEATED_RE.match(t):
        # "hello hello hello" - almost always voice-input noise, never a
        # question. Crucially this must be caught BEFORE follow-up rewriting.
        return Classification(Intent.GREETING, "repeated token", billable=False)

    if META_RE.search(t):
        return Classification(Intent.META, "asking about the system", billable=False)

    words = t.split()

    # Short AND context-dependent -> a genuine follow-up worth rewriting.
    if has_history and len(words) <= 8 and DEPENDENT_RE.search(t):
        return Classification(Intent.FOLLOW_UP, "context-dependent", billable=True)

    # Short with no question signal and no dependency marker: do not guess.
    if len(words) <= 3 and not QUESTION_SIGNAL.search(t):
        return Classification(
            Intent.UNCLEAR, "too short to interpret safely", billable=False
        )

    # No telecom vocabulary at all and reasonably short: probably
    # conversational ("so whats your name", "do you like cricket"). Rules
    # cannot enumerate conversational English, so this is handed to a cheap
    # LLM classification (E-024). Marked AMBIGUOUS; the caller resolves it.
    if len(words) <= 12 and not TELECOM_RE.search(t):
        return Classification(
            Intent.AMBIGUOUS, "no domain vocabulary; needs LLM check",
            billable=False,
        )

    return Classification(Intent.SPEC_QUESTION, "treated as a question", billable=True)


FALLBACK_PROMPT = """Classify the user's message into exactly one category.

CONVERSATIONAL — small talk, or a question about the assistant itself: its
name, what it is, who built it, how it works, what it can do.
  Examples: "so whats your name", "how are you", "are you an AI",
            "who built this", "thanks that helped", "what else can you do"

TECHNICAL — a question about telecommunications, network specifications,
measurements, procedures or equipment, even if loosely worded.
  Examples: "how do handovers work", "what counters exist for the AMF",
            "explain granularity periods"

Message: {message}

Respond with JSON only: {{"category": "CONVERSATIONAL" or "TECHNICAL"}}"""


def resolve_ambiguous(text: str, llm=None) -> Classification:
    """Second-stage classification for input the rules could not place.

    One call on the small model, ~80 tokens. It runs only on short input with
    no domain vocabulary, so it is rare - and it prevents the alternative,
    which is answering "so whats your name" with a specification refusal that
    looks like the system is broken.

    Fails toward CONVERSATIONAL: if the classifier is unavailable, replying
    conversationally to a technical question is a mild annoyance, whereas
    refusing a greeting reads as a malfunction.
    """
    if llm is None:
        return Classification(Intent.META, "no classifier available", billable=False)

    import json
    try:
        raw = llm.complete(
            FALLBACK_PROMPT.format(message=text[:400]),
            model=None, max_tokens=40, json_mode=True,
        )
        category = str(json.loads(raw).get("category", "")).upper()
    except Exception:                              # noqa: BLE001
        return Classification(Intent.META, "classifier failed", billable=False)

    if category == "TECHNICAL":
        return Classification(Intent.SPEC_QUESTION, "LLM: technical", billable=True)
    return Classification(Intent.META, "LLM: conversational", billable=False)


# --- direct responses: no retrieval, no LLM, no quota ----------------------

def greeting_response(corpus_summary: str) -> str:
    return (
        "Hello. I answer questions about the 3GPP specifications indexed here, "
        f"and every claim I make cites the clause it came from.\n\n{corpus_summary}\n\n"
        "Ask me something like *“What is the unit of measurement for the number "
        "of failed event exposure subscribe at the PCF?”* — or attach your own "
        "specification PDF and I will index it for this conversation."
    )


def conversational_response(corpus_summary: str) -> str:
    """For small talk and questions about the assistant itself."""
    return (
        "I'm TelecomRAG — an assistant for 3GPP specifications. I don't have "
        "much to say about myself, but I'm good at finding what a specification "
        "actually says and showing you the clause it came from.\n\n"
        f"{corpus_summary}\n\n"
        "Ask me about a measurement, a counter, a procedure or a parameter — "
        "or attach your own specification PDF and I'll index it for this "
        "conversation."
    )


def meta_response(corpus_summary: str) -> str:
    return (
        "I answer questions about 3GPP telecom specifications using retrieval-"
        "augmented generation, with the emphasis on not making things up.\n\n"
        f"{corpus_summary}\n\n"
        "How it works: your question is matched against the indexed clauses "
        "using both semantic and keyword search, the best passages are reranked, "
        "and an answer is generated **only** from those passages. Every claim is "
        "then checked against the clause it cites, and anything unsupported is "
        "removed. If the evidence is insufficient I decline rather than guess — "
        "and I show you what I retrieved either way, so you can check.\n\n"
        "You can also attach a specification PDF; it is indexed for this "
        "conversation only and is not visible to anyone else."
    )


def unclear_response() -> str:
    return (
        "I did not catch a question there. Could you rephrase it?\n\n"
        "I deliberately do not guess at what you might have meant — inferring "
        "a question you did not ask is exactly the kind of confident-but-wrong "
        "behaviour this system is built to avoid."
    )
