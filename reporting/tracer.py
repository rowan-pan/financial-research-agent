"""
reporting/tracer.py
Records every Claude API call and tool invocation during a pipeline run.
Renders the execution trace as a Mermaid flowchart for embedding in report.md.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ToolCall:
    agent: str
    tool_name: str
    inputs: dict
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class ClaudeCall:
    agent: str
    model: str
    input_tokens: int
    output_tokens: int
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class ExecutionTrace:
    def __init__(self):
        self.theme: str = ""
        self.claude_calls: list[ClaudeCall] = []
        self.tool_calls: list[ToolCall] = []
        self.sources: list[dict] = []  # articles: {title, source, url, publishedAt}
        self.start_time = datetime.utcnow()

    def set_theme(self, theme: str):
        self.theme = theme

    def record_claude_call(self, agent: str, model: str, usage):
        self.claude_calls.append(
            ClaudeCall(
                agent=agent,
                model=model,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
            )
        )

    def record_sources(self, articles: list[dict]):
        """Add news articles to the deduplicated sources list."""
        seen = {s["url"] for s in self.sources}
        for a in articles:
            url = a.get("url", "")
            if url and url not in seen:
                self.sources.append(a)
                seen.add(url)

    def record_tool_call(self, agent: str, tool_name: str, inputs: dict):
        self.tool_calls.append(ToolCall(agent=agent, tool_name=tool_name, inputs=inputs))

    def total_tokens(self) -> dict:
        return {
            "input": sum(c.input_tokens for c in self.claude_calls),
            "output": sum(c.output_tokens for c in self.claude_calls),
            "total": sum(c.input_tokens + c.output_tokens for c in self.claude_calls),
        }

    def to_mermaid(self) -> str:
        """
        Render the execution trace as a Mermaid flowchart.
        Grouped by agent, showing tool calls within each agent node.
        """
        lines = ["```mermaid", "flowchart TD"]

        # Pipeline stage nodes
        stages = [
            ("SCAN", "Signal Scan"),
            ("THEME", "Theme Detection"),
            ("HYPO", "Hypothesis Generation"),
            ("PREC", "Precedent Finding"),
            ("BACK", "Backtesting"),
            ("SYNTH", "Synthesis"),
            ("VIZ", "Visualization"),
            ("OUT", "Report Output"),
        ]

        agent_to_stage = {
            "theme_detector": "THEME",
            "hypothesis_generator": "HYPO",
            "precedent_finder": "PREC",
            "backtester": "BACK",
            "synthesizer": "SYNTH",
            "visualizer": "VIZ",
        }

        # Define stage boxes
        for stage_id, label in stages:
            lines.append(f'    {stage_id}["{label}"]')

        # Chain stages
        stage_ids = [s[0] for s in stages]
        for i in range(len(stage_ids) - 1):
            lines.append(f"    {stage_ids[i]} --> {stage_ids[i+1]}")

        # Annotate tool calls per agent
        tool_counts: dict[str, dict[str, int]] = {}
        for tc in self.tool_calls:
            stage = agent_to_stage.get(tc.agent, tc.agent)
            tool_counts.setdefault(stage, {})
            tool_counts[stage][tc.tool_name] = tool_counts[stage].get(tc.tool_name, 0) + 1

        for stage, tools in tool_counts.items():
            tool_node_id = f"{stage}_tools"
            tool_labels = "<br/>".join(f"{name} ×{count}" for name, count in tools.items())
            lines.append(f'    {tool_node_id}["🔧 {tool_labels}"]')
            lines.append(f"    {stage} -. calls .-> {tool_node_id}")

        # Annotate Claude calls per agent
        claude_counts: dict[str, int] = {}
        for cc in self.claude_calls:
            stage = agent_to_stage.get(cc.agent, cc.agent)
            claude_counts[stage] = claude_counts.get(stage, 0) + 1

        for stage, count in claude_counts.items():
            claude_node_id = f"{stage}_claude"
            lines.append(f'    {claude_node_id}["🤖 Claude ×{count}"]')
            lines.append(f"    {stage} -. LLM .-> {claude_node_id}")

        # Token summary note
        tokens = self.total_tokens()
        total = tokens["total"]
        inp = tokens["input"]
        out = tokens["output"]
        lines.append(
            f'    NOTE["📊 Total tokens: {total:,} (in: {inp:,} / out: {out:,})"]'
        )
        lines.append("    OUT --> NOTE")

        lines.append("```")
        return "\n".join(lines)

    def sources_section(self) -> str:
        """Render deduplicated sources sorted by date descending as a markdown section."""
        if not self.sources:
            return ""
        sorted_articles = sorted(
            self.sources,
            key=lambda a: a.get("publishedAt", ""),
            reverse=True,
        )
        lines = ["## Sources Retrieved\n"]
        for i, a in enumerate(sorted_articles, 1):
            title = a.get("title", "Untitled")
            source = a.get("source", "")
            url = a.get("url", "")
            published = a.get("publishedAt", "")[:10]  # YYYY-MM-DD
            try:
                date_str = datetime.strptime(published, "%Y-%m-%d").strftime("%B %-d %Y")
            except ValueError:
                date_str = published
            lines.append(f'{i}. "{title}" — {source}, {date_str}')
            lines.append(f"   {url}\n")
        return "\n".join(lines)

    def summary_line(self) -> str:
        tokens = self.total_tokens()
        elapsed = (datetime.utcnow() - self.start_time).seconds
        return (
            f"**Pipeline stats:** "
            f"{len(self.claude_calls)} Claude calls · "
            f"{len(self.tool_calls)} tool calls · "
            f"{tokens['total']:,} total tokens · "
            f"{elapsed}s elapsed"
        )
