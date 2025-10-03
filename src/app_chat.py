import streamlit as st
import asyncio
from generators.adapta import GeminiGenerator, ClaudeGenerator, GPTGenerator

# Page configuration
st.set_page_config(page_title="Adapta.one Chat", layout="wide")

# Function to initialize generators (cached to run only once)
@st.cache_resource
def initialize_generators():
    # This function will be executed only once
    return {
        "Gemini": GeminiGenerator(),
        "Claude": ClaudeGenerator(),
        "GPT": GPTGenerator(),
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
            st.rerun()

        model_name = st.selectbox("Choose a model:", list(generators.keys()))

    # Initialize chat history in session state
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Handle user input
    if prompt := st.chat_input("What is up?"):
        # Add user message to history
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Get response from the selected generator
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            message_placeholder.markdown("Thinking...")

            try:
                # Get the selected generator
                selected_generator = generators[model_name]

                # Call the model asynchronously
                response = asyncio.run(
                    selected_generator.call_model_with_messages(st.session_state.messages)
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
