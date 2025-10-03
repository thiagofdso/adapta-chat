import streamlit as st
import asyncio
from itertools import cycle
from utils.text_cleaner import remove_think_tags
from generators.adapta import GeminiGenerator, ClaudeGenerator, GPTGenerator

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
def get_agent_prompt(current_round, num_rounds, agent_name, problem, other_agent_memories):
    """Constructs the prompt for a worker agent based on the current round."""
    if current_round == 1:
        return f"""You are {agent_name}, an intelligent AI agent.
        You are part of a team of agents tasked with solving the following problem:
        
        **Problem:** "{problem}" 
          This is the first round. Please provide your initial, detailed solution or opinion. Structure your thoughts clearly. Do not ask questions to the user."""

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

# --- Main Application Logic ---
def main():
    st.title("🤖 Multi-Agent Debate Chat")

    # --- State Initialization ---
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
        
        st.session_state.initial_problem = st.text_area("Enter the problem or topic to be debated:", height=200)

        if st.button("Start Debate"):
            if st.session_state.initial_problem:
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

        # --- Async function to run all agents in parallel for a round ---
        async def run_debate_round():
            tasks = []
            previous_memories = st.session_state.agent_memories.copy()

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
                task = agent_instance.call_model_with_messages(st.session_state.conversation_histories[agent_name])
                tasks.append(task)
            
            # Run all tasks concurrently
            results = await asyncio.gather(*tasks, return_exceptions=True)
            return results

        # --- Execute the round and display results ---
        with st.spinner(f"Round {st.session_state.current_round} in progress... Agents are thinking..."):
            all_responses = asyncio.run(run_debate_round())
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
            with st.spinner("Manager agent is generating the final summary..."):
                summary_prompt = get_manager_summary_prompt(st.session_state.initial_problem, st.session_state.agent_memories)
                
                manager_history = [{"role": "user", "content": summary_prompt}]
                try:
                    final_conclusion = asyncio.run(
                        st.session_state.manager_agent.call_model_with_messages(manager_history)
                    )
                    if final_conclusion:
                        final_conclusion = remove_think_tags(final_conclusion)
                        st.success("**Final Conclusion**")
                        st.markdown(final_conclusion)

                    # Add the save button
                    if st.button("Save Results to debate.md"):
                        # Construct the content
                        md_content = f"# Debate Results\n\n"
                        md_content += f"## Topic\n\n{st.session_state.initial_problem}\n\n---\n\n"
                        md_content += "## Final Agent Responses\n\n"

                        for agent_name, response in st.session_state.agent_memories.items():
                            model_name = st.session_state.worker_agents[agent_name][0]
                            md_content += f"### {agent_name} ({model_name})\n\n{response}\n\n"

                        md_content += "---\n\n## Final Conclusion\n\n"
                        md_content += final_conclusion

                        # Write to file
                        try:
                            with open("debate.md", "w", encoding="utf-8") as f:
                                f.write(md_content)
                            st.success("Results successfully saved to `debate.md`!")
                        except Exception as e:
                            st.error(f"Failed to save results: {e}")

                except Exception as e:
                    st.error(f"Could not generate final conclusion: {e}")

if __name__ == "__main__":
    main()
