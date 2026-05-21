from agent.prompts.prompt_builder import PromptBuilder

__all__ = ["PromptBuilder", "ALL_PROMPTS"]

try:
    from agent.prompts.chat_prompts import PROMPTS as _chat
    from agent.prompts.inspection_prompts import PROMPTS as _inspection
    from agent.prompts.shared_prompts import PROMPTS as _shared
    ALL_PROMPTS = _chat + _inspection + _shared
except ImportError:
    ALL_PROMPTS = []
