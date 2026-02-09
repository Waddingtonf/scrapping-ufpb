import os
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# --- CONFIGURAÇÕES VIA VARIÁVEIS DE AMBIENTE ---
# No GitHub Actions, definiremos estes valores nos "Secrets"
EMAIL_REMETENTE = os.environ.get("EMAIL_REMETENTE")
SENHA_REMETENTE = os.environ.get("SENHA_REMETENTE")
EMAIL_DESTINO = os.environ.get("EMAIL_DESTINO", "waddingtonf@outlook.com")
NOME_ALVO = "WADDINGTON FREITAS DA SILVA"

URL_SIPAC = "https://sipac.ufpb.br/public/jsp/processos/consulta_processo.jsf"

def enviar_email(resultado_texto):
    print(f"Enviando e-mail para {EMAIL_DESTINO}...")
    msg = MIMEMultipart()
    msg['From'] = EMAIL_REMETENTE
    msg['To'] = EMAIL_DESTINO
    msg['Subject'] = f"🚨 ALERTA SIPAC: Processo Encontrado!"

    corpo = f"""
    O robô de monitoramento encontrou um resultado para: {NOME_ALVO}
    
    Resumo do que foi encontrado na tela:
    --------------------------------------
    {resultado_texto}
    --------------------------------------
    
    Acesse para conferir: {URL_SIPAC}
    """
    msg.attach(MIMEText(corpo, 'plain'))

    try:
        # Configuração para Outlook/Hotmail. Se for Gmail, mude para smtp.gmail.com
        server = smtplib.SMTP('smtp-mail.outlook.com', 587)
        server.starttls()
        server.login(EMAIL_REMETENTE, SENHA_REMETENTE)
        server.sendmail(EMAIL_REMETENTE, EMAIL_DESTINO, msg.as_string())
        server.quit()
        print("E-mail enviado com sucesso!")
    except Exception as e:
        print(f"Erro ao enviar e-mail: {e}")

def verificar_sipac():
    print("Configurando Chrome...")
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Obrigatório em servidores (sem interface gráfica)
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")

    # Instala o driver compatível automaticamente
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    try:
        print("Acessando SIPAC...")
        driver.get(URL_SIPAC)
        wait = WebDriverWait(driver, 20)

        # 1. Selecionar "Nome Interessado" (Value 200)
        radio = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[value='200']")))
        radio.click()
        time.sleep(1)

        # 2. Digitar o nome
        campo_nome = driver.find_element(By.NAME, "INTERESSADO")
        campo_nome.clear()
        campo_nome.send_keys(NOME_ALVO)

        # 3. Clicar em Consultar
        btn_consultar = driver.find_element(By.CSS_SELECTOR, "input[type='submit']")
        btn_consultar.click()
        
        print("Consulta enviada. Aguardando carregamento...")
        time.sleep(5) # Espera a página processar (JSF é lento)

        # 4. Analisar o HTML da resposta
        page_source = driver.page_source.lower()
        
        # Lógica: Se aparecer a tabela de resultados E NÃO tiver mensagem de erro
        # Ajuste conforme a mensagem real de erro do SIPAC ("nenhum registro", "não encontrado", etc)
        if "nenhum registro encontrado" in page_source or "nenhum processo encontrado" in page_source:
            print("Nenhum processo encontrado.")
        else:
            # Tenta capturar o texto da tabela de resultados
            try:
                # Geralmente os resultados ficam numa tabela com classe 'listagem' ou apenas 'table'
                tabela = driver.find_element(By.TAG_NAME, "table")
                texto_encontrado = tabela.text[:1000] # Pega os primeiros 1000 caracteres
            except:
                texto_encontrado = "Não foi possível extrair o texto, mas o filtro acusou positivo."

            print("!!! ENCONTRADO !!!")
            enviar_email(texto_encontrado)

    except Exception as e:
        print(f"Erro fatal: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    verificar_sipac()
