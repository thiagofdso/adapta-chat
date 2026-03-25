SHELL := pwsh.exe
.ONESHELL:

POETRY := poetry

.PHONY: pipeline destilador app_chat app_debate micro-teste1 micro-teste2

pipeline:
	$(POETRY) run python -m src.pipeline

destilador:
	$(POETRY) run python -m src.destilador

chat:
	$(POETRY) run streamlit run src/app_chat.py

debate:
	$(POETRY) run streamlit run src/app_debate.py --server.port 8502

micro-teste1:
	$(POETRY) run python prompt_tests_microaprendizado.py

micro-teste2:
	$(POETRY) run python prompt_tests_microaprendizado_variants.py
