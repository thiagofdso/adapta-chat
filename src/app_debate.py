import streamlit as st
import asyncio
import sys
import os
import nest_asyncio
from itertools import cycle
from utils.text_cleaner import remove_think_tags
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

# Em Windows, usar SelectorEventLoop evita bugs do Proactor com anyio/httpx.
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

nest_asyncio.apply()


def get_shared_loop():
    """Return a single event loop reused across the app to avoid httpx loop mismatch."""
    if "shared_loop" not in st.session_state:
        st.session_state.shared_loop = asyncio.new_event_loop()
    loop = st.session_state.shared_loop
    asyncio.set_event_loop(loop)
    return loop


def run_agent_call_sync(agent_instance, messages, chat_id=None):
    """Wrapper to run async agent call on the shared event loop."""
    loop = get_shared_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(agent_instance.call_model_with_messages(messages, chat_id=chat_id))

# --- App Configuration ---
st.set_page_config(page_title="Multi-Agent Debate Chat", layout="wide")

# --- Agent Initialization ---
@st.cache_resource
def get_shared_client() -> AdaptaClientV2:
    return AdaptaClientV2()


@st.cache_resource
def initialize_base_generators():
    """Initializes the base generator models (v2) sharing a single client."""
    client = get_shared_client()
    return {
        "Claude 4.5 Sonnet": Claude45SonnetGenerator(client=client),
        "Gemini 3 Pro Preview": Gemini3ProPreviewGenerator(client=client),
        "GPT-5": GPT5Generator(client=client),
        "GPT-5.1": GPT51Generator(client=client),
        "Deepseek V3": DeepseekV3Generator(client=client),
        "Grok 4.1": Grok41Generator(client=client),
        "Qwen3 Max": Qwen3MaxGenerator(client=client),
        "One Pro": OneProGenerator(client=client),
        "O3": O3Generator(client=client),
        "Sonar Pro": SonarProGenerator(client=client),
    }

# --- Helper Functions ---
def get_agent_prompt(current_round, num_rounds, agent_name, problem, other_agent_memories, custom_prompt=""):
    """Constructs the prompt for a worker agent based on the current round."""
    if current_round == 1:
        base_prompt = f"""You are {agent_name}, an intelligent AI agent. Responda sempre em português."""
        if custom_prompt:
            base_prompt += f"""\n\n--- YOUR CUSTOM INSTRUCTIONS ---\n{custom_prompt}\n--- END CUSTOM INSTRUCTIONS ---"""
        
        base_prompt += f"""\n\nYou are part of a team of agents tasked with solving the following problem:
        
        **Problem:** "{problem}" 
          This is the first round. Please provide your initial, detailed solution or opinion. Structure your thoughts clearly. Do not ask questions to the user."""
        return base_prompt

    # Format other agents' responses
    other_responses = "\n\n".join(
        f"# RESPONSE FROM {name}\n{response}"
        for name, response in other_agent_memories.items()
    )

    if current_round < num_rounds:
        prompt = f"""You are {agent_name}.
        This is round {current_round} of {num_rounds} in a debate to solve the problem: "{problem}" """
        prompt += f"\n\nHere are the responses from the other agents in the previous round:\n{other_responses}\n\n"
        prompt += "Please review and reflect on these other perspectives. Now, provide an updated and refined version of your own solution. Incorporate the best ideas and address any weaknesses pointed out."
        if current_round == num_rounds - 1:
            prompt += "\n\n**IMPORTANT:** This is the second-to-last round. Please make your response as conclusive as possible to prepare for the final summary."
        return prompt
    
    return """This is the final round. Please provide your absolute final and conclusive solution based on all previous discussions."""

def get_manager_summary_prompt(problem, final_memories):
    """Constructs the prompt for the manager to create the final summary."""
    final_responses = "\n\n".join(
        f"# FINAL RESPONSE FROM {name}\n{response}"
        for name, response in final_memories.items()
    )
    return f"""As the manager of a multi-agent debate, your team has concluded their discussion on the problem: "{problem}" """
    return f"\n\nHere are the final, conclusive responses from all agents:\n{final_responses}\n\nYour task is to synthesize all of these responses into a single, comprehensive, and well-structured final answer for the user. Provide the best possible solution based on the collaborative work of your team."""

PROMPTS_DIR = "src/prompts/agentes"

def save_custom_prompt(agent_name, prompt_text):
    """Saves a custom prompt to a file."""
    if not os.path.exists(PROMPTS_DIR):
        os.makedirs(PROMPTS_DIR)
    file_path = os.path.join(PROMPTS_DIR, f"{agent_name.replace(' ', '_')}.txt")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(prompt_text)

import json

