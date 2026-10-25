
import json
import os
import re
from typing import Literal, TypedDict

from dotenv import load_dotenv
from langchain_ollama import ChatOllama
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field, ValidationError

load_dotenv()

# --------------------------------------------------
# Ollama local model configuration
# --------------------------------------------------

OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL", "http://localhost:11434"
).rstrip("/")

WRITER_MODEL = os.getenv(
    "OLLAMA_WRITER_MODEL", "qwen2.5:3b"
)
REVIEWER_MODEL = os.getenv(
    "OLLAMA_REVIEWER_MODEL", "llama3.2:3b"
)
REVISER_MODEL = os.getenv(
    "OLLAMA_REVISER_MODEL", "qwen2.5-coder:3b"
)
MAX_REVISIONS = max(0, int(os.getenv("MAX_REVISIONS", "2")))


def _build_model(model_name: str) -> ChatOllama:
    """Create a client for a locally running Ollama model."""
    return ChatOllama(
        model=model_name,
        base_url=OLLAMA_BASE_URL,
        temperature=0,
    )


def _writer_model() -> ChatOllama:
    return _build_model(WRITER_MODEL)


def _reviewer_model() -> ChatOllama:
    return _build_model(REVIEWER_MODEL)


def _reviser_model() -> ChatOllama:
    return _build_model(REVISER_MODEL)


# --------------------------------------------------
# Review schema and workflow state
# --------------------------------------------------

class Review(BaseModel):
    decision: Literal["PASS", "REVISE"] = Field(
        description="PASS if all review rules are satisfied; otherwise REVISE."
    )
    feedback: str = Field(
        description="Specific improvement feedback; empty when PASS."
    )


class State(TypedDict):
    topic: str
    draft: str
    feedback: str
    decision: str
    revision_count: int


def _content_to_text(content) -> str:
    """Normalize a model response to plain text."""
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if text:
                    parts.append(str(text))
            else:
                parts.append(str(item))
        return "\n".join(parts).strip()

    return str(content)


def _parse_review(raw_text: str) -> Review:
    """Parse and validate the reviewer's JSON decision."""
    text = raw_text.strip()
    text = re.sub(
        r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE
    )
    text = re.sub(r"\s*```$", "", text)

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        # Recover a JSON object if the model adds surrounding prose.
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise ValueError(
                f"Reviewer returned invalid JSON: {raw_text}"
            )
        payload = json.loads(match.group(0))

    try:
        review = Review.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(
            f"Reviewer returned an invalid review: {payload}"
        ) from exc

    if review.decision == "PASS":
        review.feedback = ""

    return review


# --------------------------------------------------
# Agent 1: Writer
# --------------------------------------------------

def writer(state: State):
    response = _writer_model().invoke(
        [
            (
                "system",
                "You are the WRITER agent in a self-correcting "
                "multi-agent system. Explain the topic for beginners "
                "in 120-160 words. Use simple language, one everyday "
                "analogy, and one tiny concrete example.",
            ),
            ("human", f"Explain: {state['topic']}"),
        ]
    )

    return {
        "draft": _content_to_text(response.content),
        "feedback": "",
        "decision": "",
        "revision_count": 0,
    }


# --------------------------------------------------
# Agent 2: Reviewer
# --------------------------------------------------

def reviewer(state: State):
    response = _reviewer_model().invoke(
        [
            (
                "system",
                "You are the REVIEWER agent. Check the answer using "
                "these rules:\n"
                "1. It is easy for a beginner.\n"
                "2. It contains an everyday analogy.\n"
                "3. It contains a tiny concrete example.\n"
                "4. It stays focused on the requested topic.\n"
                "If any rule fails, choose REVISE and provide "
                "specific improvement feedback.\n"
                'Return ONLY valid JSON: '
                '{"decision":"PASS","feedback":""} or '
                '{"decision":"REVISE","feedback":"specific feedback"}. '
                "Use PASS only when every rule is satisfied.",
            ),
            (
                "human",
                f"Topic: {state['topic']}\n\n"
                f"Answer:\n{state['draft']}",
            ),
        ]
    )

    review = _parse_review(_content_to_text(response.content))

    return {
        "decision": review.decision,
        "feedback": review.feedback,
    }


# --------------------------------------------------
# Agent 3: Reviser
# --------------------------------------------------

