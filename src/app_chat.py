import asyncio
from typing import Optional
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
from utils.session_guard import LogoutGuard

nest_asyncio.apply()


def _get_or_create_event_loop() -> asyncio.AbstractEventLoop:
    loop = st.session_state.get("_shared_async_loop")
    if loop is None or loop.is_closed():
        loop = asyncio.new_event_loop()
        st.session_state["_shared_async_loop"] = loop
    return loop


def run_async_task(coro):
    loop = _get_or_create_event_loop()
    return loop.run_until_complete(coro)

# Page configuration
st.set_page_config(page_title="Adapta.one Chat", layout="wide")


@st.cache_resource
def get_shared_client() -> AdaptaClientV2:
    """Instancia e reutiliza o cliente Adapta para todos os generators."""
    client = AdaptaClientV2()
    guard = LogoutGuard(client, label="app_chat")
    guard.register()
    setattr(client, "_logout_guard", guard)
    return client


def _get_logout_guard(client: AdaptaClientV2) -> Optional[LogoutGuard]:
    return getattr(client, "_logout_guard", None)


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
    if not st.session_state.get("_chat_app_initialized"):
        logger.info("Interface de chat inicializada.")
        st.session_state["_chat_app_initialized"] = True

    generators = initialize_generators()

    # Sidebar
    with st.sidebar:
        st.header("Controls")
        if st.button("+ New Chat"):
            logger.info("Usuario solicitou novo chat.")
            # limpa chat remoto se existir
            current_chat = st.session_state.get("current_chat_id")
            if current_chat:
                try:
                    client = get_shared_client()
                    run_async_task(client.excluir_chat(current_chat))
                    logger.info("Chat remoto {} excluido apos reset.", current_chat)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Falha ao excluir chat remoto {}: {}", current_chat, exc)
            st.session_state.messages = []
            st.session_state.current_chat_id = None
            st.rerun()

        if st.button("Logout Adapta"):
            client = get_shared_client()
            guard = _get_logout_guard(client)
            if guard:
                run_async_task(guard.close_now())
                logger.info("Logout manual solicitado no app_chat.")
                st.session_state.messages = []
                st.session_state.current_chat_id = None
                st.success("Sessao Adapta encerrada. Um novo login sera feito automaticamente quando necessario.")
            else:
                st.info("Cliente ainda nao inicializado; nada para finalizar.")
            st.stop()

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
        logger.info(
            "Nova mensagem recebida com {} caracteres para o modelo {}.",
            len(prompt_to_send),
            model_name,
        )

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
                    logger.info(
                        "Gerado novo chat_id {} para o modelo {}.",
                        st.session_state.current_chat_id,
                        model_name,
                    )

                response = run_async_task(
                    selected_generator.call_model_with_messages(
                        st.session_state.messages,
                        chat_id=st.session_state.current_chat_id,
                    )
                )

                if response:
                    placeholder.markdown(response)
                    st.session_state.messages.append({"role": "assistant", "content": response})
                    logger.info(
                        "Resposta do modelo {} registrada ({} caracteres).",
                        model_name,
                        len(response),
                    )
                else:
                    placeholder.error("Failed to get a response from the model.")
                    st.session_state.messages.append({"role": "assistant", "content": "Failed to get a response."})
                    logger.warning(
                        "Modelo {} nao retornou resposta para chat_id {}.",
                        model_name,
                        st.session_state.current_chat_id,
                    )

            except Exception as exc:
                error_message = f"An error occurred: {exc}"
                logger.exception("Erro ao processar mensagem no app_chat")
                placeholder.error(error_message)
                st.session_state.messages.append({"role": "assistant", "content": error_message})


if __name__ == "__main__":
    main()
