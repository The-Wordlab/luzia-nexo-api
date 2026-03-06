"""LangChain/LangGraph setup for LLM-powered webhook examples.

Provides a reusable chain/graph that can be customized per assistant type.
"""

import os
from typing import Any
from dataclasses import dataclass, field

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode


@dataclass
class LLMConfig:
    """Configuration for LLM client."""
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    api_key: str | None = None
    base_url: str | None = None


@dataclass
class AssistantState:
    """LangGraph state for the assistant conversation."""
    messages: list[Any] = field(default_factory=list)
    profile_context: dict[str, Any] = field(default_factory=dict)
    response_text: str = ""
    cards: list[dict[str, Any]] = field(default_factory=list)


def create_llm(config: LLMConfig | None = None) -> ChatOpenAI:
    """Create an LLM client with sensible defaults."""
    config = config or LLMConfig()
    
    api_key = config.api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("LITELLM_API_KEY")
    if not api_key:
        raise ValueError("No API key provided. Set OPENAI_API_KEY or LITELLM_API_KEY env var.")
    
    return ChatOpenAI(
        model=config.model,
        temperature=config.temperature,
        api_key=api_key,
        base_url=config.base_url,
    )


def build_basic_chain(
    system_prompt: str,
    llm: ChatOpenAI | None = None,
) -> Any:
    """Build a simple LLM chain with system prompt and message history.
    
    This is the simplest pattern - just an LLM with a system prompt.
    For more complex scenarios, use build_graph() instead.
    """
    llm = llm or create_llm()
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "{system_prompt}{profile_context}"),
        MessagesPlaceholder(variable_name="messages", optional=True),
    ])
    
    return prompt.partial(system_prompt=system_prompt) | llm


def build_graph(
    system_prompt: str,
    llm: ChatOpenAI | None = None,
    tools: list[Any] | None = None,
) -> StateGraph:
    """Build a LangGraph for more complex scenarios.
    
    Supports:
    - System prompt with context injection
    - Tool calling
    - Conditional routing
    
    Args:
        system_prompt: Base system prompt (profile context will be injected)
        llm: LLM client (creates default if not provided)
        tools: Optional list of LangChain tools
    
    Returns:
        Compiled LangGraph StateGraph
    """
    llm = llm or create_llm()
    
    # Bind tools if provided
    if tools:
        llm_with_tools = llm.bind_tools(tools)
    else:
        llm_with_tools = llm
    
    # Define the graph
    workflow = StateGraph(AssistantState)
    
    # Add nodes
    workflow.add_node("llm", _llm_node(llm_with_tools, system_prompt))
    if tools:
        workflow.add_node("tools", ToolNode(tools))
    
    # Set entry point
    workflow.set_entry_point("llm")
    
    # Add conditional edges
    if tools:
        workflow.add_conditional_edges(
            "llm",
            _should_use_tools,
            {
                "tools": "tools",
                "respond": END,
            }
        )
        workflow.add_edge("tools", "llm")
    else:
        workflow.add_edge("llm", END)
    
    return workflow.compile()


def _llm_node(llm: Any, system_prompt: str):
    """Create an LLM node that generates response."""
    def node(state: AssistantState) -> dict[str, Any]:
        # Build messages with system prompt + profile context
        system_with_context = _compose_system_prompt(
            system_prompt,
            state.profile_context,
        )
        
        # Get prior messages
        prior_messages = state.messages[:-1] if state.messages else []
        
        # Call LLM
        response = llm.invoke([
            SystemMessage(content=system_with_context),
            *prior_messages,
            state.messages[-1] if state.messages else HumanMessage(content=""),
        ])
        
        return {
            "messages": [response],
            "response_text": response.content,
        }
    return node


def _should_use_tools(state: AssistantState) -> str:
    """Decide whether to use tools or respond directly."""
    last_message = state.messages[-1] if state.messages else None
    if last_message and hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return "respond"


def _inject_profile_context(profile_context: dict[str, Any]) -> str:
    """Inject profile context into system prompt."""
    if not profile_context:
        return ""
    
    context_parts = ["\n\n## User Profile Context"]
    
    if name := profile_context.get("name"):
        context_parts.append(f"- Name: {name}")
    if locale := profile_context.get("locale"):
        context_parts.append(f"- Locale: {locale}")
    if facts := profile_context.get("facts"):
        context_parts.append(f"- Facts: {facts}")
    if preferences := profile_context.get("preferences"):
        context_parts.append(f"- Preferences: {preferences}")
    
    return "\n".join(context_parts)


def _compose_system_prompt(
    system_prompt: str,
    profile_context: dict[str, Any],
) -> str:
    """Compose system prompt with optional profile context."""
    return f"{system_prompt}{_inject_profile_context(profile_context)}"


class AssistantChain:
    """Simple chain-based assistant for straightforward scenarios.
    
    Use this for most webhooks. Use LangGraph for complex scenarios
    with tools, multiple agents, or complex routing.
    """
    
    def __init__(self, system_prompt: str, llm: ChatOpenAI | None = None):
        self.chain = build_basic_chain(system_prompt, llm)
        self.messages: list[Any] = []
    
    def reset(self) -> None:
        """Clear conversation history."""
        self.messages = []
    
    def invoke(
        self,
        user_message: str,
        profile_context: dict[str, Any] | None = None,
    ) -> str:
        """Invoke the chain with a user message."""
        # Add user message to history
        self.messages.append(HumanMessage(content=user_message))
        
        # Invoke chain
        response = self.chain.invoke({
            "messages": self.messages,
            "profile_context": _inject_profile_context(profile_context or {}),
        })
        
        # Add assistant response to history
        self.messages.append(response)
        
        return response.content


class AssistantGraph:
    """Graph-based assistant for complex scenarios."""
    
    def __init__(self, system_prompt: str, llm: ChatOpenAI | None = None, tools: list[Any] | None = None):
        self.graph = build_graph(system_prompt, llm, tools)
        self.llm = llm
    
    def reset(self) -> None:
        """Clear conversation state."""
        pass  # Graph doesn't hold state
    
    def invoke(
        self,
        user_message: str,
        profile_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Invoke the graph with a user message."""
        initial_state = AssistantState(
            messages=[HumanMessage(content=user_message)],
            profile_context=profile_context or {},
        )
        
        result = self.graph.invoke(initial_state)
        
        return {
            "response_text": result.get("response_text", ""),
            "cards": result.get("cards", []),
        }
