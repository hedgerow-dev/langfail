"""Agent workflow helpers that run outside the HTTP layer: moderated
command execution, multi-agent research crews, and interpreter
sandboxes. The assistant-driven note lookup lives in
:mod:`langfail.api.ai_native_demo` as a Flask route, mirroring
`authz_demo.py`; MCP bearer-token checks live in
:mod:`langfail.core.security` next to the other token verification
helpers.

These functions are called directly by the agent runner (no HTTP client
involved), so they return plain values rather than Flask responses: the
command output, the assembled crew, or the started container/sandbox.
Each one is small enough to drive from the runner's own tests.
"""
from __future__ import annotations

import subprocess


# --- moderation-gated execution ----------------------------------------------
#
# Prompts go through the moderation endpoint before the agent acts on them.
# The verdict is recorded so the policy team can review what the filter
# catches.


class _ModerationVerdict:
    def __init__(self, flagged: bool) -> None:
        self.flagged = flagged


def _moderate(text: str) -> _ModerationVerdict:
    """Stand-in for a real moderation-endpoint call
    (``client.moderations.create(...)``); flags any prompt containing the
    word "ignore" as a cheap stand-in for a real content-policy check."""
    return _ModerationVerdict(flagged="ignore" in text.lower())


def run_agent_command(prompt: str) -> str:
    """Run an operator-approved agent command after a moderation check.
    Flagged prompts are logged for policy review.
    Returns the command's standard output.
    """
    verdict = _moderate(prompt)
    if verdict.flagged:
        print(f"[guardrail] flagged prompt: {prompt!r}")  # logged, not blocked
    return subprocess.run(prompt, shell=True, capture_output=True, text=True).stdout


def run_operator_command(prompt: str) -> str:
    """Run a command on behalf of an operator, enforcing the content policy."""
    verdict = _moderate(prompt)
    if verdict.flagged:
        raise ValueError("prompt blocked by content policy")
    return subprocess.run(prompt, shell=True, capture_output=True, text=True).stdout


# --- research crews -----------------------------------------------------------
#
# Crews follow the usual CrewAI shape: a task's `context=[...]` hands the
# previous agent's output to the next agent, so a researcher can brief a
# downstream agent without the two sharing tools.
# Tools are attached per agent, so each crew lists exactly the capabilities
# its members need.


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


def build_research_crew() -> Crew:
    """Researcher scrapes the target site and briefs the executor, which
    carries out the recommended command with its interpreter tool. Used by
    the "investigate and fix" workflow.
    Returns the crew without starting it; the runner calls kickoff().
    """
    researcher = Agent(role="Researcher", tools=[ScrapeWebsiteTool()])
    executor = Agent(role="Executor", tools=[CodeInterpreterTool()])
    research_task = Task(description="scrape the target site", agent=researcher)
    exec_task = Task(
        description="run the recommended command", agent=executor,
        context=[research_task],
    )
    return Crew(agents=[researcher, executor], tasks=[research_task, exec_task])


def build_digest_crew() -> Crew:
    """Researcher scrapes the target site and a summarizer writes the digest
    for the weekly report."""
    researcher = Agent(role="Researcher", tools=[ScrapeWebsiteTool()])
    summarizer = Agent(role="Summarizer", tools=[])
    research_task = Task(description="scrape the target site", agent=researcher)
    summary_task = Task(
        description="summarize the findings", agent=summarizer,
        context=[research_task],
    )
    return Crew(agents=[researcher, summarizer], tasks=[research_task, summary_task])


# --- interpreter sandboxes ------------------------------------------------------
#
# Two ways to give an agent somewhere to run code: a local container the
# agent can manage itself, or a hosted sandbox with fixed limits.
# The hosted sandbox is preferred for untrusted workloads; the local
# container is kept for development setups without a sandbox account.


class _StubDockerContainers:
    def run(self, image: str, **kwargs):
        return {"image": image, "kwargs": kwargs}


class _StubDockerClient:
    def __init__(self) -> None:
        self.containers = _StubDockerContainers()


def docker_from_env() -> _StubDockerClient:
    return _StubDockerClient()


def start_interpreter_container():
    """Start the local interpreter container. The Docker socket is mounted so
    the agent can spin up and tear down its own helper containers, as the
    self-hosted agent setup guide describes.
    Returns the container handle from the Docker SDK.
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


def start_hosted_interpreter():
    """Start a hosted interpreter sandbox with a 30-second timeout and no
    internet access."""
    return _E2BSandbox(timeout=30, allow_internet=False)