def reviser(state: State):
    response = _reviser_model().invoke(
        [
            (
                "system",
                "You are the REVISER agent. Improve the current answer "
                "using the reviewer's feedback. Keep it beginner-friendly, "
                "focused, and concise. Include an everyday analogy and "
                "a tiny concrete example. Return only the improved answer.",
            ),
            (
                "human",
                f"Topic: {state['topic']}\n\n"
                f"Current answer:\n{state['draft']}\n\n"
                f"Reviewer feedback:\n{state['feedback']}",
            ),
        ]
    )

    return {
        "draft": _content_to_text(response.content),
        "revision_count": state["revision_count"] + 1,
    }


# --------------------------------------------------
# LangGraph routing and workflow
# --------------------------------------------------

def route_after_review(state: State):
    if state["decision"] == "PASS":
        return "done"

    if state["revision_count"] >= MAX_REVISIONS:
        return "done"

    return "revise"


builder = StateGraph(State)

builder.add_node("writer", writer)
builder.add_node("reviewer", reviewer)
builder.add_node("reviser", reviser)

builder.add_edge(START, "writer")
builder.add_edge("writer", "reviewer")

builder.add_conditional_edges(
    "reviewer",
    route_after_review,
    {
        "revise": "reviser",
        "done": END,
    },
)

builder.add_edge("reviser", "reviewer")

graph = builder.compile()


# --------------------------------------------------
# Runtime information for the web UI
# --------------------------------------------------

def get_runtime_info() -> dict:
    return {
        "provider": "Ollama (Local)",
        "endpoint": OLLAMA_BASE_URL,
        "router_enabled": False,
        "router": None,
        "writer_model": WRITER_MODEL,
        "reviewer_model": REVIEWER_MODEL,
        "reviser_model": REVISER_MODEL,
        "max_revisions": MAX_REVISIONS,
    }


# --------------------------------------------------
# Run workflow and record each agent's output
# --------------------------------------------------

def run_workflow(topic: str):
    if not isinstance(topic, str) or not 2 <= len(topic.strip()) <= 300:
        raise ValueError("Topic must contain 2 to 300 characters.")

    topic = topic.strip()

    initial_state: State = {
        "topic": topic,
        "draft": "",
        "feedback": "",
        "decision": "",
        "revision_count": 0,
    }

    final_state = initial_state.copy()
    events = []

    for update in graph.stream(initial_state, stream_mode="updates"):
        for node_name, values in update.items():
            final_state.update(values)

            model_for_agent = {
                "writer": WRITER_MODEL,
                "reviewer": REVIEWER_MODEL,
                "reviser": REVISER_MODEL,
            }.get(node_name, "")

            events.append(
                {
                    "agent": node_name,
                    "draft": values.get("draft", ""),
                    "decision": values.get("decision", ""),
                    "feedback": values.get("feedback", ""),
                    "revision_count": final_state["revision_count"],
                    "provider": "Ollama (Local)",
                    "model": model_for_agent,
                }
            )

    return {
        "topic": topic,
        "events": events,
        "final_answer": final_state["draft"],
        "final_decision": final_state["decision"],
        "revision_count": final_state["revision_count"],
        **get_runtime_info(),
    }


# --------------------------------------------------
# Command-line demonstration
# --------------------------------------------------

def run_demo(topic: str):
    result = run_workflow(topic)

    print("\n=== SELF-CORRECTING MULTI-AGENT DEMO ===")
    print(f"Provider: {result['provider']}")
    print(f"Writer model: {result['writer_model']}")
    print(f"Reviewer model: {result['reviewer_model']}")
    print(f"Reviser model: {result['reviser_model']}")
    print(f"Topic: {topic}\n")

    for event in result["events"]:
        print(
            f"\n--- {event['agent'].upper()} "
            f"({event['model']}) ---"
        )

        if event["agent"] in {"writer", "reviser"}:
            print(event["draft"])
        elif event["agent"] == "reviewer":
            print("Decision:", event["decision"])
            print("Feedback:", event["feedback"] or "No changes needed")

    print("\n=== FINAL ANSWER ===")
    print(result["final_answer"])
    print(f"\nFinal decision: {result['final_decision']}")
    print(f"Revisions used: {result['revision_count']}")


if __name__ == "__main__":
    topic = input(
        "Enter a topic (example: What is an AI agent?): "
    ).strip()

    if not topic:
        topic = "What is an AI agent?"

    run_demo(topic)
