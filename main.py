import os
import re
import time
import requests  # Nova biblioteca necessária para o Telegram
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
        else:
            print("!!! ALERTA: PROCESSO ENCONTRADO !!!")

            dados_essenciais = None
            if abrir_primeiro_processo(driver, wait):
                time.sleep(2)
                dados_essenciais = extrair_dados_essenciais(driver)

            if dados_essenciais:
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
                )
            else:
                numeros_processo = sorted(
                    set(
                        re.findall(r"\b\d{5}\.\d{6}/\d{4}-\d{2}\b", driver.page_source)
                    )
                )

                if numeros_processo:
                    detalhes = "*Número(s) do processo:*\n" + "\n".join(
                        f"- `{numero}`" for numero in numeros_processo
                    )
                else:
                    detalhes = "*Número(s) do processo:*\n- Número não identificado automaticamente"
            
            msg = (
                f"🚨 *NOVO PROCESSO DETECTADO*\n\n"
                f"O sistema encontrou um registro para: *{NOME_ALVO}*\n"
                f"{detalhes}\n\n"
                f"[Clique aqui para acessar o SIPAC]({URL_SIPAC})"
            )
            enviar_telegram(msg)

    except Exception as e:
        print(f"Erro fatal durante a execução: {e}")
        # Opcional: Enviar erro pro Telegram também para você saber que falhou
        # enviar_telegram(f"⚠️ Erro no script do SIPAC: {str(e)}")
    finally:
        driver.quit()

if __name__ == "__main__":
    verificar_sipac()
