.PHONY: install ingest eval smoke api ui test docker up clean

install:
	pip install -r requirements.txt

ingest:          ## Parse + chunk + index the corpus. Run once per corpus change.
	python -m scripts.ingest

inspect:         ## Gate G2: print chunk stats and 10 samples. DO THIS before indexing.
	python -m scripts.inspect_chunks

golden:          ## Draft golden-set candidates for hand verification (D-012).
	python -m scripts.build_golden_set

smoke:           ## Fast 15-question run for iteration under the Groq token budget.
	python -m eval.run_eval --run-id smoke --smoke --note "iteration"

eval:            ## Full run. Use at phase gates only.
	python -m eval.run_eval --run-id $(RUN) --note "$(NOTE)"

sweep:           ## Gate G6: tau sweep for the abstention operating point.
	for t in 0.1 0.2 0.3 0.4 0.5 0.6; do \
		python -m eval.run_eval --run-id 006-t$$t --tau $$t --note "tau sweep"; \
	done

api:
	uvicorn app.api.main:app --reload --port 8000

ui:
	streamlit run ui/streamlit_app.py

test:
	pytest -q

up:
	docker compose up --build

clean:
	rm -rf data/processed/chroma data/processed/llm_cache data/processed/bm25.pkl
