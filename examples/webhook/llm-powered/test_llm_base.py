from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda

from base.llm import AssistantChain, AssistantState, _llm_node


def test_assistant_chain_includes_system_prompt_and_profile_context() -> None:
    captured = {}

    def fake_llm(prompt_value):
        captured["messages"] = prompt_value.to_messages()
        return AIMessage(content="ok")

    assistant = AssistantChain(
        "You are a shopping copilot.",
        llm=RunnableLambda(fake_llm),
    )

    response = assistant.invoke(
        "Find me a light jacket",
        profile_context={"name": "Marta", "locale": "es"},
    )

    assert response == "ok"
    assert captured["messages"][0].content.startswith("You are a shopping copilot.")
    assert "- Name: Marta" in captured["messages"][0].content
    assert "- Locale: es" in captured["messages"][0].content
    assert captured["messages"][-1].content == "Find me a light jacket"


def test_assistant_chain_without_profile_context_keeps_base_prompt() -> None:
    captured = {}

    def fake_llm(prompt_value):
        captured["messages"] = prompt_value.to_messages()
        return AIMessage(content="ok")

    assistant = AssistantChain("Base prompt.", llm=RunnableLambda(fake_llm))
    assistant.invoke("Hello")

    assert captured["messages"][0].content == "Base prompt."


def test_graph_llm_node_includes_system_prompt_and_profile_context() -> None:
    captured = {}

    class StubLLM:
        def invoke(self, messages):
            captured["messages"] = messages
            return AIMessage(content="graph-ok")

    node = _llm_node(StubLLM(), "System behavior.")
    result = node(
        AssistantState(
            messages=[HumanMessage(content="Need help")],
            profile_context={"name": "Alex"},
        )
    )

    assert result["response_text"] == "graph-ok"
    assert captured["messages"][0].content.startswith("System behavior.")
    assert "- Name: Alex" in captured["messages"][0].content
    assert captured["messages"][-1].content == "Need help"
