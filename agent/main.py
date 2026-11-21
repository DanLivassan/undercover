"""The UnderCover Agent."""

import os

import httpx
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from agent.api import request
from agent.tools import claim_tools

load_dotenv()

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openai/gpt-6-luna"


def model() -> ChatOpenAI:
    """Return MODEL_NAME when set, otherwise GPT-6 Luna with low reasoning effort."""
    name = os.getenv("MODEL_NAME")
    return ChatOpenAI(
        model=name or DEFAULT_MODEL,
        base_url=OPENROUTER_BASE_URL,
        api_key=SecretStr(os.environ["OPENROUTER_API_KEY"]),
        reasoning_effort=None if name else "low",
    )


def run(claim_id: str, thread_id: str, llm: BaseChatModel | None = None) -> str:
    """Review one claim through the backend API and return the agent's summary."""
    base = f"/api/claims/{claim_id}"
    request("POST", f"{base}/start", {"thread_id": thread_id})
    try:
        instructions = request("GET", "/api/agent/instructions")["text"]
        agent = create_agent(
            llm or model(),
            tools=claim_tools(claim_id, thread_id),
            system_prompt=instructions,
        )
        result = agent.invoke(
            {"messages": [{"role": "user", "content": f"Review claim {claim_id}."}]},
            config={"configurable": {"thread_id": thread_id}, "recursion_limit": 50},
        )
        claim = request("GET", base)
        if not claim["decision"] or claim["status"] == "in_progress":
            raise RuntimeError(
                "The agent stopped before completing the claim workflow."
            )
        return result["messages"][-1].text
    except Exception as error:
        try:
            request(
                "POST",
                f"{base}/failure",
                {
                    "thread_id": thread_id,
                    "content": f"{type(error).__name__}: {error}",
                },
            )
        except httpx.HTTPError as reporting_error:
            error.add_note(f"Could not record the failure: {reporting_error}")
        raise
