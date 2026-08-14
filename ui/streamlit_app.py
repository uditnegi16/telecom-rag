"""
TelecomRAG — grounded 3GPP chatbot (FR-10, FR-13).

DESIGN INTENT
-------------
The UI must make GROUNDING VISIBLE. For every turn a reviewer can see the
answer, the clause each claim came from, and the retrieved source text -
enough to falsify any claim in seconds without opening a 400-page PDF.

Abstentions get the same treatment as answers. A refusal with no visible
reasoning is indistinguishable from a broken app, so the retrieved evidence
is shown either way and the user can judge whether the refusal was right.
"""

import sys
import time
from pathlib import Path

# The project root must precede ui/ on sys.path. Streamlit puts the script's
# own directory first, so a UI file named app.py would shadow the `app`
# package and `import app.chat` would resolve to the script itself
# (ERROR_LOG E-014). The file is named streamlit_app.py for that reason; this
# guard makes the import order explicit regardless of how it is launched.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

st.set_page_config(page_title="TelecomRAG — 3GPP Assistant",
                   page_icon="📡", layout="wide")


@st.cache_resource(show_spinner="Loading models…")
def load_pipeline(tau: float):
    # Streamlit re-runs this script on every interaction; without
    # cache_resource the embedder and cross-encoder reload on each message
    # (ERROR_LOG E-000e).
    from app.pipeline import get_answer_fn
    return get_answer_fn(tau=tau)


@st.cache_data(ttl=300)
def corpus_info():
    import json
    from collections import Counter
    from pathlib import Path
    p = Path("data/processed/chunks.json")
    if not p.exists():
        return None
    chunks = json.loads(p.read_text(encoding="utf-8"))
    return {"chunks": len(chunks),
            "specs": dict(Counter(f"{c['spec_id']} {c['spec_version']}" for c in chunks))}


if "session" not in st.session_state:
    from app.chat.session import Session
    st.session_state.session = Session()
    st.session_state.asked = 0

QUESTION_LIMIT = 8

with st.sidebar:
    st.title("📡 TelecomRAG")
    st.caption("Grounded question answering over 3GPP specifications.")

    used = st.session_state.asked
    st.progress(min(used / QUESTION_LIMIT, 1.0),
                text=f"{QUESTION_LIMIT - used} of {QUESTION_LIMIT} questions left")
    st.caption("This demo runs on a shared free-tier API key. "
               "Clone the repo to run without limits.")

    st.divider()
    st.subheader("Indexed corpus")
    info = corpus_info()
    if info:
        st.caption(f"{info['chunks']:,} clauses")
        for spec, n in info["specs"].items():
            st.write(f"**{spec}** · {n}")
        st.caption("Questions outside these specs are refused by design.")
    else:
        st.error("No corpus indexed.")

    st.divider()
    from app.config import CFG
    with st.expander("Settings"):
        tau = st.slider("τ — abstention threshold", 0.0, 1.0,
                        float(CFG.tau_abstain), 0.05,
                        help="Below this relevance score the system refuses "
                             "without calling the model at all.")
        st.caption(f"generation `{CFG.gen_model}`")
        st.caption(f"verification `{CFG.verify_model}`")

    if st.button("New conversation", use_container_width=True):
        from app.chat.session import Session
        st.session_state.session = Session()
        st.rerun()

    st.divider()
    st.caption("Try a follow-up like *“what about for the SMF?”* — "
               "the system rewrites it into a standalone query before "
               "retrieving, and shows you what it searched for.")


def render_evidence(res: dict):
    sources = res.get("source_chunks", [])
    if not sources:
        return
    cited = set(res.get("citations", []))
    with st.expander(f"Retrieved evidence ({len(sources)} clauses)",
                     expanded=False):
        for s in sources:
            mark = "✅ cited" if s.get("chunk_id") in cited else "— not cited"
            st.markdown(
                f"**{s.get('spec_id')} {s.get('spec_version')} · "
                f"clause {s.get('clause_id')}** · score "
                f"{s.get('reranker_score', 0):.3f} · {mark}"
            )
            st.caption(s.get("heading_path", ""))
            st.caption(f"pages {s.get('page_start')}–{s.get('page_end')} · "
                       f"`{s.get('chunk_id')}`")
            st.text((s.get("body") or "")[:1800])
            st.divider()


session = st.session_state.session

if not session.turns:
    st.markdown("### Ask about the indexed 3GPP specifications")
    st.caption(
        "Every claim carries a clause citation. When the corpus does not "
        "contain the answer, the system refuses rather than guessing — and "
        "shows you what it retrieved so you can check."
    )

for turn in session.turns:
    with st.chat_message("user" if turn.role == "user" else "assistant"):
        if turn.role == "user":
            st.write(turn.content)
        else:
            if turn.rewritten_query:
                st.caption(f"🔎 searched for: *{turn.rewritten_query}*")
            if turn.abstained:
                st.warning(turn.content)
                st.caption("Fail-closed: insufficient supporting evidence.")
            else:
                st.write(turn.content)
                if turn.citations:
                    st.caption("Sources: " +
                               " · ".join(f"`{c}`" for c in turn.citations))

prompt = st.chat_input(
    "Ask a question…"
    if st.session_state.asked < QUESTION_LIMIT
    else "Demo question limit reached",
    disabled=st.session_state.asked >= QUESTION_LIMIT,
)

if prompt:
    session.add_user(prompt)
    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        answer_fn = load_pipeline(tau)
        history = session.history()[:-1]        # exclude the message just added
        t0 = time.time()
        with st.spinner("Retrieving → generating → verifying…"):
            try:
                res = answer_fn(prompt, history=history)
            except Exception as exc:                       # noqa: BLE001
                st.error(f"Pipeline error: {exc}")
                st.stop()
        latency = time.time() - t0

        st.session_state.asked += 1
        session.add_assistant(res)

        if res.get("rewritten_query"):
            st.caption(f"🔎 searched for: *{res['rewritten_query']}*")

        if res.get("abstained"):
            st.warning(res.get("answer"))
            st.caption(f"Fail-closed · reason `{res.get('abstain_reason')}` · "
                       f"confidence {res.get('confidence', 0):.3f}")
        else:
            st.write(res.get("answer"))
            if res.get("claims"):
                st.caption("**Verified claims**")
                for c in res["claims"]:
                    st.caption(f"• {c['claim']}  →  `{c['citation']}`")

        cols = st.columns(4)
        cols[0].caption(f"confidence {res.get('confidence', 0):.3f}")
        cols[1].caption(f"claims dropped {res.get('claims_dropped', 0)}")
        cols[2].caption(f"{latency:.1f}s")
        cols[3].caption(f"{QUESTION_LIMIT - st.session_state.asked} left")

        render_evidence(res)

    st.rerun()
