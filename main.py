import os
import re
import time
import requests  # Nova biblioteca necessária para o Telegram
import json
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# --- CONFIGURAÇÕES ---
# As credenciais virão das Secrets do GitHub
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

NOME_ALVO = "WADDINGTON FREITAS DA SILVA"
URL_SIPAC = "https://sipac.ufpb.br/public/jsp/processos/consulta_processo.jsf"

# --- PERSISTÊNCIA DE ESTADO ---
STATE_FILE = "last_state.json"

def carregar_ultimo_estado():
    """Carrega o último estado salvo do arquivo JSON."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Erro ao ler arquivo de estado: {e}")
    return None

def salvar_estado(estado):
    """Salva o estado atual no arquivo JSON."""
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(estado, f, indent=4, ensure_ascii=False)
        print("Novo estado salvo com sucesso.")
    except Exception as e:
        print(f"Erro ao salvar arquivo de estado: {e}")


def extrair_campo_texto(texto_pagina, rotulo):
    """Extrai valor de um campo textual no formato 'Rótulo: valor'."""
    padrao = rf"{re.escape(rotulo)}\s*([^\n\r]+)"
    match = re.search(padrao, texto_pagina, flags=re.IGNORECASE)
    if not match:
        return "Não informado"
    return match.group(1).strip()

def abrir_primeiro_processo(driver, wait):
    """Abre o primeiro processo encontrado no resultado (ícone da lupa/link de detalhe)."""
    seletores_lupa = [
        "a[title*='Visualizar']",
        "a[href*='detalhe']",
        "a[href*='processo']",
        "a[href*='consulta_processo']",
        "a[onclick*='processo']",
    ]

    for seletor in seletores_lupa:
        elementos = driver.find_elements(By.CSS_SELECTOR, seletor)
        for elemento in elementos:
            texto_ancora = (elemento.text or "").strip().lower()
            title_ancora = (elemento.get_attribute("title") or "").strip().lower()
            if "sistema integrado" in title_ancora:
                continue

            if title_ancora and "visualizar" not in title_ancora and texto_ancora:
                continue

            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elemento)
            elemento.click()
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            return True

    return False

def extrair_dados_essenciais(driver):
    """Extrai dados essenciais da página de detalhes do processo."""
    texto_pagina = driver.find_element(By.TAG_NAME, "body").text

    dados = {
        "numero": extrair_campo_texto(texto_pagina, "Processo:"),
        "origem": extrair_campo_texto(texto_pagina, "Origem do Processo:"),
        "data_autuacao": extrair_campo_texto(texto_pagina, "Data de Autuação:"),
        "assunto": extrair_campo_texto(texto_pagina, "Assunto do Processo:"),
        "assunto_detalhado": extrair_campo_texto(texto_pagina, "Assunto Detalhado:"),
        "natureza": extrair_campo_texto(texto_pagina, "Natureza do Processo:"),
        "unidade_origem": extrair_campo_texto(texto_pagina, "Unidade de Origem:"),
        "status": extrair_campo_texto(texto_pagina, "Status:"),
        "data_cadastro": extrair_campo_texto(texto_pagina, "Data de Cadastro:"),
    }

    return dados

def extrair_documentos_da_pagina(driver):
    """Extrai os documentos da página de detalhes do processo."""
    documentos = []
    try:
        todas_tabelas = driver.find_elements(By.TAG_NAME, "table")
        tabela_documentos = None
        
        # 1. Tenta encontrar a tabela que possui a coluna "Espécie" nos headers (th)
        for t in todas_tabelas:
            try:
                headers = [th.text.strip().lower() for th in t.find_elements(By.TAG_NAME, "th")]
                if any("espécie" in h or "especie" in h for h in headers):
                    tabela_documentos = t
                    print("Tabela de documentos encontrada pelo header <th>.")
                    break
            except Exception:
                continue

        # 2. Se não encontrou por th, tenta encontrar por td da primeira linha da tabela
        if not tabela_documentos:
            for t in todas_tabelas:
                try:
                    tr_elements = t.find_elements(By.TAG_NAME, "tr")
                    if tr_elements:
                        primeira_linha = tr_elements[0]
                        cols = [td.text.strip().lower() for td in primeira_linha.find_elements(By.TAG_NAME, "td")]
                        if any("espécie" in c or "especie" in c for c in cols):
                            tabela_documentos = t
                            print("Tabela de documentos encontrada pela primeira linha de <td>.")
                            break
                except Exception:
                    continue

        # 3. Se não encontrou por headers, tenta por classes padrão (com filtro de texto)
        if not tabela_documentos:
            for classe in ["table.subListagem", "table.listagem", "table"]:
                tabelas = driver.find_elements(By.CSS_SELECTOR, classe)
                for t in tabelas:
                    try:
                        texto_t = t.text.lower()
                        if "espécie" in texto_t or "especie" in texto_t or "documento" in texto_t:
                            tabela_documentos = t
                            print(f"Tabela de documentos encontrada pela classe ou filtro: {classe}")
                            break
                    except Exception:
                        continue
                if tabela_documentos:
                    break

        if tabela_documentos:
            # Pega todas as linhas de tr de forma genérica (sem assumir tbody)
            linhas = tabela_documentos.find_elements(By.TAG_NAME, "tr")
            for linha in linhas:
                cols = linha.find_elements(By.TAG_NAME, "td")
                if len(cols) >= 3:
                    ordem = cols[0].text.strip()
                    especie = cols[1].text.strip()
                    data = cols[2].text.strip()
                    
                    # Ignora se for cabeçalho
                    if "ordem" in ordem.lower() or "espécie" in especie.lower() or "especie" in especie.lower():
                        continue
                        
                    if especie and (ordem.isdigit() or (ordem and ordem[0].isdigit())):
                        documentos.append({
                            "ordem": ordem,
                            "especie": especie,
                            "data": data
                        })
            print(f"Documentos extraídos com sucesso: {len(documentos)}")
        else:
            print("Não foi possível identificar a tabela de documentos na página.")
    except Exception as e:
        print(f"Erro ao extrair documentos da página: {e}")
    return documentos

def enviar_telegram(mensagem):
    """Envia mensagem para o seu Telegram pessoal via API do Bot."""
    print(f"Enviando notificação via Telegram...")
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensagem,
        "parse_mode": "Markdown" # Permite negrito e formatação básica
    }
    
    try:
        response = requests.post(url, data=payload)
        if response.status_code == 200:
            print("Mensagem Telegram enviada com sucesso!")
        else:
            print(f"Erro Telegram: {response.text}")
    except Exception as e:
        print(f"Falha na conexão com Telegram: {e}")

def verificar_sipac():
    print("Iniciando verificação (Modo Headless)...")
    
    # Carrega o estado anterior
    estado_anterior = carregar_ultimo_estado()
    
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    try:
        driver.get(URL_SIPAC)
        wait = WebDriverWait(driver, 20)

        # 1. Selecionar "Nome Interessado"
        print("Selecionando filtro...")
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[value='200']"))).click()
        
        # 2. Preencher Nome
        print(f"Buscando por: {NOME_ALVO}")
        campo_nome = driver.find_element(By.NAME, "INTERESSADO")
        campo_nome.clear()
        campo_nome.send_keys(NOME_ALVO)

        # 3. Consultar
        driver.find_element(By.CSS_SELECTOR, "input[type='submit']").click()
        
        # 4. Validar Resultado
        time.sleep(5) # Aguarda processamento do servidor
        page_source = driver.page_source.lower()

        # Lógica de detecção
        if "nenhum registro encontrado" in page_source or "nenhum processo encontrado" in page_source:
            print("Nenhum processo encontrado.")
            estado_atual = {
                "numero": None,
                "status": "Nenhum processo encontrado",
                "quantidade_documentos": 0,
                "documentos": []
            }
            if estado_anterior != estado_atual:
                print("Alteração detectada: Anteriormente havia processos e agora nenhum foi encontrado.")
                salvar_estado(estado_atual)
        else:
            print("!!! ALERTA: PROCESSO ENCONTRADO !!!")

            dados_essenciais = None
            documentos = []
            if abrir_primeiro_processo(driver, wait):
                time.sleep(2)
                dados_essenciais = extrair_dados_essenciais(driver)
                documentos = extrair_documentos_da_pagina(driver)

            if dados_essenciais:
                estado_atual = {
                    "numero": dados_essenciais.get("numero"),
                    "status": dados_essenciais.get("status"),
                    "quantidade_documentos": len(documentos),
                    "documentos": documentos
                }
            else:
                numeros_processo = sorted(
                    set(
                        re.findall(r"\b\d{5}\.\d{6}/\d{4}-\d{2}\b", driver.page_source)
                    )
                )
                estado_atual = {
                    "numero": ", ".join(numeros_processo) if numeros_processo else "Não identificado",
                    "status": "Encontrado na lista (sem detalhes)",
                    "quantidade_documentos": 0,
                    "documentos": []
                }

            # Compara se houve alteração em relação ao último estado
            if estado_anterior != estado_atual:
                print("Atualização detectada! Enviando notificação...")
                
                if dados_essenciais:
                    if documentos:
                        exibidos = documentos[:30]
                        texto_docs = f"\n*Documentos ({len(documentos)}):*\n" + "\n".join(
                            f"- {doc['ordem']}. {doc['especie']} ({doc['data']})" for doc in exibidos
                        )
                        if len(documentos) > 30:
                            texto_docs += f"\n- ... e mais {len(documentos) - 30} documentos."
                    else:
                        texto_docs = "\n*Documentos:* Nenhum documento listado."

                    detalhes = (
                        f"*Número:* `{dados_essenciais['numero']}`\n"
                        f"*Origem:* {dados_essenciais['origem']}\n"
                        f"*Status:* {dados_essenciais['status']}\n"
                        f"*Data de Autuação:* {dados_essenciais['data_autuacao']}\n"
                        f"*Data de Cadastro:* {dados_essenciais['data_cadastro']}\n"
                        f"*Assunto:* {dados_essenciais['assunto']}\n"
                        f"*Assunto Detalhado:* {dados_essenciais['assunto_detalhado']}\n"
                        f"*Natureza:* {dados_essenciais['natureza']}\n"
                        f"*Unidade de Origem:* {dados_essenciais['unidade_origem']}"
                        f"{texto_docs}"
                    )
                else:
                    if numeros_processo:
                        detalhes = "*Número(s) do processo:*\n" + "\n".join(
                            f"- `{numero}`" for numero in numeros_processo
                        )
                    else:
                        detalhes = "*Número(s) do processo:*\n- Número não identificado automaticamente"
                
                msg = (
                    f"🚨 *ATUALIZAÇÃO DE PROCESSO DETECTADA*\n\n"
                    f"O sistema encontrou novidades para: *{NOME_ALVO}*\n"
                    f"{detalhes}\n\n"
                    f"[Clique aqui para acessar o SIPAC]({URL_SIPAC})"
                )
                enviar_telegram(msg)
                salvar_estado(estado_atual)
            else:
                print("Nenhuma alteração detectada desde a última verificação. Notificação ignorada.")

    except Exception as e:
        print(f"Erro fatal durante a execução: {e}")
        # Opcional: Enviar erro pro Telegram também para você saber que falhou
        # enviar_telegram(f"⚠️ Erro no script do SIPAC: {str(e)}")
    finally:
        driver.quit()

if __name__ == "__main__":
    verificar_sipac()
