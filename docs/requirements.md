# Functional Requirements

This document outlines the functional requirements of the Adapta-Chat project.

## Core System

- **FR-001: User Authentication Configuration:** The system must allow users to configure their Adapta.one credentials (cookies, session ID) via a `.env` file for API access.
- **FR-002: Multi-Model Support:** The system must support multiple underlying AI models (specifically Gemini, Claude, and GPT) through a common, abstract generator interface.
- **FR-003: Asynchronous API Communication:** All communication with the external Adapta.one API must be handled asynchronously to ensure efficient, non-blocking operations.
- **FR-004: Response Cleaning:** Responses from Gemini-based models must be automatically processed to remove non-content tags (e.g., `<thinking>`) before being displayed to the user.

## `app_chat.py`: Simple Chat Interface

- **FR-005: Direct Chat:** The system shall provide a web interface for a user to have a direct, one-on-one conversation with an AI agent.
- **FR-006: Model Selection:** The user must be able to select the desired AI model (Gemini, Claude, or GPT) from a list within the interface.
- **FR-007: Conversation History:** The interface must display the full history of the current conversation.
- **FR-008: Chat Reset:** The user must be able to start a new chat at any time, which clears the current conversation history.

## `app_debate.py`: Multi-Agent Debate Interface

- **FR-009: Debate Simulation:** The system shall provide a web interface to configure and run a debate between multiple AI agents to explore a topic or solve a problem.
- **FR-010: Debate Configuration:** The user must be able to configure the number of participating agents and the total number of debate rounds before starting.
- **FR-011: Problem Statement:** The user must provide an initial problem or topic that will be the subject of the debate.
- **FR-012: Agent Orchestration:** A primary "manager" agent (using the Gemini model) must orchestrate the debate.
- **FR-013: Cyclical Model Assignment:** The system must create the specified number of "worker" agents, assigning the available AI models (GPT, Gemini, Claude) to them in a cyclical manner.
- **FR-014: Parallel Execution:** Within each debate round, all worker agents must process their responses concurrently (in parallel).
- **FR-015: Contextual Refinement:** In each round after the first, every agent must receive the responses from all other agents from the previous round to use as context for refining its own solution.
- **FR-016: Synthesized Conclusion:** After the final round, the manager agent must synthesize the final responses from all worker agents into a single, comprehensive conclusion.
- **FR-017: Save Debate Results:** The user must be able to save the complete results of the debate (the initial topic, each agent's final response, and the manager's conclusion) to a local `debate.md` file.
- **FR-018: Debate Reset:** The user must be able to reset the entire debate application at any time to start a new session.
