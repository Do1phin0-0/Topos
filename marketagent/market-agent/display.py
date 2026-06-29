"""
Terminal display and formatting for the Market Intelligence Agent.
Uses rich for pretty output when available, falls back to plain text.
"""

try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.table import Table
    RICH_AVAILABLE = True
    console = Console()
except ImportError:
    RICH_AVAILABLE = False


def print_header():
    if RICH_AVAILABLE:
        console.print(Panel.fit(
            "[bold cyan]Market Intelligence Agent[/bold cyan]\n"
            "[dim]Powered by Claude · Real-time web search · Persistent memory · Not financial advice[/dim]",
            border_style="cyan",
        ))
    else:
        print("=" * 65)
        print("  MARKET INTELLIGENCE AGENT")
        print("  Powered by Claude | Real-time search | Not financial advice")
        print("=" * 65)
    print()


def print_help(command_registry: dict = None):
    """Print all available commands."""
    # Import here to avoid circular import
    if command_registry is None:
        from commands import COMMAND_REGISTRY
        command_registry = COMMAND_REGISTRY

    if RICH_AVAILABLE:
        table = Table(title="Available Commands", border_style="cyan", show_header=True)
        table.add_column("Command", style="bold yellow", no_wrap=True)
        table.add_column("Description", style="white")
        for cmd, desc in command_registry.items():
            table.add_row(cmd, desc)
        console.print(table)
    else:
        print("\nAVAILABLE COMMANDS:")
        print("-" * 60)
        for cmd, desc in command_registry.items():
            print(f"  {cmd:<30} {desc}")
    print()


def print_skills(command_registry: dict, custom_skills: dict):
    """Print built-in commands plus any registered custom skills."""
    if RICH_AVAILABLE:
        table = Table(title="Available Skills", border_style="magenta", show_header=True)
        table.add_column("Skill", style="bold yellow", no_wrap=True)
        table.add_column("Type", style="dim")
        table.add_column("Description", style="white")

        for cmd, desc in command_registry.items():
            table.add_row(cmd, "built-in", desc)

        for name, meta in custom_skills.items():
            table.add_row(f"/{name}", "custom", meta.get("description", ""))

        console.print(table)
    else:
        print("\nBUILT-IN SKILLS:")
        print("-" * 60)
        for cmd, desc in command_registry.items():
            print(f"  {cmd:<30} {desc}")
        if custom_skills:
            print("\nCUSTOM SKILLS:")
            print("-" * 60)
            for name, meta in custom_skills.items():
                print(f"  /{name:<29} {meta.get('description', '')}")
    print()


def print_history(symbol: str, history: list):
    """Print stored analysis history for a symbol."""
    if not history:
        if RICH_AVAILABLE:
            console.print(f"[dim]No stored analyses for {symbol}.[/dim]")
        else:
            print(f"No stored analyses for {symbol}.")
        print()
        return

    title = f"Analysis History: {symbol} ({len(history)} entries)"
    if RICH_AVAILABLE:
        for i, entry in enumerate(history, 1):
            date = entry["date"][:10]
            cmd = entry.get("command", "/analyze")
            snippet = entry["text"][:300].replace("\n", " ")
            panel = Panel(
                f"[dim]{snippet}...[/dim]",
                title=f"[bold]{i}. {date} ({cmd})[/bold]",
                border_style="blue",
            )
            console.print(panel)
    else:
        print(f"\n{title}")
        print("=" * 60)
        for i, entry in enumerate(history, 1):
            date = entry["date"][:10]
            cmd = entry.get("command", "/analyze")
            print(f"\n--- {i}. {date} ({cmd}) ---")
            print(entry["text"][:300] + "...")
    print()


def print_response(text: str):
    """Print the agent's response with markdown formatting."""
    if RICH_AVAILABLE:
        console.print(Markdown(text))
    else:
        print(text)
    print()


def print_error(message: str):
    """Print an error message."""
    if RICH_AVAILABLE:
        console.print(f"[bold red]Error:[/bold red] {message}")
    else:
        print(f"Error: {message}")
    print()
