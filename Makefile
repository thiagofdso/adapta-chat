SHELL := pwsh.exe
.ONESHELL:

POETRY := poetry

.PHONY: pipeline destilador app_chat app_debate

pipeline:
	$(POETRY) run python -m src.pipeline

destilador:
	$(POETRY) run python -m src.destilador

chat:
	$(POETRY) run streamlit run src/app_chat.py

debate:
	$(POETRY) run streamlit run src/app_debate.py