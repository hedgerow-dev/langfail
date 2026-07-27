"""AI-native detection demo functions (open-rowan epic #183), categories
that don't have a natural HTTP-route shape: guardrail enforcement (P2),
multi-agent handoff (P4), and sandbox configuration (P5). LLM-authz (P1)
lives in :mod:`langfail.api.ai_native_demo` as a real Flask route (it fits
naturally there, mirroring `authz_demo.py`); MCP authorization (P3) lives in
:mod:`langfail.core.security` alongside the existing token-verification
pair it's a sibling bug class to.

Each vulnerable/safe pair here is driveable directly (no HTTP client
needed) -- the property under test is a structural one (did the dangerous
action execute; does the sandbox config carry an escape primitive), not an
HTTP response body.
"""
from __future__ import annotations

import subprocess


# --- P2: guardrail enforcement (open-rowan #186) ----------------------------
#
# A moderation call that exists in source is not the same as a moderation
# call that's enforced -- ns-aiml-130/131/132 detect the gap between "a
# guardrail is present" and "a flagged verdict actually stops the request."


class _ModerationVerdict:
    def __init__(self, flagged: bool) -> None:
        self.flagged = flagged


def _moderate(text: str) -> _ModerationVerdict:
    """Stand-in for a real moderation-endpoint call
    (``client.moderations.create(...)``); flags any prompt containing the
    word "ignore" as a cheap stand-in for a real content-policy check."""
    return _ModerationVerdict(flagged="ignore" in text.lower())


def run_agent_command(prompt: str) -> str:
    """VULNERABLE: the moderation verdict is checked and logged, but no
    branch stops the request -- a flagged prompt still reaches the shell.
    (ns-aiml-132 / open-rowan #186)
    """
    verdict = _moderate(prompt)
    if verdict.flagged:
        print(f"[guardrail] flagged prompt: {prompt!r}")  # logged, not blocked
    return subprocess.run(prompt, shell=True, capture_output=True, text=True).stdout


def run_agent_command_safe(prompt: str) -> str:
    """SAFE: a flagged verdict raises before the shell call is ever reached."""
    verdict = _moderate(prompt)
    if verdict.flagged:
        raise ValueError("prompt blocked by content policy")
    return subprocess.run(prompt, shell=True, capture_output=True, text=True).stdout


# --- P4: multi-agent handoff (open-rowan #188) ------------------------------
#
# CrewAI's own `Task(context=[...])` handoff: a lower-privilege agent's
# output (here, one that "browses" attacker-influenceable content) reaches
# a higher-privilege agent's prompt with nothing schema-constraining it.
# AGENT-HANDOFF-001 traces the object references between Agent/Task
# constructions the same way AuthzPass resolves ownership/guard relationships.


class Agent:
    def __init__(self, role: str, tools: list | None = None) -> None:
        self.role = role
        self.tools = tools or []


class ScrapeWebsiteTool:
    pass


class CodeInterpreterTool:
    pass


class Task:
    def __init__(self, description: str, agent: Agent, context: list | None = None) -> None:
        self.description = description
        self.agent = agent
        self.context = context or []


class Crew:
    def __init__(self, agents: list, tasks: list) -> None:
        self.agents = agents
        self.tasks = tasks

    def kickoff(self):
        return [t.description for t in self.tasks]


def build_research_to_exec_crew() -> Crew:
    """VULNERABLE: the researcher's scraped output feeds the executor's
    prompt directly, and the executor holds a code-execution tool. A prompt
    injection in the scraped page steers the executor's tool call.
    (AGENT-HANDOFF-001 / open-rowan #188)
    """
    researcher = Agent(role="Researcher", tools=[ScrapeWebsiteTool()])
    executor = Agent(role="Executor", tools=[CodeInterpreterTool()])
    research_task = Task(description="scrape the target site", agent=researcher)
    exec_task = Task(
        description="run the recommended command", agent=executor,
        context=[research_task],
    )
    return Crew(agents=[researcher, executor], tasks=[research_task, exec_task])


def build_research_to_noop_crew_safe() -> Crew:
    """SAFE: the receiving agent has no privileged tool at all -- the same
    handoff shape, but nothing for a prompt injection to escalate to."""
    researcher = Agent(role="Researcher", tools=[ScrapeWebsiteTool()])
    summarizer = Agent(role="Summarizer", tools=[])
    research_task = Task(description="scrape the target site", agent=researcher)
    summary_task = Task(
        description="summarize the findings", agent=summarizer,
        context=[research_task],
    )
    return Crew(agents=[researcher, summarizer], tasks=[research_task, summary_task])


# --- P5: sandbox escape configuration (open-rowan #189) ---------------------
#
# The Docker socket bind mount is the flagship instance the epic names
# explicitly: mounting `/var/run/docker.sock` into a container an LLM agent
# can drive gives it the ability to launch new, arbitrary containers on the
# HOST engine -- full host takeover, not merely "escape this one container."


class _StubDockerContainers:
    def run(self, image: str, **kwargs):
        return {"image": image, "kwargs": kwargs}


class _StubDockerClient:
    def __init__(self) -> None:
        self.containers = _StubDockerContainers()


def docker_from_env() -> _StubDockerClient:
    return _StubDockerClient()


def start_interpreter_container_unsafe():
    """VULNERABLE: the Docker socket is bind-mounted into the interpreter
    container -- a common "let the agent spin up its own sandboxes" tutorial
    pattern that actually hands it the host's own container engine.
    (ns-aiml-140 / open-rowan #189)
    """
    client = docker_from_env()
    return client.containers.run(
        "agent-sandbox:latest",
        command="python interpreter.py",
        volumes={"/var/run/docker.sock": {"bind": "/var/run/docker.sock", "mode": "rw"}},
    )


class _E2BSandbox:
    def __init__(self, timeout: int | None = None, allow_internet: bool = True) -> None:
        self.timeout = timeout
        self.allow_internet = allow_internet

    def run_code(self, code: str) -> str:
        return f"ran: {code[:80]}"


def start_interpreter_sandbox_safe():
    """SAFE: a scoped, timeout-bound, network-isolated hosted sandbox --
    no host filesystem or Docker engine access at all."""
    return _E2BSandbox(timeout=30, allow_internet=False)