def load_custom_prompts():
    """Loads all custom prompts from files."""
    prompts = {}
    if not os.path.exists(PROMPTS_DIR):
        return prompts

    for filename in os.listdir(PROMPTS_DIR):
        if filename.endswith(".txt"):
            agent_name = os.path.splitext(filename)[0].replace('_', ' ')
            file_path = os.path.join(PROMPTS_DIR, filename)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    prompts[agent_name] = f.read()
            except Exception as e:
                logger.error(f"Erro ao carregar prompt personalizado para {agent_name}: {e}")
                st.write(f"Error loading custom prompt for {agent_name}: {e}") # Keep this as a user-facing error
    return prompts

def save_model_config(model_config):
    """Saves the agent model configuration to models.json."""
    if not os.path.exists(PROMPTS_DIR):
        os.makedirs(PROMPTS_DIR)
    file_path = os.path.join(PROMPTS_DIR, "models.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(model_config, f, indent=4)

def load_model_config():
    """Loads the agent model configuration from models.json."""
    file_path = os.path.join(PROMPTS_DIR, "models.json")
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

# --- Main Application Logic ---
def main():
    st.title("🤖 Multi-Agent Debate Chat")

    # Load custom prompts and model config from files
    loaded_prompts = load_custom_prompts()
    loaded_model_config = load_model_config()

    # --- State Initialization ---
    if "agent_custom_prompts" not in st.session_state:
        st.session_state.agent_custom_prompts = loaded_prompts
    if "agent_selected_models" not in st.session_state:
        st.session_state.agent_selected_models = loaded_model_config
    if "final_conclusion" not in st.session_state:
        st.session_state.final_conclusion = None
    if "agent_chat_ids" not in st.session_state:
        st.session_state.agent_chat_ids = {}
    if "manager_chat_id" not in st.session_state:
        st.session_state.manager_chat_id = None
    if "auth_done" not in st.session_state:
        st.session_state.auth_done = False
    if "shared_loop" not in st.session_state:
        st.session_state.shared_loop = asyncio.new_event_loop()
        
    if "debate_started" not in st.session_state:
        st.session_state.debate_started = False
        st.session_state.num_agents = 3
        st.session_state.num_rounds = 3
        st.session_state.initial_problem = ""
        st.session_state.current_round = 0
        st.session_state.manager_agent = None
        st.session_state.worker_agents = {}
        st.session_state.agent_memories = {}
        st.session_state.conversation_histories = {}
        st.session_state.internet_access = False

    base_generators = initialize_base_generators()

    async def ensure_shared_login() -> None:
        """Garante login do client compartilhado apenas uma vez."""
        if st.session_state.auth_done:
            return
        client = get_shared_client()
        try:
            await client.simulate_login()
            st.session_state.auth_done = True
        except Exception as exc:  # noqa: BLE001
            logger.error("Falha ao autenticar client compartilhado: %s", exc)
            raise

    # --- UI Rendering ---
    if not st.session_state.debate_started:
        # --- Setup View ---
        st.sidebar.header("Debate Setup")
        st.session_state.num_agents = st.sidebar.number_input("Number of Agents", min_value=2, max_value=10, value=3)
        st.session_state.num_rounds = st.sidebar.number_input("Number of Debate Rounds", min_value=1, max_value=10, value=3)
        # internet access removido no v2
        
        # --- Custom Prompts UI ---
        st.sidebar.subheader("Customize Agent Prompts")
        # Ensure the custom prompts dict has keys for all potential agents
        for i in range(st.session_state.num_agents):
            agent_name = f"Agent {i+1}"
            if agent_name not in st.session_state.agent_custom_prompts:
                st.session_state.agent_custom_prompts[agent_name] = ""

        # Create expanders for each agent
        for i in range(st.session_state.num_agents):
            agent_name = f"Agent {i+1}"
            with st.sidebar.expander(f"Configure {agent_name}"):
                current_prompt_value = st.session_state.agent_custom_prompts.get(agent_name, "")
                st.session_state.agent_custom_prompts[agent_name] = st.text_area(
                    f"Custom instructions for {agent_name}",
                    value=current_prompt_value,
                    key=f"prompt_{agent_name}",
                    height=150
                )
                
                # Model selection for each agent
                available_model_names = list(base_generators.keys())
                default_model = st.session_state.agent_selected_models.get(agent_name, available_model_names[0] if available_model_names else "Gemini")
                
                st.session_state.agent_selected_models[agent_name] = st.selectbox(
                    f"Select Model for {agent_name}",
                    options=available_model_names,
                    index=available_model_names.index(default_model) if default_model in available_model_names else 0,
                    key=f"model_select_{agent_name}"
                )

        st.session_state.initial_problem = st.text_area(
            "Enter the problem or topic to be debated:",
            height=200,
            key="initial_problem_input_main",
        )

        if st.button("Start Debate"):
            if st.session_state.initial_problem:
                # login único antes de iniciar
                try:
                    loop = get_shared_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(ensure_shared_login())
                except Exception:
                    st.error("Falha ao autenticar. Verifique as credenciais do Adapta.")
                    return
                # --- Save Custom Prompts and Model Config ---
                current_model_config = {}
                for i in range(st.session_state.num_agents):
                    agent_name = f"Agent {i+1}"
                    prompt_text = st.session_state.agent_custom_prompts.get(agent_name, "")
                    if prompt_text:
                        save_custom_prompt(agent_name, prompt_text)
                    current_model_config[agent_name] = st.session_state.agent_selected_models.get(agent_name, "Gemini") # Default to Gemini if not set
                save_model_config(current_model_config)
                st.success("Custom prompts and model configurations saved!")

                # --- Initialize Debate State ---
                st.session_state.debate_started = True
                st.session_state.current_round = 1
                st.session_state.manager_agent = Gemini3ProPreviewGenerator(client=get_shared_client())  # Manager with v2
                
                # Assign models to worker agents based on selection or rotation
                st.session_state.worker_agents = {}
                available_models = cycle([
                    ("Claude 4.5 Sonnet", base_generators["Claude 4.5 Sonnet"]),
                    ("Gemini 3 Pro Preview", base_generators["Gemini 3 Pro Preview"]),
                    ("GPT-5", base_generators["GPT-5"]),
                    ("GPT-5.1", base_generators["GPT-5.1"]),
                    ("Deepseek V3", base_generators["Deepseek V3"]),
                    ("Grok 4.1", base_generators["Grok 4.1"]),
                    ("Qwen3 Max", base_generators["Qwen3 Max"]),
                    ("One Pro", base_generators["One Pro"]),
                    ("O3", base_generators["O3"]),
                    ("Sonar Pro", base_generators["Sonar Pro"]),
                ])
                for i in range(st.session_state.num_agents):
                    agent_name = f"Agent {i+1}"
                    selected_model_name = st.session_state.agent_selected_models.get(agent_name)
                    
                    if selected_model_name and selected_model_name in base_generators:
                        st.session_state.worker_agents[agent_name] = (selected_model_name, base_generators[selected_model_name])
                    else:
                        # Fallback to rotating if no selection or invalid selection
                        st.session_state.worker_agents[agent_name] = next(available_models)
                
                st.session_state.agent_memories = {name: "" for name in st.session_state.worker_agents}
                st.session_state.conversation_histories = {name: [] for name in st.session_state.worker_agents}
                st.session_state.agent_chat_ids = {
                    name: agent_instance.generate_chat_id() if hasattr(agent_instance, "generate_chat_id") else None
                    for name, (_, agent_instance) in st.session_state.worker_agents.items()
                }
                st.session_state.manager_chat_id = (
                    st.session_state.manager_agent.generate_chat_id()
                    if hasattr(st.session_state.manager_agent, "generate_chat_id")
                    else None
                )
                st.rerun()
            else:
                st.warning("Please enter a problem or topic.")
    else:
        # --- Debate View ---
        st.sidebar.header("Debate in Progress")
        st.sidebar.write(f"**Topic:** {st.session_state.initial_problem}")
        st.sidebar.write(f"**Agents:** {st.session_state.num_agents}")
        st.sidebar.write(f"**Rounds:** {st.session_state.num_rounds}")
        st.sidebar.write(f"**Current Round:** {st.session_state.current_round}")

        if st.sidebar.button("+ Chat"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

        st.subheader(f"Round {st.session_state.current_round} of {st.session_state.num_rounds}")

        # --- Function to run all agents in parallel for a round ---
        async def run_debate_round():
            tasks = []
            previous_memories = st.session_state.agent_memories.copy()

            await ensure_shared_login()

            for agent_name, (model_name, agent_instance) in st.session_state.worker_agents.items():
                other_agents_memories = {name: mem for name, mem in previous_memories.items() if name != agent_name}
                
                prompt = get_agent_prompt(
                    st.session_state.current_round,
                    st.session_state.num_rounds,
                    agent_name,
                    st.session_state.initial_problem,
                    other_agents_memories
                )
                
                # Append the new user prompt to the agent's history
                st.session_state.conversation_histories[agent_name].append({"role": "user", "content": prompt})
                
                # Create a coroutine for the API call
                task = agent_instance.call_model_with_messages(
                    st.session_state.conversation_histories[agent_name],
                    chat_id=st.session_state.agent_chat_ids.get(agent_name),
                )
                tasks.append(task)
            
            # Gather results from all tasks
            results = await asyncio.gather(*tasks, return_exceptions=True)
            return results

        # --- Execute the round and display results ---
        with st.spinner(f"Round {st.session_state.current_round} in progress... Agents are thinking..."):
            loop = get_shared_loop()
            asyncio.set_event_loop(loop)
            all_responses = loop.run_until_complete(run_debate_round())
        agent_columns = st.columns(st.session_state.num_agents)

        for i, (agent_name, response) in enumerate(zip(st.session_state.worker_agents.keys(), all_responses)):
            with agent_columns[i]:
                model_name = st.session_state.worker_agents[agent_name][0]
                st.info(f"**{agent_name} ({model_name})**")

                if isinstance(response, Exception):
                    error_message = f"Error for {agent_name}: {response}"
                    st.error(error_message)
                    st.session_state.agent_memories[agent_name] = error_message
                elif response:
                    model_name = st.session_state.worker_agents[agent_name][0]
                    if model_name == "Gemini":
                        response = remove_think_tags(response)
                    st.markdown(response)
                    st.session_state.agent_memories[agent_name] = response
                    # Append the assistant's response to the history for the next round
                    st.session_state.conversation_histories[agent_name].append({"role": "assistant", "content": response})
                else:
                    error_message = f"{agent_name} returned an empty response."
                    st.warning(error_message)
                    st.session_state.agent_memories[agent_name] = error_message

        st.success(f"Round {st.session_state.current_round} complete.")

        # --- Round Progression and Conclusion ---
        if st.session_state.current_round < st.session_state.num_rounds:
            if st.button("Continue to Next Round"):
                st.session_state.current_round += 1
                st.rerun()
        else:
            st.subheader("Final Conclusion")

            # --- Generate and Save Conclusion if it doesn't exist ---
            if st.session_state.final_conclusion is None:
                with st.spinner("Manager agent is generating the final summary..."):
                    summary_prompt = get_manager_summary_prompt(st.session_state.initial_problem, st.session_state.agent_memories)
                    manager_history = [{"role": "user", "content": summary_prompt}]
                    try:
                        final_conclusion_text = run_agent_call_sync(
                            st.session_state.manager_agent,
                            manager_history,
                            chat_id=st.session_state.manager_chat_id,
                        )
                        if final_conclusion_text:
                            st.session_state.final_conclusion = remove_think_tags(final_conclusion_text)
                        else:
                            st.session_state.final_conclusion = "The manager agent did not provide a final conclusion."
                            st.warning(st.session_state.final_conclusion)
                        
                        # --- Auto-save Results ---
                        with st.spinner("Saving results to `debate.md`..."):
                            md_content = "# Debate Results\n\n"
                            md_content += f"## Topic\n\n{st.session_state.initial_problem}\n\n---\n\n"

                            md_content += "## Agent Conversation Histories\n\n"
                            for agent_name, history in st.session_state.conversation_histories.items():
                                model_name = st.session_state.worker_agents.get(agent_name, ('Desconhecido',))[0]
                                md_content += f"### {agent_name} ({model_name})\n\n"
                                for idx, message in enumerate(history, start=1):
                                    role = message.get('role', 'unknown').capitalize()
                                    content = message.get('content', '')
                                    md_content += f"{idx:02d}. **{role}**\n\n{content}\n\n"

                            md_content += "---\n\n## Final Agent Responses\n\n"
                            for agent_name, response in st.session_state.agent_memories.items():
                                model_name = st.session_state.worker_agents[agent_name][0]
                                md_content += f"### {agent_name} ({model_name})\n\n{response}\n\n"

                            md_content += "---\n\n## Final Conclusion\n\n"
                            md_content += st.session_state.final_conclusion
                            
                            with open("debate.md", "w", encoding="utf-8") as f:
                                f.write(md_content)
                            st.success("Results successfully saved to `debate.md`!")
                            # Limpeza de chats remotos
                            try:
                                client = get_shared_client()
                                ids_para_remover = list(st.session_state.agent_chat_ids.values()) + [st.session_state.manager_chat_id]
                                ids_para_remover = [cid for cid in ids_para_remover if cid]
                                if ids_para_remover:
                                    loop = get_shared_loop()
                                    asyncio.set_event_loop(loop)
                                    loop.run_until_complete(client.excluir_chat(ids_para_remover))
                                    logger.info("Chats removidos ao final do debate: %s", ids_para_remover)
                                st.session_state.agent_chat_ids = {}
                                st.session_state.manager_chat_id = None
                            except Exception as exc:  # noqa: BLE001
                                logger.warning("Falha ao remover chats ao final do debate: %s", exc)

                    except Exception as e:
                        error_msg = f"Could not generate or save final conclusion: {e}"
                        st.session_state.final_conclusion = error_msg
                        st.error(error_msg)

            # --- Display the final conclusion from session state ---
            if st.session_state.final_conclusion:
                st.success("**Final Conclusion**")
                st.markdown(st.session_state.final_conclusion)

if __name__ == "__main__":
    main()
