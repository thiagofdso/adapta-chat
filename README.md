# Adapta

A Python project designed to interact with the Adapta.one API for various content generation tasks. It provides a modular framework with different AI model generators.

## Features

- **Multiple AI Providers:** Easily switch between different content generators like Gemini, Claude, and GPT.
- **Content Generation:**
    - Summarize long texts.
    - Create structured diagrams from text.
    - Generate mind maps in OPML format.
- **Asynchronous Client:** Built with `httpx` for efficient, non-blocking API communication.
- **Configuration Management:** Simple setup using a `.env` file.

## Prerequisites

- Python 3.9+
- [Poetry](https://python-poetry.org/) for dependency management.

## Installation

1.  **Clone the repository:**
    ```sh
    git clone https://github.com/thiagofdso/adapta-chat.git
    cd adapta-chat
    ```

2.  **Set up the environment file:**
    Copy the example environment file and fill in your credentials.
    ```sh
    cp .env.example .env
    ```

    #### Obtaining Credentials

    To configure your `.env` file, follow these steps:

    1.  Log in to your account at [https://app.adapta.one/chats](https://app.adapta.one/chats).
    2.  Open your browser's developer tools and inspect the cookies for the `https://app.adapta.one` domain.
    3.  **For `ADAPTA_COOKIES_STR`**:
        - Find the values of the `__client` and `__client_uat` cookies.
        - Combine them into a single string, separated by a semicolon (e.g., `__client=value1;__client_uat=value2`).
    4.  **For `ADAPTA_SESSION_ID` (Optional)**:
        - Find the value of the `clerk_active_context` cookie. **Important:** You must remove the trailing colon (`:`) from the value before adding it to the `.env` file. Using this ID can reduce the number of initial API calls.

    Now, edit the `.env` file with these values.

3.  **Install dependencies:**
    Use Poetry to install the required Python packages.
    ```sh
    poetry install
    ```

## Usage

This project provides two interactive web interfaces and can also be used programmatically.

### Web Interfaces

#### Simple Chat (`app_chat.py`)

A straightforward chat interface for having a one-on-one conversation with a selected AI model.

To start this application, run:
```sh
poetry run streamlit run src/app_chat.py
```

#### Multi-Agent Debate (`app_debate.py`)

A more advanced application where you can orchestrate a debate between multiple AI agents to solve a problem.

- **Setup:** Configure the number of agents and debate rounds.
- **Debate:** Watch as agents respond in parallel, refining their solutions each round.
- **Save Results:** At the end, you can save the entire debate transcript to a `debate.md` file.

To start this application, run:
```sh
poetry run streamlit run src/app_debate.py
```

### Programmatic Usage

You can also use the generators directly in your own Python scripts. Here is a basic example:

```python
import asyncio
from src.generators.adapta import GeminiGenerator

async def main():
    # Ensure you have a valid .env file in the project root
    try:
        generator = GeminiGenerator()

        text_to_summarize = "This is a long text about the history of artificial intelligence..."

        # Generate a summary
        summary = await generator.summarize(text_to_summarize)
        print("--- Summary ---")
        print(summary)

        # Generate a diagram
        diagram = await generator.diagram(text_to_summarize)
        print("\n--- Diagram ---")
        print(diagram)

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(main())
```

## Testing

To validate the functionality of the generators and the Adapta client, you can run the provided test script. The tests are designed to check the class interfaces and methods without requiring valid API credentials.

```sh
poetry run python test_adapta_generators.py
```

```