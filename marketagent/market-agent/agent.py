"""
Market Intelligence AI Agent
Powered by Claude with real-time web search and persistent memory.
"""

import anthropic
import os
import re
import sys
from datetime import datetime

# Load .env if present (optional dependency — silently skip if not installed)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from watchlist import load_watchlist, save_watchlist, add_to_watchlist, remove_from_watchlist
from memory import (
    load_memory, store_analysis, get_prior_thesis_context,
    register_skill, get_skills, list_all_analyzed_symbols, get_analysis_history,
)
from commands import COMMAND_REGISTRY, build_system_prompt
from display import print_header, print_help, print_error, print_skills, print_history
from data import build_data_context

# Commands that auto-save the response to memory
ANALYSIS_COMMANDS = {"/analyze", "/stock", "/coin", "/risk", "/sentiment"}


def _check_api_key():
    """Exit with a clear message if no API key is configured."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("\nError: ANTHROPIC_API_KEY is not set.\n")
        print("Option 1 — .env file (recommended):")
        print("  Copy .env.example to .env and add your key.\n")
        print("Option 2 — environment variable:")
        print("  Mac/Linux:  export ANTHROPIC_API_KEY=your_key_here")
        print("  Windows:    $env:ANTHROPIC_API_KEY=\"your_key_here\"\n")
        print("Get your key at: https://console.anthropic.com\n")
        sys.exit(1)


def _extract_symbols(user_input: str) -> list[str]:
    """Extract up to 2 asset symbols from a command string."""
    parts = user_input.strip().split()
    symbols = []
    for raw in parts[1:]:
        candidate = raw.upper().lstrip("$")
        if re.match(r"^[A-Z0-9]{1,10}$", candidate):
            symbols.append(candidate)
        if len(symbols) == 2:
            break
    return symbols


def run_command(user_input: str, conversation_history: list, watchlist: dict, memory: dict) -> str:
    """Send a command to the agent with streaming output and agentic web search loop."""

    # Build context block
    context_parts = []
    if watchlist.get("assets"):
        context_parts.append(f"[USER WATCHLIST: {', '.join(watchlist['assets'])}]")

    # Live market data (prices, fundamentals, insiders)
    live_data = build_data_context(user_input, watchlist)
    if live_data:
        context_parts.append(live_data)

    # Prior thesis for all recognized symbols (fixes /compare injecting both)
    symbols = _extract_symbols(user_input)
    for sym in symbols:
        prior = get_prior_thesis_context(memory, sym)
        if prior:
            context_parts.append(prior)

    message_content = user_input
    if context_parts:
        message_content += "\n\n" + "\n".join(context_parts)

    conversation_history.append({"role": "user", "content": message_content})
    messages = list(conversation_history)

    client = anthropic.Anthropic()
    full_response = ""
    search_count = 0

    while True:
        current_text = ""

        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=build_system_prompt(memory),
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=messages,
        ) as stream:
            for chunk in stream.text_stream:
                print(chunk, end="", flush=True)
                current_text += chunk
            final = stream.get_final_message()

        if final.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": final.content})
            tool_results = [
                {"type": "tool_result", "tool_use_id": b.id, "content": ""}
                for b in final.content
                if b.type == "tool_use"
            ]
            messages.append({"role": "user", "content": tool_results})
            search_count += 1
            # Show search indicator only if no text was streamed (pure tool call)
            if not current_text:
                print(f"   [searching... #{search_count}]", flush=True)
            continue

        full_response = current_text
        break

    print("\n")  # newline after streamed content

    # Save to conversation history
    conversation_history.append({"role": "assistant", "content": full_response})
    if len(conversation_history) > 40:
        conversation_history[:] = conversation_history[-40:]

    # Auto-save analyses to persistent memory
    cmd = user_input.strip().split()[0].lower() if user_input.strip() else ""
    primary_symbol = symbols[0] if symbols else None
    if cmd in ANALYSIS_COMMANDS and primary_symbol and full_response:
        store_analysis(memory, primary_symbol, full_response, command=cmd)

    return full_response


def handle_local_commands(user_input: str, watchlist: dict, memory: dict) -> tuple[bool, str | None]:
    """Handle commands that don't need the AI."""
    parts = user_input.strip().split()
    cmd = parts[0].lower() if parts else ""

    if cmd == "/help":
        return True, None

    if cmd == "/skills":
        return True, "SKILLS"

    if cmd == "/history":
        if len(parts) >= 2:
            return True, f"HISTORY:{parts[1].upper()}"
        return True, "Usage: /history SYMBOL"

    if cmd == "/watch":
        if len(parts) >= 3 and parts[1].lower() == "add":
            symbol = parts[2].upper()
            add_to_watchlist(watchlist, symbol)
            save_watchlist(watchlist)
            assets = ", ".join(watchlist["assets"]) or "empty"
            return True, f"Added {symbol} to watchlist. Current: {assets}"

        if len(parts) >= 3 and parts[1].lower() == "remove":
            symbol = parts[2].upper()
            remove_from_watchlist(watchlist, symbol)
            save_watchlist(watchlist)
            assets = ", ".join(watchlist["assets"]) or "empty"
            return True, f"Removed {symbol} from watchlist. Current: {assets}"

        if len(parts) == 1 and not watchlist.get("assets"):
            return True, "Your watchlist is empty. Use: /watch add TICKER"

    return False, None


def handle_buildskill_response(user_input: str, memory: dict):
    """Register a new skill after /buildskill runs."""
    parts = user_input.strip().split()
    if len(parts) < 2 or parts[0].lower() != "/buildskill":
        return
    skill_name = parts[1].lower()
    if skill_name not in memory.get("skills", {}):
        register_skill(
            memory,
            name=skill_name,
            description=f"Custom skill registered on {datetime.now().strftime('%Y-%m-%d')}",
            data_sources="web search",
            output_format="AI-generated",
        )


def main():
    _check_api_key()
    print_header()

    watchlist = load_watchlist()
    memory = load_memory()
    conversation_history = []

    analyzed = list_all_analyzed_symbols(memory)
    if analyzed:
        label = ", ".join(analyzed[:8]) + (" ..." if len(analyzed) > 8 else "")
        print(f"Memory: {len(analyzed)} prior analyses ({label})")
    if watchlist.get("assets"):
        print(f"Watchlist: {', '.join(watchlist['assets'])}")
    print("\nType /help for commands. Type 'exit' to quit.\n")

    while True:
        try:
            user_input = input("→ ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nGoodbye.")
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit", "q"):
            print("\nGoodbye.")
            break

        is_local, local_result = handle_local_commands(user_input, watchlist, memory)

        if is_local:
            if local_result is None:
                print_help()
            elif local_result == "SKILLS":
                print_skills(COMMAND_REGISTRY, get_skills(memory))
            elif local_result.startswith("HISTORY:"):
                symbol = local_result.split(":", 1)[1]
                print_history(symbol, get_analysis_history(memory, symbol))
            else:
                print(f"\n{local_result}\n")
            continue

        print("\n📡 Fetching live data...\n")
        try:
            run_command(user_input, conversation_history, watchlist, memory)
            handle_buildskill_response(user_input, memory)
        except anthropic.APIError as e:
            print_error(f"API error: {e}")
        except Exception as e:
            print_error(f"Unexpected error: {e}")
            raise


if __name__ == "__main__":
    main()
