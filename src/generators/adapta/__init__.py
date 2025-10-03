"""Sub-pacote adapta - Implementações específicas para a API Adapta.one.

Este módulo contém as implementações dos geradores de conteúdo que utilizam
a API Adapta.one, incluindo suporte para diferentes modelos de IA (GPT, Gemini, Claude).
"""

from .client import AdaptaClient
from .gemini_generator import GeminiGenerator
from .claude_generator import ClaudeGenerator
from .gpt_generator import GPTGenerator
from .claude_opus_generator import ClaudeOpusGenerator
from .deepseek_generator import DeepseekGenerator
from .grok_4_generator import Grok4Generator
from .gpt_oss_generator import GptOssGenerator
from .deepseek_r1_generator import DeepseekR1Generator
from .gpt_o3_generator import GptO3Generator
from .gpt_o4_mini_generator import GptO4MiniGenerator

__all__ = [
    "AdaptaClient",
    "GeminiGenerator", 
    "ClaudeGenerator",
    "GPTGenerator",
    "ClaudeOpusGenerator",
    "DeepseekGenerator",
    "Grok4Generator",
    "GptOssGenerator",
    "DeepseekR1Generator",
    "GptO3Generator",
    "GptO4MiniGenerator",
]