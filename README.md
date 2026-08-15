# TelecomRAG — grounded question answering over 3GPP specifications

A retrieval-augmented assistant for 3GPP telecom specifications, built so that
**every claim it makes is traceable to a clause**, and so that it **refuses
rather than guesses** when the corpus does not contain the answer.

Submitted for the Mavenir Graduate Engineer Trainee (AI/LLM Engineer, MavAI
OPS) technical assignment.

**Live demo — [https://15-206-59-248.sslip.io](https://15-206-59-248.sslip.io)**

> **On "zero hallucination".** This system does not claim zero hallucination,
> and I do not believe that is provable for a generative model over open-ended
> input. It claims something narrower and verifiable: **fail-closed and
> auditable.** Every claim carries a clause citation that a human can falsify
> in seconds, and anything unsupported becomes a refusal instead of a guess.
> The measured numbers are below, alongside the false-refusal cost of getting
> them.

---

## Results

Measured on a hand-verified benchmark: **47 answerable** questions with gold
clause references, and **25 adversarial** questions that the corpus cannot
answer. Construction method in [Evaluation](#evaluation).

| Metric | Measured | Target |
|---|---|---|
| Recall@3 (gold clause retrieved) | **91.5%** (43/47) | > 85% |
| Abstention correctness (adversarial, N=25) | **96.0%** | > 90% |
| False-refusal rate (answerable, N=47) | **2.1%** (1/47) | < 15% |
| Retrieval separation (Youden's J) | **0.939** | — |
| Answerable relevance score, median | **0.996** | — |
| Adversarial relevance score, median | **0.029** | — |
| End-to-end latency, typical | **3–6 s** | < 6 s |

### Choosing the operating point

The abstention threshold τ is **measured, not chosen**. `scripts/sweep_tau.py`
scores every benchmark question through the real retrieval path — no LLM calls,
so the sweep costs nothing and runs in about two minutes.

| τ | Answered (of 47) | False refusal | Correct abstention | Separation |
|---|---|---|---|---|
| 0.35 | 47 | 0.0% | 76.0% | 0.760 |
| 0.50 | 46 | 2.1% | 84.0% | 0.819 |
| 0.75 | 46 | 2.1% | 92.0% | 0.899 |
| **0.90** | **46** | **2.1%** | **96.0%** | **0.939** |
| 0.95 | 43 | 8.5% | 96.0% | 0.875 |

**τ = 0.90 in production.** For a service-assurance assistant a wrong answer
about alarm semantics during an outage costs a NOC engineer more than a
refusal, so the system is tuned to fail closed and the 2.1% false-refusal cost
is accepted deliberately.

### What the numbers do not cover

Stated plainly rather than left to be inferred:

- The **RUN-001 baseline** was measured on `llama-3.3-70b-versatile` before
  that model was dropped for its 1000-requests/day cap (D-027). It is not
  comparable to current output and is therefore not quoted above.
- **Ungrounded-claim rate** is instrumented (`app/verification/entailment.py`)
  and visible per response as *claims removed*, but a full post-swap benchmark
  run has not been completed. Quoting a number here without that run would be
  exactly the unsupported claim this project exists to prevent.
- Five of the 25 adversarial questions score above 0.6 on retrieval — they use
  real-looking identifiers such as an invented `TS 28.599`. Those are caught by
  citation validation and entailment verification, not by the threshold. That
  is the defence-in-depth argument, with the overlap measured rather than
  asserted.

### Ablation — what each change actually bought

| Run | Change | Recall@10 | Ungrounded ↓ | Abstain ✓ | False refuse ↓ |
|---|---|---|---|---|---|
| 001 | Baseline: fixed-size chunks, dense-only, plain prompt | | | | |
| 002 | + clause-aware chunking | | | | |
| 003 | + BM25 hybrid + RRF | | | | |
| 004 | + cross-encoder rerank | | | | |
| 005 | + per-claim citation prompt | | | | |
| 006 | + abstention gate (τ swept) | | | | |
| 007 | + entailment verifier | | | | |

Full per-run detail, including reverted experiments, in
[`docs/OUTCOMES_LOG.md`](docs/OUTCOMES_LOG.md).

---

## How it works

```
3GPP PDFs → clause-aware chunker → ┬→ bge-small embeddings → ChromaDB
                                   └→ BM25 index

query → dense + BM25 → RRF → cross-encoder rerank → τ gate ──low──→ ABSTAIN
                                                       │
                                                    generate (JSON, per-claim
                                                       │       citations)
                                          citation validation ──bad──→ ABSTAIN
                                                       │
                                          entailment verification ──all──→ ABSTAIN
                                                       │
                                        answer + surviving claims + clauses
```

Five paths end in abstention. None emit an unverified claim. Detail in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

### Why each part exists

| Component | The hallucination it prevents |
|---|---|
| Clause-aware chunking | A definition split mid-sentence, which the model then completes from memory |
| BM25 alongside embeddings | Dense retrieval misses exact identifiers — `TS 28.552`, `5QI`, `gNB-CU-UP`, `perceivedSeverity` |
| Cross-encoder reranking | Right clause retrieved but ranked outside the window the model sees |
| **Abstention gate** | The corpus has no answer — removes the *opportunity* to invent |
| Citation validation | Fabricated clause and specification numbers |
| **Entailment verification** | Retrieval was correct but the generation embellished |

---

## Corpus

Ten Rel-18 specifications, weighted toward fault management, KPIs and OAM
because that is the domain MavAI OPS operates in — TS 28.545/28.546 (fault
supervision), 28.552/28.554 (performance measurements and E2E KPIs),
28.532/28.533 (management services and architecture), 23.501/23.502 (5GS
architecture and procedures), 32.111-2 (alarm IRP), TR 21.905 (vocabulary).

Exact versions in [`docs/CORPUS_MANIFEST.md`](docs/CORPUS_MANIFEST.md).
The Release is frozen: mixing Releases makes two contradictory versions of the
same clause retrievable at once, which no retriever can resolve.

---

## Evaluation

Two datasets, deliberately separate:

- **Golden set** — answerable questions with gold clause IDs. Drafted by LLM
  from real chunks, then **every item read and corrected by hand**. Measures
  whether the system answers and cites correctly.
- **Adversarial set** — 25 hand-written unanswerable questions across five
  families: out-of-corpus, false premise, invented entity, wrong Release, and
  not-a-spec-question. Correct behaviour is refusal; any confident answer is a
  hallucination.

**The adversarial set is what makes the hallucination claim meaningful.** A
system tested only on answerable questions cannot demonstrate that it abstains.

Abstention is reported per family, because the families are caught by different
mechanisms: `invented_entity` is stopped by the relevance gate, while
`false_premise` often retrieves genuinely relevant text with a high score and
must be caught by the entailment verifier instead. A single aggregate number
would hide which mechanism is doing the work.

Judge validation: 20 verifier decisions were hand-labelled and agreement is
reported — an LLM evaluator can hallucinate too.

Method and metric definitions: [`docs/EVALUATION_PLAN.md`](docs/EVALUATION_PLAN.md).

---

## Running it

```bash
cp .env.example .env          # add your GROQ_API_KEY
make install

# 1. put spec PDFs in data/raw/  — see scripts/CORPUS.md
make inspect                   # gate G2: READ the sampled chunks
make ingest                    # build dense + BM25 indices

# 2. evaluate
make smoke                     # 15 questions, fast iteration
make eval RUN=007 NOTE="verifier on"
make sweep                     # τ operating-point sweep

# 3. serve
make api                       # FastAPI on :8000
make ui                        # Streamlit on :8501
make up                        # both, in Docker
```

Runs on CPU. No GPU required.

---

## Engineering process

The assignment is graded on understanding of the design, so the process is
documented rather than implied.

| Document | What it holds |
|---|---|
| [`docs/SDLC.md`](docs/SDLC.md) | Lifecycle model, phases, gates, and why a hybrid V-model/eval-driven spiral was chosen over waterfall or pure MLOps |
| [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md) | 12 functional, 9 non-functional, 5 explicit non-goals, each with an acceptance criterion |
| [`docs/TRACEABILITY.md`](docs/TRACEABILITY.md) | Requirement → decision → module → test → metric, both directions |
| [`docs/DECISION_LOG.md`](docs/DECISION_LOG.md) | 20 decisions with the alternatives rejected and why |
| [`docs/ERROR_LOG.md`](docs/ERROR_LOG.md) | Failures hit during the build, with root causes |
| [`docs/OUTCOMES_LOG.md`](docs/OUTCOMES_LOG.md) | Every eval run, including reverted experiments |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Component justification and known limitations |
| [`docs/REUSE_AUDIT.md`](docs/REUSE_AUDIT.md) | Build-vs-reuse analysis |

The governing rule: **the evaluation harness was built before the system was
optimised.** Without a baseline measured first, no change can be attributed and
the ablation table above would not exist.

---

---

## Live demo — running costs and teardown

The demo runs on a single EC2 instance because the pipeline keeps two PyTorch
models resident (`bge-small` for embedding, a cross-encoder for reranking).
That is the only reason it needs a long-lived host rather than a serverless
function.

| Resource | ID | Cost |
|---|---|---|
| EC2 t3.small (ap-south-1) | `i-04f8f50c5b7d0f54e` | $0.0224/hr running · $0 stopped |
| 20 GB gp3 volume | attached | ~$1.60/month, billed even when stopped |
| Elastic IP `15.206.59.248` | `eipalloc-0efd47e9d8366eca8` | free while attached to a **running** instance |
| Security group | `sg-0723163f90683e08a` | free |
| Key pair | `telecom-rag` | free |

Billing depends on the instance being *running*, not on traffic. Roughly $16
per month if left on continuously.

### Pause (keeps everything, stops compute charges)

```bash
aws ec2 stop-instances --region ap-south-1 --instance-ids i-04f8f50c5b7d0f54e
```

Disk, repository, `.env` and the built images all survive. Restart with:

```bash
aws ec2 start-instances --region ap-south-1 --instance-ids i-04f8f50c5b7d0f54e
aws ec2 wait instance-running --region ap-south-1 --instance-ids i-04f8f50c5b7d0f54e
aws ec2 describe-instances --region ap-south-1 \
  --instance-ids i-04f8f50c5b7d0f54e \
  --query "Reservations[0].Instances[0].PublicIpAddress" --output text
```

An Elastic IP (`15.206.59.248`) is attached, so the address survives a
stop/start. Note that an Elastic IP is only free while attached to a
**running** instance — a stopped instance with one attached is billed for it.

### Terminate (permanent — deletes the instance and its disk)

Run these in order. The first two are the important ones; the rest clean up
resources that would otherwise linger.

```bash
# 1. Terminate the instance (also deletes its root volume)
aws ec2 terminate-instances --region ap-south-1 --instance-ids i-04f8f50c5b7d0f54e
aws ec2 wait instance-terminated --region ap-south-1 --instance-ids i-04f8f50c5b7d0f54e
```

```bash
# 2. Release the Elastic IP, if one was allocated.
#    An unassociated Elastic IP is billed hourly - this is the single most
#    common source of a surprise charge after tearing an instance down.
aws ec2 describe-addresses --region ap-south-1 \
  --query "Addresses[].[PublicIp,AllocationId,InstanceId]" --output table
aws ec2 release-address --region ap-south-1 --allocation-id <AllocationId>
```

```bash
# 3. Delete the security group (must be done AFTER the instance is terminated,
#    or AWS refuses because the group is still in use)
aws ec2 delete-security-group --region ap-south-1 --group-name telecom-rag-sg
```

```bash
# 4. Delete the key pair
aws ec2 delete-key-pair --region ap-south-1 --key-name telecom-rag
```

```bash
# 5. Remove the billing alarm
aws cloudwatch delete-alarms --region us-east-1 --alarm-names telecom-rag-billing
```

### Verify nothing is left billing

```bash
aws ec2 describe-instances --region ap-south-1 \
  --filters "Name=instance-state-name,Values=running,stopped" \
  --query "Reservations[].Instances[].[InstanceId,State.Name]" --output table

aws ec2 describe-volumes --region ap-south-1 \
  --query "Volumes[].[VolumeId,State,Size]" --output table

aws ec2 describe-addresses --region ap-south-1 \
  --query "Addresses[].PublicIp" --output table
```

All three should return empty. **Unattached volumes and unassociated Elastic
IPs keep billing after the instance is gone** — they are not deleted
automatically, and they are the usual reason a "terminated" project still
appears on an invoice.

### Running it locally instead

Nothing about the system requires AWS. After teardown:

```bash
git clone https://github.com/uditnegi16/telecom-rag.git && cd telecom-rag
printf 'GROQ_API_KEY=gsk_...\n' > .env
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

The built index is committed to the repository (D-029), so this serves traffic
on first boot with no ingestion step.

---

## Reuse disclosure

Ingestion scaffolding, the FastAPI layer, the cross-encoder reranker, the
response cache, the prompt-injection sanitizer, the query logger, and the
Docker/CI configuration were adapted from a prior personal project
(`production-rag`).

Written new for this assignment: the 3GPP clause-aware chunker, hybrid
lexical+dense retrieval with RRF, the rate-limit-aware Groq client, the
citation validator, the claim-level entailment verifier, the abstention gate
redesign, the LangGraph answer pipeline, and both evaluation datasets.

Six defects in the reused code were found and fixed during the reuse audit;
they are documented as DEF-01…DEF-06 in
[`docs/TRACEABILITY.md`](docs/TRACEABILITY.md). Two are worth naming here
because they shaped the design:

- **DEF-01** — on an unresolvable citation the old code silently substituted
  the top-ranked chunk, returning a real passage under a fabricated citation
  and causing the grounding check to score against a passage that was never
  cited. Unresolvable citations are now a hard failure.
- **DEF-02** — the old hallucination check was bag-of-words overlap. On
  specification text this cannot distinguish a claim from its negation, since
  "shall reject" and "shall not reject" share ~95% of their tokens. Replaced
  with claim-level entailment.

---

## Limitations

Stated here rather than left to be discovered.

1. **Single-hop retrieval.** Cross-spec comparison questions need evidence from
   two clauses; the system does not decompose questions. The `cross_spec`
   category scores worst.
2. **Table extraction.** Large 3GPP measurement tables extract imperfectly from
   PDF. Affected chunks are tagged `content_type: table` so the impact is
   measurable, not silently absorbed.
3. **The verifier is itself an LLM** and can err. Judge–human agreement is
   reported for this reason.
4. **τ is tuned on this corpus** and does not transfer without re-sweeping.
5. **Two specifications is a small corpus.** Whether retrieval precision holds
   at 100 specs is untested and I would not claim it does.
6. **Follow-up references resolve against the previous turn, even if that turn
   was a refusal.** Asking a question, having it declined, then asking "what
   about for the AMF?" rewrites against the declined question rather than the
   last topic actually answered. Observed on the live deployment. A refusal
   means "I have nothing on this", so it is a poor antecedent; the rewriter
   should skip abstained turns when searching for context.
7. **Non-3GPP PDFs degrade gracefully rather than failing.** The clause-aware
   chunker looks for 3GPP's numbered hierarchy; a document without one falls
   through to fixed-window splitting, so retrieval and verification still work
   but citations lose clause-level precision and read as
   `filename_fallback_7`. The upload response says so explicitly.
8. **HTTPS via a shared DNS service.** The demo is served over TLS by Caddy,
   using a `sslip.io` hostname that resolves to the instance's Elastic IP.
   That avoided buying a domain, at the cost of an unmemorable hostname and a
   dependency on a third-party DNS service. A real domain would be a
   fifteen-minute change to the Caddyfile.

---

## Stack

Python 3.12 · PyMuPDF · `bge-small-en-v1.5` · ChromaDB · `rank_bm25` ·
`ms-marco-MiniLM-L-6-v2` cross-encoder · Groq (`llama-3.3-70b-versatile`
generation, `llama-3.1-8b-instant` verification) · LangGraph · FastAPI ·
Streamlit · Docker · pytest

Runs entirely on CPU. The LLM layer sits behind a provider interface, so the
stack can be pointed at a local model for air-gapped on-premises deployment —
which matters for operators who cannot send network telemetry to a third-party
API.
