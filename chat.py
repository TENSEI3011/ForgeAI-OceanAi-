"""Chat with any agent definition produced by ForgeAI.

    python chat.py runs/hr_policy/agent_definition_final.json
"""
import sys

from forgeai.chat import chat_loop

if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python chat.py <agent_definition.json>")
    chat_loop(sys.argv[1])
