"""Pacote raiz dos generators v2."""

from .base import BaseContentGenerator
from .adapta.client import AdaptaClientV2, AuthResult, ChatCompletionResult
from .adapta.claude_generator import ClaudeGenerator
from .adapta.claude_opus_generator import ClaudeOpusGenerator
from .adapta.deepseek_generator import DeepseekGenerator
from .adapta.deepseek_r1_generator import DeepseekR1Generator
from .adapta.gemini_generator import GeminiGenerator
from .adapta.gpt_generator import GPTGenerator
from .adapta.gpt_o3_generator import GptO3Generator
from .adapta.gpt_o4_mini_generator import GptO4MiniGenerator
from .adapta.gpt_oss_generator import GptOssGenerator
from .adapta.grok_4_generator import Grok4Generator

__all__ = [
    "BaseContentGenerator",
    "AdaptaClientV2",
    "AuthResult",
    "ChatCompletionResult",
    "ClaudeGenerator",
    "ClaudeOpusGenerator",
    "DeepseekGenerator",
    "DeepseekR1Generator",
    "GeminiGenerator",
    "GPTGenerator",
    "GptO3Generator",
    "GptO4MiniGenerator",
    "GptOssGenerator",
    "Grok4Generator",
]
