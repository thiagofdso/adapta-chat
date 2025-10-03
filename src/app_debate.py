import streamlit as st
import asyncio
import os
from itertools import cycle
from utils.text_cleaner import remove_think_tags
from concurrent.futures import ThreadPoolExecutor
from generators.adapta import GeminiGenerator, ClaudeGenerator, GPTGenerator

def run_agent_call_sync(agent_instance, messages):
    """Wrapper to run async agent call in a new event loop."""
    return asyncio.run(agent_instance.call_model_with_messages(messages))

# --- App Configuration ---
st.set_page_config(page_title="Multi-Agent Debate Chat", layout="wide")

# --- Agent Initialization ---
@st.cache_resource
def initialize_base_generators():
    """Initializes the base generator models. This runs only once."""
    return {
        "Gemini": GeminiGenerator(),
        "Claude": ClaudeGenerator(),
        "GPT": GPTGenerator(),
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

def load_custom_prompts():
    """Loads all custom prompts from files."""
    prompts = {}
    if not os.path.exists(PROMPTS_DIR):
        return prompts
    for filename in os.listdir(PROMPTS_DIR):
        if filename.endswith(".txt"):
            agent_name = os.path.splitext(filename)[0].replace('_', ' ')
            file_path = os.path.join(PROMPTS_DIR, filename)
            with open(file_path, "r", encoding="utf-8") as f:
                prompts[agent_name] = f.read()
    return prompts

# --- Main Application Logic ---
def main():
    st.title("🤖 Multi-Agent Debate Chat")

    # Load custom prompts from files
    loaded_prompts = load_custom_prompts()

    # --- State Initialization ---
    if "agent_custom_prompts" not in st.session_state:
        st.session_state.agent_custom_prompts = loaded_prompts
    if "final_conclusion" not in st.session_state:
        st.session_state.final_conclusion = None
        
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

    base_generators = initialize_base_generators()

    # --- UI Rendering ---
    if not st.session_state.debate_started:
        # --- Setup View ---
        st.sidebar.header("Debate Setup")
        st.session_state.num_agents = st.sidebar.number_input("Number of Agents", min_value=2, max_value=10, value=3)
        st.session_state.num_rounds = st.sidebar.number_input("Number of Debate Rounds", min_value=1, max_value=10, value=3)
        
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
            with st.sidebar.expander(f"Customize Prompt for {agent_name}"):
                st.session_state.agent_custom_prompts[agent_name] = st.text_area(
                    f"Custom instructions for {agent_name}",
                    value=st.session_state.agent_custom_prompts.get(agent_name, ""),
                    key=f"prompt_{agent_name}",
                    height=150
                )
        
        st.session_state.initial_problem = st.text_area("Enter the problem or topic to be debated:", height=200)

        if st.button("Start Debate"):
            if st.session_state.initial_problem:
                # --- Save Custom Prompts ---
                for i in range(st.session_state.num_agents):
                    agent_name = f"Agent {i+1}"
                    prompt_text = st.session_state.agent_custom_prompts.get(agent_name, "")
                    save_custom_prompt(agent_name, prompt_text)
                st.success("Custom prompts saved!")

                # --- Initialize Debate State ---
                st.session_state.debate_started = True
                st.session_state.current_round = 1
                st.session_state.manager_agent = GeminiGenerator()
                
                available_models = cycle([("GPT", base_generators["GPT"]), ("Gemini", base_generators["Gemini"]), ("Claude", base_generators["Claude"])])
                st.session_state.worker_agents = {f"Agent {i+1}": next(available_models) for i in range(st.session_state.num_agents)}
                
                st.session_state.agent_memories = {name: "" for name in st.session_state.worker_agents}
                st.session_state.conversation_histories = {name: [] for name in st.session_state.worker_agents}
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
        def run_debate_round():
            previous_memories = st.session_state.agent_memories.copy()
            results = []

            with ThreadPoolExecutor(max_workers=st.session_state.num_agents) as executor:
                futures = []
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
                    
                    # Submit the agent call to the thread pool
                    future = executor.submit(
                        run_agent_call_sync, 
                        agent_instance, 
                        st.session_state.conversation_histories[agent_name]
                    )
                    futures.append(future)
                
                for future in futures:
                    try:
                        results.append(future.result())
                    except Exception as e:
                        results.append(e)
            return results

        # --- Execute the round and display results ---
        with st.spinner(f"Round {st.session_state.current_round} in progress... Agents are thinking..."):
            all_responses = run_debate_round()
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
                            manager_history
                        )
                        if final_conclusion_text:
                            st.session_state.final_conclusion = remove_think_tags(final_conclusion_text)
                        else:
                            st.session_state.final_conclusion = "The manager agent did not provide a final conclusion."
                            st.warning(st.session_state.final_conclusion)
                        
                        # --- Auto-save Results ---
                        with st.spinner("Saving results to `debate.md`..."):
                            md_content = f"# Debate Results\n\n"
                            md_content += f"## Topic\n\n{st.session_state.initial_problem}\n\n---\n\n"
                            md_content += "## Final Agent Responses\n\n"
                            for agent_name, response in st.session_state.agent_memories.items():
                                model_name = st.session_state.worker_agents[agent_name][0]
                                md_content += f"### {agent_name} ({model_name})\n\n{response}\n\n"
                            md_content += "---\n\n## Final Conclusion\n\n"
                            md_content += st.session_state.final_conclusion
                            
                            with open("debate.md", "w", encoding="utf-8") as f:
                                f.write(md_content)
                            st.success("Results successfully saved to `debate.md`!")

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
