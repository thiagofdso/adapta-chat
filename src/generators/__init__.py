"""Módulo generators - Implementações de provedores de IA para geração de conteúdo."""

from .base import BaseContentGenerator

# Importa geradores do sub-pacote adapta
try:
    from .adapta import (
        AdaptaClient,
        GeminiGenerator,
        ClaudeGenerator,
        GPTGenerator,
        ClaudeOpusGenerator,
        DeepseekGenerator,
        Grok4Generator,
        GptOssGenerator,
        DeepseekR1Generator,
        GptO3Generator,
        GptO4MiniGenerator
    )
    __all__ = [
        "BaseContentGenerator",
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
except ImportError:
    # Se o sub-pacote adapta não estiver disponível, exporta apenas a base
    __all__ = ["BaseContentGenerator"]