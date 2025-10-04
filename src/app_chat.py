import streamlit as st
import asyncio
from generators.adapta import (
    GeminiGenerator, ClaudeGenerator, GPTGenerator, ClaudeOpusGenerator,
    DeepseekGenerator, Grok4Generator, GptOssGenerator, DeepseekR1Generator,
    GptO3Generator, GptO4MiniGenerator
)

# Page configuration
st.set_page_config(page_title="Adapta.one Chat", layout="wide")

# Function to initialize generators (cached to run only once)
@st.cache_resource
def initialize_generators():
    """Initializes the base generator models. This runs only once."""
    return {
        "Gemini": GeminiGenerator(),
        "Claude": ClaudeGenerator(),
        "GPT": GPTGenerator(),
        "Claude Opus": ClaudeOpusGenerator(),
        "Deepseek": DeepseekGenerator(),
        "Grok-4": Grok4Generator(),
        "GPT-OSS": GptOssGenerator(),
        "Deepseek-R1": DeepseekR1Generator(),
        "O3": GptO3Generator(),
        "O4-Mini": GptO4MiniGenerator(),
    }

# Main app logic
def main():
    st.title("Adapta.one Chat Interface")

    # Initialize generators
    generators = initialize_generators()

    # Sidebar for controls
    with st.sidebar:
        st.header("Controls")
        if st.button("+ New Chat"):
            st.session_state.messages = []
            st.session_state.current_chat_id = None # Reset chat ID
            st.rerun()

        model_name = st.selectbox("Choose a model:", list(generators.keys()))

        with st.expander("🌐 Internet Search"):
            st.write("Select a search mode to enhance the AI's response for your next message.")
            
            search_mode_options = ["Desativado", "Google", "Científica", "Deep Research"]
            
            # Determine the default selection for the selectbox
            default_search_selection = "Desativado"
            # Safely get search_option, defaulting to None if not present
            current_search_option = st.session_state.get("search_option", None)
            
            if current_search_option:
                if current_search_option == "google":
                    default_search_selection = "Google"
                elif current_search_option == "scientific":
                    default_search_selection = "Científica"
                elif current_search_option == "deep_research":
                    default_search_selection = "Deep Research"
            
            selected_search_mode = st.selectbox(
                "Choose search type:",
                search_mode_options,
                index=search_mode_options.index(default_search_selection),
                key="search_mode_selectbox"
            )
            
            # Update session state based on selectbox selection
            if selected_search_mode == "Desativado":
                st.session_state.search_option = None
            else:
                st.session_state.search_option = selected_search_mode.lower().replace(" ", "_") # Convert to internal format
    st.session_state.messages = st.session_state.get("messages", [])
    st.session_state.search_option = st.session_state.get("search_option", None)
    st.session_state.current_chat_id = st.session_state.get("current_chat_id", None)

    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Handle user input
    user_input = st.chat_input("What is up?")
    if user_input is not None: # Check if user submitted anything (even empty string)
        if user_input.strip() == "": # If submitted an empty string
            prompt_to_send = "Por favor, continue gerando a sua resposta."
        else:
            prompt_to_send = user_input
        
        # Add user message to history
        st.session_state.messages.append({"role": "user", "content": prompt_to_send})
        with st.chat_message("user"):
            st.markdown(prompt_to_send)

        # Get response from the selected generator
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            message_placeholder.markdown("Thinking...")

            try:
                # Prepare search parameters
                searchType = None
                tool = None
                if st.session_state.search_option == "google":
                    searchType = "normal"
                elif st.session_state.search_option == "scientific":
                    searchType = "scientific"
                elif st.session_state.search_option == "deep_research":
                    tool = "PERFORM_RESEARCH"
                
                # Get the selected generator
                selected_generator = generators[model_name]

                # Generate chat ID if it's a new conversation
                if st.session_state.current_chat_id is None:
                    st.session_state.current_chat_id = selected_generator.generate_chat_id()

                # Call the model asynchronously with search parameters and chat ID
                response = asyncio.run(
                    selected_generator.call_model_with_messages(
                        st.session_state.messages,
                        searchType=searchType,
                        tool=tool,
                        chat_id=st.session_state.current_chat_id
                    )
                )

                if response:
                    message_placeholder.markdown(response)
                    # Add assistant response to history
                    st.session_state.messages.append({"role": "assistant", "content": response})
                else:
                    message_placeholder.error("Failed to get a response from the model.")
                    st.session_state.messages.append({"role": "assistant", "content": "Failed to get a response."})

            except Exception as e:
                error_message = f"An error occurred: {e}"
                message_placeholder.error(error_message)
                st.session_state.messages.append({"role": "assistant", "content": error_message})


if __name__ == "__main__":
    main()
