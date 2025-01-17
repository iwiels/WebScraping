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

def buscar_en_estilos(producto):
    """Busca un producto en Estilos usando Selenium y recorre hasta 10 páginas de resultados."""
    user_agents = obtener_user_agents()
    if not user_agents:
        print("Error: Lista de User-Agents vacía.")
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

    service = Service(executable_path="backup/descuentos/backend/scrapping/msedgedriver.exe")
    driver = webdriver.Edge(service=service, options=options)

    resultados = []

    try:
        driver.get("https://www.estilos.com.pe/")
        try:
            search_input = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "input.vtex-styleguide-9-x-input"))
            )
        except TimeoutException:
            driver.quit()
            return resultados

        search_input.clear()
        search_input.send_keys(producto)
        search_input.send_keys(Keys.RETURN)

        pagina_actual = 1
        max_paginas = 10

        while pagina_actual <= max_paginas:
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.vtex-search-result-3-x-galleryItem"))
                )
                items = driver.find_elements(By.CSS_SELECTOR, "div.vtex-search-result-3-x-galleryItem")
            except TimeoutException:
  
                break

            for item in items:
                try:
                    # Extraer nombre
                    nombre_elem = item.find_element(By.CSS_SELECTOR, "span.vtex-product-summary-2-x-productBrand")
                    nombre = nombre_elem.text.strip()

                    # Extraer link
                    link_elem = item.find_element(By.CSS_SELECTOR, "a.vtex-product-summary-2-x-clearLink")
                    link = link_elem.get_attribute("href")

                    # Extraer precio
                    precio = None
                    try:
                        precio_elem = item.find_element(By.CSS_SELECTOR, "span.vtex-product-price-1-x-sellingPriceValue")
                        precio_text = precio_elem.text.strip()
                        precio = float(re.sub(r"[^\d.]", "", precio_text))
                    except (NoSuchElementException, ValueError):
                        continue

                    # Extraer descuento
                    descuento = None
                    try:
                        desc_elem = item.find_element(By.CSS_SELECTOR, "span.vtex-product-price-1-x-savingsPercentage")
                        desc_text = desc_elem.text.strip().replace("%", "").replace("-", "")
                        descuento = int(desc_text)
                    except NoSuchElementException:
                        pass

                    # Extraer imagen
                    imagen = None
                    try:
                        img_elem = item.find_element(By.CSS_SELECTOR, "img.vtex-product-summary-2-x-image")
                        imagen = img_elem.get_attribute("src")
                    except NoSuchElementException:
                        pass

                    if nombre and precio and link:
                        resultados.append({
                            "nombre": nombre,
                            "precio": precio,
                            "link": link,
                            "tienda": "estilos",
                            "descuento": descuento,
                            "imagen": imagen
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
        print(f"Error al buscar en Estilos: {e}")
    finally:
        driver.quit()

    return resultados