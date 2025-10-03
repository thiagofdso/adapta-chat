#!/usr/bin/env python3
"""Script de teste para validar os geradores do sub-pacote adapta."""

import asyncio
import sys
import tempfile
from pathlib import Path

# Adiciona o diretório src ao path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from generators import (
    BaseContentGenerator,
    GeminiGenerator,
    ClaudeGenerator,
    GPTGenerator
)
from generators.adapta.client import AdaptaClient


def log_info(message: str) -> None:
    """Função simples de logging."""
    print(f"INFO: {message}")


def log_error(message: str) -> None:
    """Função simples de logging de erro."""
    print(f"ERROR: {message}")


async def test_adapta_client():
    """Testa a funcionalidade do AdaptaClient."""
    log_info("Testando AdaptaClient...")
    
    try:
        # Cria instância do cliente (sem cookies para teste)
        client = AdaptaClient()
        log_info("✓ AdaptaClient criado com sucesso")
        
        # Testa métodos estáticos de verificação de formatos
        log_info("  - Testando verificação de formatos aceitos...")
        formatos_aceitos = AdaptaClient.get_formatos_aceitos()
        log_info(f"    Formatos aceitos: {', '.join(formatos_aceitos)}")
        
        # Testa formatos aceitos
        formatos_validos = ['.txt', '.docx', '.pdf', '.xlsx', '.xls', '.csv', '.png', '.jpg']
        for formato in formatos_validos:
            is_aceito = AdaptaClient.is_formato_aceito(formato)
            log_info(f"    {formato}: {'✓' if is_aceito else '❌'}")
        
        # Testa formatos não aceitos
        formatos_invalidos = ['.mp3', '.mp4', '.avi', '.zip', '.rar', '.exe']
        for formato in formatos_invalidos:
            is_aceito = AdaptaClient.is_formato_aceito(formato)
            log_info(f"    {formato}: {'❌' if not is_aceito else '✓ (erro)'}")
        
        # Testa health check (deve falhar sem cookies válidos)
        health_status = await client.health_check()
        log_info(f"  - Health check: {health_status}")
        
        # Testa upload de arquivo com formato aceito (deve falhar sem cookies válidos)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as temp_file:
            temp_file.write("Arquivo de teste para upload")
            temp_file_path = temp_file.name
        
        try:
            upload_result = await client.upload_arquivo(temp_file_path)
            log_info(f"  - Upload de arquivo .txt: {upload_result}")
        except Exception as e:
            log_info(f"  - Upload de arquivo .txt (esperado falhar): {e}")
        finally:
            # Remove arquivo temporário
            Path(temp_file_path).unlink(missing_ok=True)
        
        # Testa upload de arquivo com formato aceito (.pdf)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.pdf', delete=False) as temp_file:
            temp_file.write("%PDF-1.4\nTeste PDF")
            temp_file_path = temp_file.name
        
        try:
            upload_result = await client.upload_arquivo(temp_file_path)
            log_info(f"  - Upload de arquivo .pdf: {upload_result}")
        except Exception as e:
            log_info(f"  - Upload de arquivo .pdf (esperado falhar): {e}")
        finally:
            # Remove arquivo temporário
            Path(temp_file_path).unlink(missing_ok=True)
        
        # Testa upload de arquivo com formato NÃO aceito (.mp3)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.mp3', delete=False) as temp_file:
            temp_file.write("Arquivo de áudio não suportado")
            temp_file_path = temp_file.name
        
        try:
            upload_result = await client.upload_arquivo(temp_file_path)
            log_info(f"  - Upload de arquivo .mp3: {upload_result}")
        except ValueError as e:
            log_info(f"  - Upload de arquivo .mp3 (rejeitado corretamente): {e}")
        except Exception as e:
            log_info(f"  - Upload de arquivo .mp3 (outro erro): {e}")
        finally:
            # Remove arquivo temporário
            Path(temp_file_path).unlink(missing_ok=True)
        
        # Testa upload de arquivo com formato NÃO aceito (.mp4)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.mp4', delete=False) as temp_file:
            temp_file.write("Arquivo de vídeo não suportado")
            temp_file_path = temp_file.name
        
        try:
            upload_result = await client.upload_arquivo(temp_file_path)
            log_info(f"  - Upload de arquivo .mp4: {upload_result}")
        except ValueError as e:
            log_info(f"  - Upload de arquivo .mp4 (rejeitado corretamente): {e}")
        except Exception as e:
            log_info(f"  - Upload de arquivo .mp4 (outro erro): {e}")
        finally:
            # Remove arquivo temporário
            Path(temp_file_path).unlink(missing_ok=True)
        
        # Testa exclusão de arquivo (deve falhar sem ID válido)
        try:
            delete_result = await client.excluir_arquivo("test-id-123")
            log_info(f"  - Exclusão de arquivo: {delete_result}")
        except Exception as e:
            log_info(f"  - Exclusão de arquivo (esperado falhar): {e}")
        
        log_info("✓ AdaptaClient testado com sucesso")
        
    except Exception as e:
        log_error(f"❌ Erro ao testar AdaptaClient: {e}")


