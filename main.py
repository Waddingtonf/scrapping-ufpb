import os
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
            
            msg = (
                f"🚨 *NOVO PROCESSO DETECTADO*\n\n"
                f"O sistema encontrou um registro para: *{NOME_ALVO}*\n"
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
