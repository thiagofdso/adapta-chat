"""Subpacote Adapta do stack generators_v2."""

from .client import AdaptaClientV2, AuthResult, ChatCompletionResult
from .claude_45_sonnet_generator import Claude45SonnetGenerator
from .deepseek_v3_generator import DeepseekV3Generator
from .gemini_3_pro_preview_generator import Gemini3ProPreviewGenerator
from .gpt_5_generator import GPT5Generator
from .gpt_51_generator import GPT51Generator
from .grok_41_generator import Grok41Generator
from .o3_generator import O3Generator
from .one_pro_generator import OneProGenerator
from .qwen3_max_generator import Qwen3MaxGenerator
from .sonar_pro_generator import SonarProGenerator

__all__ = [
    "AdaptaClientV2",
    "AuthResult",
    "ChatCompletionResult",
    "Claude45SonnetGenerator",
    "DeepseekV3Generator",
    "Gemini3ProPreviewGenerator",
    "GPT5Generator",
    "GPT51Generator",
    "Grok41Generator",
    "O3Generator",
    "OneProGenerator",
    "Qwen3MaxGenerator",
    "SonarProGenerator",
]