async def test_adapta_generators():
    """Testa a funcionalidade dos geradores do sub-pacote adapta."""
    log_info("Iniciando testes dos geradores Adapta...")
    
    # Texto de teste
    test_text = "Este é um texto de teste sobre inteligência artificial e machine learning. Vamos verificar se os geradores estão funcionando corretamente."
    test_texts = [
        "Primeiro texto sobre IA e automação",
        "Segundo texto sobre machine learning e deep learning",
        "Terceiro texto sobre processamento de linguagem natural"
    ]
    
    # Lista de geradores para testar
    generators = [
        ("GeminiGenerator", GeminiGenerator),
        ("ClaudeGenerator", ClaudeGenerator),
        ("GPTGenerator", GPTGenerator)
    ]
    
    for generator_name, generator_class in generators:
        log_info(f"Testando {generator_name}...")
        
        try:
            # Cria instância do gerador (sem cookies para teste)
            generator = generator_class()
            log_info(f"✓ {generator_name} criado com sucesso")
            
            # Testa métodos básicos
            log_info(f"  - Nome do provedor: {generator.get_provider_name()}")
            log_info(f"  - Modelos suportados: {generator.get_supported_models()}")
            
            # Testa health check (deve falhar sem cookies válidos)
            health_status = await generator.health_check()
            log_info(f"  - Health check: {health_status}")
            
            # Testa carregamento de prompts
            try:
                summarize_prompt = generator._load_prompt("summarize")
                diagram_prompt = generator._load_prompt("diagram")
                mindmap_prompt = generator._load_prompt("mindmap")
                preprocess_prompt = generator._load_prompt("preprocess_mindmap")
                log_info(f"  - Prompts carregados: summarize ({len(summarize_prompt)} chars), diagram ({len(diagram_prompt)} chars), mindmap ({len(mindmap_prompt)} chars), preprocess ({len(preprocess_prompt)} chars)")
            except Exception as e:
                log_error(f"  - Erro ao carregar prompts: {e}")
            
            # Testa pré-processamento de mapa mental (não requer API)
            try:
                preprocessed = await generator.preprocess_mindmap(test_texts)
                log_info(f"  - Pré-processamento: {len(preprocessed)} caracteres")
                print(f"    Pré-processamento: {preprocessed[:200]}...")
            except Exception as e:
                log_error(f"  - Erro no pré-processamento: {e}")
            
            log_info(f"✓ {generator_name} testado com sucesso")
            
        except Exception as e:
            log_error(f"❌ Erro ao testar {generator_name}: {e}")
    
    log_info("🎉 Testes dos geradores Adapta concluídos!")


async def test_generator_interface():
    """Testa se os geradores implementam corretamente a interface base."""
    log_info("Testando implementação da interface BaseContentGenerator...")
    
    generators = [GeminiGenerator, ClaudeGenerator, GPTGenerator]
    
    for generator_class in generators:
        generator_name = generator_class.__name__
        log_info(f"Verificando {generator_name}...")
        
        # Verifica se herda de BaseContentGenerator
        if not issubclass(generator_class, BaseContentGenerator):
            log_error(f"❌ {generator_name} não herda de BaseContentGenerator")
            continue
        
        # Verifica se tem todos os métodos obrigatórios
        required_methods = [
            'summarize', 'diagram', 'create_mindmap', 
            'generate_content', 'health_check'
        ]
        
        for method_name in required_methods:
            if not hasattr(generator_class, method_name):
                log_error(f"❌ {generator_name} não tem método {method_name}")
            else:
                method = getattr(generator_class, method_name)
                if not asyncio.iscoroutinefunction(method):
                    log_error(f"❌ {generator_name}.{method_name} não é assíncrono")
                else:
                    log_info(f"  ✓ {method_name} implementado corretamente")
        
        log_info(f"✓ {generator_name} implementa a interface corretamente")
    
    log_info("🎉 Teste de interface concluído!")


if __name__ == "__main__":
    #asyncio.run(test_adapta_client())
    #asyncio.run(test_generator_interface())
    asyncio.run(test_adapta_generators()) 