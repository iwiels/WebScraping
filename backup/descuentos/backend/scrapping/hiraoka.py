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
from .ripley import obtener_user_agents

def buscar_en_hiraoka(producto):
    """Busca un producto en Hiraoka usando Selenium."""
    resultados = []
    user_agents = obtener_user_agents()
    if not user_agents:
        return resultados

    options = Options()
    #options.add_argument("--headless")#
    options.add_argument('--log-level=3')
    options.add_argument('--silent')
    options.add_argument('--disable-logging')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])
    options.add_experimental_option('useAutomationExtension', False)

    service = Service(executable_path="backup/descuentos/backend/scrapping/msedgedriver.exe")
    driver = webdriver.Edge(service=service, options=options)

    try:
        driver.get("https://hiraoka.com.pe")
        
        # Esperar y encontrar el campo de búsqueda
        search_input = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "input#search"))
        )
        search_input.clear()
        search_input.send_keys(producto)
        search_input.send_keys(Keys.RETURN)

        time.sleep(3)

        pagina_actual = 1
        max_paginas = 10

        while pagina_actual <= max_paginas:
            try:
                # Esperar a que los productos se carguen
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "li.product-item"))
                )

                # Obtener todos los productos de la página
                productos = driver.find_elements(By.CSS_SELECTOR, "li.product-item")

                for item in productos:
                    try:
                        # Extraer marca
                        marca = item.find_element(By.CSS_SELECTOR, ".product-item-brand a").text.strip()
                        
                        # Extraer nombre
                        nombre = item.find_element(By.CSS_SELECTOR, ".product-item-name a").text.strip()
                        
                        # Extraer link
                        link = item.find_element(By.CSS_SELECTOR, ".product-item-link").get_attribute("href")
                        
                        # Extraer imagen
                        imagen = item.find_element(By.CSS_SELECTOR, ".product-image-photo").get_attribute("src")
                        
                        # Extraer precios
                        precio_actual = None
                        precio_antiguo = None

                        try:
                            precio_actual = float(re.sub(r'[^\d.]', '', 
                                item.find_element(By.CSS_SELECTOR, "span[data-price-type='finalPrice'] .price").text))
                            precio_antiguo = float(re.sub(r'[^\d.]', '', 
                                item.find_element(By.CSS_SELECTOR, "span[data-price-type='oldPrice'] .price").text))
                        except:
                            continue

                        # Calcular descuento
                        descuento = None
                        if precio_actual and precio_antiguo and precio_antiguo > precio_actual:
                            descuento = int(((precio_antiguo - precio_actual) / precio_antiguo) * 100)

                        if precio_actual and nombre and link:
                            resultados.append({
                                'nombre': f"{marca} {nombre}".strip(),
                                'precio': precio_actual,
                                'link': link,
                                'tienda': 'hiraoka',
                                'imagen': imagen,
                                'descuento': descuento
                            })

                    except Exception as e:
                        print(f"Error procesando producto: {str(e)}")
                        continue

                # Intentar pasar a la siguiente página
                try:
                    next_button = driver.find_element(By.CSS_SELECTOR, "li.pages-item-next:not(.disabled) a")
                    driver.execute_script("arguments[0].click();", next_button)
                    pagina_actual += 1
                    time.sleep(random.uniform(4, 7))
                except NoSuchElementException:
                    break

            except TimeoutException:
                break

    except Exception as e:
        print(f"Error al buscar en Hiraoka: {e}")
    finally:
        driver.quit()

    return resultados
