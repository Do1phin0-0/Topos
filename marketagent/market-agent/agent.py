"""
Market Intelligence AI Agent
Powered by Claude with real-time web search and persistent memory.
"""

import anthropic
import os
import re
from datetime import datetime

from watchlist import load_watchlist, save_watchlist, add_to_watchlist, remove_from_watchlist
from memory import (
    load_memory, save_memory, store_analysis, get_prior_thesis_context,
    register_skill, get_skills, list_all_analyzed_symbols
)
from commands import COMMAND_REGISTRY, build_system_prompt
from display import print_header, print_response, print_help, print_error, print_skills, print_history
from data import build_data_context

client = anthropic.Anthropic()

# Commands that should auto-save the response to memory
ANALYSIS_COMMANDS = {"/analyze", "/stock", "/coin", "/risk", "/sentiment"}


def _extract_symbol(user_input: str) -> str | None:
    """Extract the primary asset symbol from a command string."""
    parts = user_input.strip().split()
    if len(parts) >= 2:
        candidate = parts[1].upper().lstrip("$")
        # Basic sanity: 1-10 alphanumeric chars
        if re.match(r"^[A-Z0-9]{1,10}$", candidate):
            return candidate
    return None


def run_command(user_input: str, conversation_history: list, watchlist: dict, memory: dict) -> str:
    """Send a command to the agent with a proper agentic loop for web search."""

    # Inject watchlist context
    context_parts = []
    if watchlist.get("assets"):
        context_parts.append(f"[USER WATCHLIST: {', '.join(watchlist['assets'])}]")

    # Inject live market data (prices, volume, fundamentals, insiders)
    live_data = build_data_context(user_input, watchlist)
    if live_data:
        context_parts.append(live_data)

    # Inject prior thesis context for recognized symbols
    symbol = _extract_symbol(user_input)
    if symbol:
        prior = get_prior_thesis_context(memory, symbol)
        if prior:
            context_parts.append(prior)

    message_content = user_input
    if context_parts:
        message_content += "\n\n" + "\n".join(context_parts)

    conversation_history.append({"role": "user", "content": message_content})

    # Run the agentic loop (handles multi-turn web search tool use)
    messages = list(conversation_history)

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=build_system_prompt(memory),
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=messages,
        )

        if response.stop_reason == "tool_use":
            # Append assistant message (contains tool_use blocks)
            messages.append({"role": "assistant", "content": response.content})

            # Send tool_result for each tool_use block
            # web_search_20250305 is server-side — Anthropic runs the search;
            # we just acknowledge each call and let the server inject results.
            tool_results = [
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": "",
                }
                for block in response.content
                if block.type == "tool_use"
            ]
            messages.append({"role": "user", "content": tool_results})
            continue

        # end_turn or max_tokens — extract final text
        break

    full_response = "".join(
        block.text for block in response.content if hasattr(block, "text")
    )

    # Save to conversation history (text only for compactness)
    conversation_history.append({"role": "assistant", "content": full_response})
    if len(conversation_history) > 40:
        conversation_history[:] = conversation_history[-40:]

    # Auto-save analyses to memory
    cmd = user_input.strip().split()[0].lower() if user_input.strip() else ""
    if cmd in ANALYSIS_COMMANDS and symbol and full_response:
        store_analysis(memory, symbol, full_response, command=cmd)

    return full_response


def handle_local_commands(user_input: str, watchlist: dict, memory: dict) -> tuple[bool, str | None]:
    """Handle commands that don't need the AI."""
    parts = user_input.strip().split()
    cmd = parts[0].lower() if parts else ""

    if cmd == "/help":
        return True, None  # signal print_help

    if cmd == "/skills":
        return True, "SKILLS"  # signal print_skills

    if cmd == "/history":
        if len(parts) >= 2:
            symbol = parts[1].upper()
            return True, f"HISTORY:{symbol}"
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


def handle_buildskill_response(user_input: str, response_text: str, memory: dict):
    """If the user ran /buildskill and the agent described a new skill, register it."""
    parts = user_input.strip().split()
    if len(parts) < 2 or parts[0].lower() != "/buildskill":
        return
    skill_name = parts[1].lower()
    if skill_name not in memory.get("skills", {}):
        # Best-effort extraction — store what the agent produced
        register_skill(
            memory,
            name=skill_name,
            description=f"Custom skill registered via /buildskill on {datetime.now().strftime('%Y-%m-%d')}",
            data_sources="web search",
            output_format="AI-generated",
        )


def main():
    print_header()

    watchlist = load_watchlist()
    memory = load_memory()
    conversation_history = []

    analyzed = list_all_analyzed_symbols(memory)
    if analyzed:
        print(f"Memory loaded — {len(analyzed)} prior analyses: {', '.join(analyzed[:8])}"
              + (" ..." if len(analyzed) > 8 else ""))
    print("Type /help for commands. Type 'exit' to quit.\n")

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
                from memory import get_analysis_history
                print_history(symbol, get_analysis_history(memory, symbol))
            else:
                print(f"\n{local_result}\n")
            continue

        print("\n📡 Fetching live data + researching...\n")
        try:
            response = run_command(user_input, conversation_history, watchlist, memory)
            print_response(response)
            handle_buildskill_response(user_input, response, memory)
        except anthropic.APIError as e:
            print_error(f"API error: {e}")
        except Exception as e:
            print_error(f"Unexpected error: {e}")
            raise


if __name__ == "__main__":
    main()
