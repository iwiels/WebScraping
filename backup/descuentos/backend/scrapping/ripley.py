import os
import time
import random
import re
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.edge.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

def obtener_user_agents():
    user_agents = []
    filepath = "C:/Users/victo/OneDrive/Documentos/descuentos/backend/scrapping/user_agents.txt"
    try:
        with open(filepath, 'r') as file:
            for line in file:
                user_agents.append(line.strip())
    except FileNotFoundError:
        print(f"Error: Archivo '{filepath}' no encontrado.")
    return user_agents

def buscar_en_ripley(producto):
    """Busca un producto en Ripley usando Selenium y recorre hasta 10 páginas de resultados."""
    user_agents = obtener_user_agents()
    if not user_agents:
        return []

    options = Options()
    options.add_argument("--headless")
    options.add_argument('--log-level=3')
    options.add_argument('--silent')
    options.add_argument('--disable-logging')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])
    options.add_experimental_option('useAutomationExtension', False)

    service = Service(executable_path="C:/Users/victo/OneDrive/Documentos/descuentos/backend/scrapping/msedgedriver.exe")
    driver = webdriver.Edge(service=service, options=options)
    driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": random.choice(user_agents)})

    resultados = []

    try:
        driver.get("https://www.ripley.com.pe/")
        try:
            search_input = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'input[type="search"]'))
            )
        except TimeoutException:
            driver.quit()
            return resultados

        # Ingresar el producto y presionar Enter
        search_input.clear()
        search_input.send_keys(producto)
        search_input.send_keys(Keys.RETURN)
        pagina_actual = 1
        max_paginas = 10

        while pagina_actual <= max_paginas:
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.catalog-product-item"))
                )
                items = driver.find_elements(By.CSS_SELECTOR, "div.catalog-product-item")

            except TimeoutException:

                break

            for item in items:
                try:
                    # Extraer nombre
                    nombre_elem = item.find_element(By.CSS_SELECTOR, "div.catalog-product-details__name")
                    nombre = nombre_elem.text.strip()

                    # Extraer link
                    link_elem = item.find_element(By.CSS_SELECTOR, "a.catalog-product-item")
                    link = link_elem.get_attribute("href")

                    # Extraer precio
                    precio = None
                    try:
                        precio_elem = item.find_element(By.CSS_SELECTOR, "li.catalog-prices__offer-price")
                        precio_text = precio_elem.text.strip()
                        precio = float(re.sub(r"[^\d.]", "", precio_text))
                    except (NoSuchElementException, ValueError):
                        continue

                    # Forzar scroll para asegurar carga de la imagen
                    try:
                        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", item)
                        time.sleep(1)
                    except:
                        pass

                    # Buscar la imagen con dos selectores
                    imagen = None
                    try:
                        img_elem = item.find_element(By.CSS_SELECTOR, ".images-preview-item.is-active img")
                        imagen = img_elem.get_attribute("src")
                    except NoSuchElementException:
                        try:
                            img_elem = item.find_element(By.TAG_NAME, "img")
                            imagen = img_elem.get_attribute("src")
                        except NoSuchElementException:
                            print(f"No se encontró imagen para: {nombre}")

                    if imagen and not imagen.startswith('http'):
                        imagen = f"https://www.ripley.com.pe{imagen}"

                    # Extraer descuento
                    descuento_porcentaje = None
                    try:
                        descuento_tag = item.find_element(By.CSS_SELECTOR, 'div.catalog-product-details__discount-tag')
                        descuento_texto = descuento_tag.text.strip().replace('%', '').replace('-', '')
                        descuento_porcentaje = int(descuento_texto)
                    except NoSuchElementException:
                        pass  # No hay etiqueta de descuento

                    if nombre and precio and link:
                        resultados.append({
                            'nombre': nombre,
                            'precio': precio,
                            'link': link,
                            'tienda': 'ripley',
                            'imagen': imagen,
                            'descuento': descuento_porcentaje
                        })

                except Exception as e:
                    continue

            # Scroll al final de la página
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            try:
                next_button = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "a.page-link[aria-label='Siguiente']"))
                )
                if next_button and next_button.is_enabled():
                    driver.execute_script("arguments[0].click();", next_button)
                    pagina_actual += 1
                    time.sleep(random.uniform(4, 7))
                else:
                    break
            except (TimeoutException, NoSuchElementException):

                break

    except Exception as e:
        print(f"Error al buscar en Ripley: {e}")
    finally:
        driver.quit()

    return resultados