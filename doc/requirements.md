# Functional Requirements

This document outlines the functional requirements of the Adapta-Chat project.

## Core System

- **FR-001: User Authentication Configuration:** The system must allow users to configure their Adapta.one credentials (cookies, session ID) via a `.env` file for API access.
- **FR-002: Multi-Model Support:** The system must support an expanded list of AI models (Gemini, Claude, GPT, Claude Opus, Deepseek, Grok-4, GPT-OSS, Deepseek-R1, O3, O4-Mini) through a common, abstract generator interface. A parallel `generators_v2` package must mirror this structure so that the newer `AdaptaClientV2` can replace the legacy client transparently.
- **FR-003: Asynchronous API Communication:** All communication with the external Adapta.one API must be handled asynchronously to ensure efficient, non-blocking operations.
- **FR-004: Response Cleaning:** Responses from Gemini-based models must be automatically processed to remove non-content tags (e.g., `<thinking>`) before being displayed to the user.

## `app_chat.py`: Simple Chat Interface

- **FR-005: Direct Chat:** The system shall provide a web interface for a user to have a direct, one-on-one conversation with an AI agent.
- **FR-006: Model Selection:** The user must be able to select the desired AI model from the expanded list (Gemini, Claude, GPT, Claude Opus, Deepseek, Grok-4, GPT-OSS, Deepseek-R1, O3, O4-Mini) within the interface.
- **FR-007: Conversation History:** The interface must display the full history of the current conversation.
- **FR-008: Chat Reset:** The user must be able to start a new chat at any time, which clears the current conversation history.
- **FR-009: Internet Search Integration:** The user must be able to select an internet search option (Google, Scientific, Deep Research) to enhance the AI's response for the next message.

## `app_debate.py`: Multi-Agent Debate Interface

- **FR-010: Debate Simulation:** The system shall provide a web interface to configure and run a debate between multiple AI agents to explore a topic or solve a problem.
- **FR-011: Debate Configuration:** The user must be able to configure the number of participating agents and the total number of debate rounds before starting.
- **FR-012: Problem Statement:** The user must provide an initial problem or topic that will be the subject of the debate.
- **FR-013: Agent Orchestration:** A primary "manager" agent (using the Gemini model) must orchestrate the debate.
- **FR-014: Cyclical Model Assignment:** The system must create the specified number of "worker" agents, assigning the available AI models (Gemini, Claude, GPT, Claude Opus, Deepseek, Grok-4, GPT-OSS, Deepseek-R1, O3, O4-Mini) to them in a cyclical manner.
- **FR-015: Parallel Execution:** Within each debate round, all worker agents must process their responses concurrently (in parallel).
- **FR-016: Contextual Refinement:** In each round after the first, every agent must receive the responses from all other agents from the previous round to use as context for refining its own solution.
- **FR-017: Synthesized Conclusion:** After the final round, the manager agent must synthesize the final responses from all worker agents into a single, comprehensive conclusion.
- **FR-018: Save Debate Results:** The user must be able to save the complete results of the debate (the initial topic, each agent's final response, and the manager's conclusion) to a local `debate.md` file.
- **FR-019: Debate Reset:** The user must be able to reset the entire debate application at any time to start a new session.
- **FR-020: Internet Access for Agents:** The user must be able to enable an internet access option (Google search) for all worker agents during the debate.

## Knowledge Pipeline (`pipeline.py`)

- **FR-021: Dual-Mode Operation:** The pipeline must operate in two modes: (1) by processing a specified input folder (`--input`) to discover and register new source files (`.txt` and `.pdf`), or (2) if no input is given, by processing items that are already pending in the database.
- **FR-022: Job Registration and State Management:** The system must use a SQLite database to create and manage the state of all processing jobs and individual knowledge items, tracking their progress through stages (e.g., indexing, generation, complete) and statuses (e.g., pending, in-progress, completed, error).
- **FR-023: Knowledge Indexing:** For each new file, the system must use the Gemini model to generate a JSON index of all granular knowledge pieces contained within the text, anexando PDFs diretamente (sem conversão local) para que o modelo processe o conteúdo original.
- **FR-024: Dynamic De-duplication:** To prevent duplicate entries, the indexing prompt must be dynamically updated with a list of all knowledges that have already been extracted from other files in the same source folder.
- **FR-029: Index Partitioning:** The knowledge index must be persisted em arquivos fracionados com no maximo 300 registros cada (indexes/<slug>_part_XXX.json) e cada parte deve ser enviada individualmente como anexo nas requisicoes de JSON Patch.
- **FR-025: Knowledge Persistence:** Each knowledge piece from the generated JSON index must be saved as a distinct record in the database with a "pending" status, linked to its parent job.
- **FR-026: Markdown Generation:** For each pending knowledge record, the system must use the Claude Opus model to generate a detailed, structured Markdown file based on a specific template.
- **FR-027: Structured File Output:** Generated Markdown files must be saved under um diretório raiz `docs_<raiz>` derivado da pasta de entrada e devem preservar a hierarquia relativa das subpastas com nomes slugificados antes do arquivo Markdown final.
- **FR-028: Job Finalization and Cleanup:** Once all knowledge items for a specific job have been successfully generated, the system must update the parent job's stage to "complete" and automatically delete any temporary JSON files created during the indexing stage.
