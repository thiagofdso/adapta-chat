import asyncio
import nest_asyncio
import streamlit as st

from generators_v2 import (
    AdaptaClientV2,
    Claude45SonnetGenerator,
    DeepseekV3Generator,
    Gemini3ProPreviewGenerator,
    GPT5Generator,
    GPT51Generator,
    Grok41Generator,
    O3Generator,
    OneProGenerator,
    Qwen3MaxGenerator,
    SonarProGenerator,
)
from utils.logger import logger

nest_asyncio.apply()

# Page configuration
st.set_page_config(page_title="Adapta.one Chat", layout="wide")


@st.cache_resource
def get_shared_client() -> AdaptaClientV2:
    """Instancia e reutiliza o cliente Adapta para todos os generators."""
    return AdaptaClientV2()


@st.cache_resource
def initialize_generators():
    """Inicializa generators v2 compartilhando um cliente."""
    client = get_shared_client()
    return {
        "Claude 4.5 Sonnet": Claude45SonnetGenerator(client=client),
        "Gemini 3 Pro Preview": Gemini3ProPreviewGenerator(client=client),
        "Grok 4.1": Grok41Generator(client=client),
        "GPT-5": GPT5Generator(client=client),
        "GPT-5.1": GPT51Generator(client=client),
        "Deepseek V3": DeepseekV3Generator(client=client),
        "Qwen3 Max": Qwen3MaxGenerator(client=client),
        "One Pro": OneProGenerator(client=client),
        "O3": O3Generator(client=client),
        "Sonar Pro": SonarProGenerator(client=client),
    }


def main():
    st.title("Adapta.one Chat Interface")

    generators = initialize_generators()

    # Sidebar
    with st.sidebar:
        st.header("Controls")
        if st.button("+ New Chat"):
            # limpa chat remoto se existir
            current_chat = st.session_state.get("current_chat_id")
            if current_chat:
                try:
                    client = get_shared_client()
                    asyncio.run(client.excluir_chat(current_chat))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Falha ao excluir chat remoto %s: %s", current_chat, exc)
            st.session_state.messages = []
            st.session_state.current_chat_id = None
            st.rerun()

        model_name = st.selectbox("Choose a model:", list(generators.keys()))

    st.session_state.messages = st.session_state.get("messages", [])
    st.session_state.current_chat_id = st.session_state.get("current_chat_id", None)

    # Display chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    user_input = st.chat_input("What is up?")
    if user_input is not None:
        prompt_to_send = user_input if user_input.strip() else "Por favor, continue gerando a sua resposta."

        st.session_state.messages.append({"role": "user", "content": prompt_to_send})
        with st.chat_message("user"):
            st.markdown(prompt_to_send)

        with st.chat_message("assistant"):
            placeholder = st.empty()
            placeholder.markdown("Thinking...")

            try:
                selected_generator = generators[model_name]

                if st.session_state.current_chat_id is None:
                    st.session_state.current_chat_id = selected_generator.generate_chat_id()

                response = asyncio.run(
                    selected_generator.call_model_with_messages(
                        st.session_state.messages,
                        chat_id=st.session_state.current_chat_id,
                    )
                )

                if response:
                    placeholder.markdown(response)
                    st.session_state.messages.append({"role": "assistant", "content": response})
                else:
                    placeholder.error("Failed to get a response from the model.")
                    st.session_state.messages.append({"role": "assistant", "content": "Failed to get a response."})

            except Exception as exc:
                error_message = f"An error occurred: {exc}"
                logger.exception("Erro ao processar mensagem no app_chat")
                placeholder.error(error_message)
                st.session_state.messages.append({"role": "assistant", "content": error_message})


if __name__ == "__main__":
    main()
