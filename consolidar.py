#!/usr/bin/env python3
import os
import sys
import glob
from pathlib import Path

def contar_palavras(texto):
    """Conta o número de palavras em um texto."""
    return len(texto.split())

def gerar_estrutura_arquivo(caminho_arquivo, conteudo_arquivo):
    """Gera a estrutura completa do arquivo com header, conteúdo e trailer."""
    # Calcula o caminho relativo
    caminho_relativo = os.path.relpath(caminho_arquivo)
    
    # Conta as linhas do arquivo original
    linhas = conteudo_arquivo.count('\n') + (1 if conteudo_arquivo and not conteudo_arquivo.endswith('\n') else 0)
    
    # Monta a estrutura completa
    estrutura = f"""-------- HEADER --------
{caminho_relativo}
-------- FIM HEADER --------
{conteudo_arquivo}
-------- TRAILER --------
Linhas: {linhas}
-------- FIM TRAILER --------"""
    
    return estrutura

def processar_pasta(pasta_origem):
    """Processa todos os arquivos .txt da pasta e gera arquivos consolidados."""
    
    # Verifica se a pasta existe
    if not os.path.isdir(pasta_origem):
        print(f"Erro: A pasta '{pasta_origem}' não existe.")
        return
    
    # Nome base para os arquivos de saída (nome da pasta)
    nome_pasta = os.path.basename(os.path.abspath(pasta_origem))
    
    # Lista todos os arquivos .txt da pasta
    arquivos_txt = glob.glob(os.path.join(pasta_origem, "*.txt"))
    
    if not arquivos_txt:
        print(f"Nenhum arquivo .txt encontrado na pasta '{pasta_origem}'.")
        return
    
    # Ordena os arquivos para processamento consistente
    arquivos_txt.sort()
    
    # Variáveis de controle
    contador_arquivo = 1
    conteudo_atual = ""
    palavras_atual = 0
    max_palavras = 300000
    
    print(f"Processando {len(arquivos_txt)} arquivos .txt da pasta '{pasta_origem}'...")
    
    for arquivo_path in arquivos_txt:
        try:
            # Lê o conteúdo do arquivo
            with open(arquivo_path, 'r', encoding='utf-8') as f:
                conteudo_arquivo = f.read()
            
            # Gera a estrutura completa do arquivo
            estrutura_completa = gerar_estrutura_arquivo(arquivo_path, conteudo_arquivo)
            palavras_estrutura = contar_palavras(estrutura_completa)
            
            # Verifica se o arquivo atual sozinho excede o limite
            if palavras_estrutura > max_palavras:
                print(f"Aviso: O arquivo '{os.path.basename(arquivo_path)}' tem {palavras_estrutura} palavras, "
                      f"excedendo o limite de {max_palavras} palavras. Será colocado em um arquivo separado.")
                
                # Se já temos conteúdo acumulado, salva primeiro
                if conteudo_atual:
                    nome_arquivo_saida = f"{nome_pasta}{contador_arquivo:02d}.txt"
                    with open(nome_arquivo_saida, 'w', encoding='utf-8') as f:
                        f.write(conteudo_atual)
                    print(f"Arquivo gerado: {nome_arquivo_saida} ({palavras_atual} palavras)")
                    contador_arquivo += 1
                    conteudo_atual = ""
                    palavras_atual = 0
                
                # Salva o arquivo grande sozinho
                nome_arquivo_saida = f"{nome_pasta}{contador_arquivo:02d}.txt"
                with open(nome_arquivo_saida, 'w', encoding='utf-8') as f:
                    f.write(estrutura_completa)
                print(f"Arquivo gerado: {nome_arquivo_saida} ({palavras_estrutura} palavras)")
                contador_arquivo += 1
                
            else:
                # Verifica se adicionar este arquivo excederia o limite
                if palavras_atual + palavras_estrutura > max_palavras and conteudo_atual:
                    # Salva o arquivo atual
                    nome_arquivo_saida = f"{nome_pasta}{contador_arquivo:02d}.txt"
                    with open(nome_arquivo_saida, 'w', encoding='utf-8') as f:
                        f.write(conteudo_atual)
                    print(f"Arquivo gerado: {nome_arquivo_saida} ({palavras_atual} palavras)")
                    contador_arquivo += 1
                    conteudo_atual = ""
                    palavras_atual = 0
                
                # Adiciona o arquivo atual ao conteúdo
                if conteudo_atual:
                    conteudo_atual += "\n\n"
                conteudo_atual += estrutura_completa
                palavras_atual += palavras_estrutura
        
        except Exception as e:
            print(f"Erro ao processar o arquivo '{arquivo_path}': {e}")
            continue
    
    # Salva o último arquivo se houver conteúdo restante
    if conteudo_atual:
        nome_arquivo_saida = f"{nome_pasta}{contador_arquivo:02d}.txt"
        with open(nome_arquivo_saida, 'w', encoding='utf-8') as f:
            f.write(conteudo_atual)
        print(f"Arquivo gerado: {nome_arquivo_saida} ({palavras_atual} palavras)")
    
    print(f"\nProcessamento concluído! {contador_arquivo} arquivo(s) gerado(s).")

def main():
    """Função principal do programa."""
    if len(sys.argv) != 2:
        print("Uso: python script.py <pasta_origem>")
        print("Exemplo: python script.py /caminho/para/pasta")
        sys.exit(1)
    
    pasta_origem = sys.argv[1]
    processar_pasta(pasta_origem)

if __name__ == "__main__":
    main()