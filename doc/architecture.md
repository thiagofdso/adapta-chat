# Project Architecture

This document provides an overview of the project's architecture, components, and file structure.

## 1. High-Level Overview

This project is a Python application designed for orchestrating conversations and debates with multiple Large Language Models (LLMs) through the Adapta.one API. It features a modular architecture that separates the API client, content generation logic, and user interfaces.

The user interacts with the system via web interfaces built with Streamlit. These interfaces use a set of "generators" to process user input and get responses from different AI models.

## 2. Core Components

### 2.1. Configuration (`src/config.py`)
- **Purpose:** Manages application settings.
- **Details:** Uses `pydantic-settings` to load sensitive information (like API cookies and session IDs) from a `.env` file, keeping credentials separate from the code.

### 2.2. API Client (`src/generators/adapta/client.py`)
- **Purpose:** Handles all communication with the Adapta.one API.
- **Details:** An asynchronous client built on `httpx`. It manages authentication, session tokens, file uploads, and provides core methods for calling the AI models. It is designed to be resilient, handling event loop issues when used with Streamlit.

### 2.3. Generator Abstraction (`src/generators/`)
- **Purpose:** To provide a consistent interface for different AI models.
- **Details:** Supports an expanded list of models including Claude Opus, Gemini, Claude, GPT, Deepseek, Grok-4, GPT-OSS, Deepseek-R1, O3, and O4-Mini.
- **`base.py`:** Defines the `BaseContentGenerator` abstract class. This class enforces a contract that all specific generator implementations must follow (e.g., must have a `call_model_with_messages` method).
- **`*_generator.py` files:** These are concrete implementations (`ClaudeOpusGenerator`, `GeminiGenerator`, `ClaudeGenerator`, `GPTGenerator`, `DeepseekGenerator`, `Grok4Generator`, `GptOssGenerator`, `DeepseekR1Generator`, `GptO3Generator`, `GptO4MiniGenerator`). They inherit from `BaseContentGenerator` and use the `AdaptaClient` to perform their tasks. This design makes it easy to add new AI models in the future.

### 2.4. User Interfaces (`src/app_*.py`)
- **Purpose:** To provide interactive web interfaces for the user.
- **Technology:** Built with Streamlit.
- **`app_chat.py`:** A simple, single-thread chat application for direct conversation with a chosen AI model. It now includes internet search capabilities (Google, Scientific, Deep Research) for enhancing AI responses.
- **`app_debate.py`:** A complex, multi-agent simulation application. It orchestrates a debate between several AI agents to collaboratively solve a problem, running the agents in parallel for each round of debate. It now features optional internet access (Google search) for all agents.

### 2.5. Knowledge Pipeline Components
- **Purpose:** To provide a multi-stage, fault-tolerant pipeline for extracting and generating knowledge from text files.
- **src/pipeline.py:** Orchestrates the three pipeline stages. It consolidates the source .txt files (limit de 400k palavras por upload), tenta gerar os patches JSON alternando entre ClaudeOpusGenerator, GPTGenerator e GeminiGenerator, e mantem um indice JSON particionado por pasta (indexes/<slug>_part_001.json, ..._part_002.json, etc.) junto com o manifesto agregado (indexes/<slug>.json). As saidas de Stage 2 sao gravadas em docs_{folder}. Cada knowledge registra a lista de arquivos (iles) e os IDs de conhecimentos relacionados (knowledge_related).
iles) e os IDs de conhecimentos relacionados (knowledge_related).
iles) e os IDs de conhecimentos relacionados (knowledge_related).
- **`src/prompt_manager.py`:** Generates the extraction prompt. When an index already exists, todos os arquivos particionados sao listados no prompt (somente pelos nomes) juntamente com regras extras (continuar o catalogo, permitir insercao de novas secoes, preservar arquivos e relacionamentos) antes de chamar o LLM.
- **src/prompt_manager.py:** Generates the extraction prompt. When an index already exists, todos os arquivos particionados sao listados no prompt (somente pelos nomes) juntamente com regras extras (continuar o catalogo, permitir insercao de novas secoes, preservar arquivos e relacionamentos) antes de chamar o LLM.
- **src/prompt_manager.py:** Generates the extraction prompt. When an index already exists, todos os arquivos particionados sao listados no prompt (somente pelos nomes) juntamente com regras extras (continuar o catalogo, permitir insercao de novas secoes, preservar arquivos e relacionamentos) antes de chamar o LLM.
- **Knowledge JSON format:** Stage 1 expects `{ "sections": [...] }`, where each section provides `section_id`, `title`, and a `knowledges` array with items `{ "id", "category", "name", "description", "files", "knowledge_related" }`. The `files` field is a list of objects `{ "name": "arquivo.ext" }`, and `knowledge_related` é um array de IDs inteiros. Legacy flat lists are still normalized; missing descriptions default to an empty string.

## 3. Project File Structure

```
.
+-- data/
¦   +-- pipeline.db              # SQLite database for the knowledge pipeline.
+-- docs/
¦   +-- architecture.md          # This document.
¦   +-- requirements.md          # Functional requirements of the project.
+-- indexes/                     # Persistent JSON indexes per processed folder.
+-- docs_{folder}/               # Generated markdown files for a given source folder.
+-- logs/
¦   +-- adapta-chat.log          # Log file generated by the application.
+-- src/
¦   +-- __init__.py
¦   +-- app_chat.py              # Streamlit UI for the simple chat.
¦   +-- app_debate.py            # Streamlit UI for the multi-agent debate.
¦   +-- config.py                # Application configuration and .env loader.
¦   +-- database.py              # Database handler for the pipeline.
¦   +-- pipeline.py              # Main orchestrator for the knowledge pipeline.
¦   +-- prompt_manager.py        # Dynamic prompt generator for the pipeline.
¦   +-- generators/
¦   ¦   +-- __init__.py
¦   ¦   +-- base.py              # Abstract base class for all generators.
¦   ¦   +-- adapta/
¦   ¦       +-- __init__.py
¦   ¦       +-- client.py        # The Adapta.one API client (plus generator wrappers).
¦   +-- prompts/
¦   ¦   +-- knowledge_creation.txt
¦   ¦   +-- knowledge_extraction.txt
¦   +-- services/
¦   ¦   +-- knowledge_service.py # Business logic for the pipeline.
¦   +-- utils/
¦       +-- __init__.py
¦       +-- logger.py            # Logging configuration using Loguru.
¦       +-- text_cleaner.py      # Utility helpers (e.g., removing think tags).
+-- .env.example                 # Example environment file.
+-- .gitignore                   # Specifies files for Git to ignore.
+-- GEMINI.md                    # Development guidelines for the Gemini agent.
+-- pyproject.toml               # Project definition and dependencies for Poetry.
+-- README.md                    # General project information and setup instructions.
+-- test_adapta_generators.py    # Test script for the generators.
```
