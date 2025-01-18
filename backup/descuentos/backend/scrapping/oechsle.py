import os
import time
import random
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from .ripley import obtener_user_agents

def buscar_en_oechsle(producto):
    resultados = []
    user_agents = obtener_user_agents()
    if not user_agents:
        print("Error: Lista de User-Agents vacía.")
        return resultados

    options = ChromeOptions()
    options.add_argument("--headless")
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')

    try:
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)

        driver.get("https://www.oechsle.pe/")
        print("Accediendo a Oechsle...")
        try:
            search_input = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "input.biggy-autocomplete__input"))
            )
        except TimeoutException:
            driver.quit()
            return resultados

        search_input.clear()
        search_input.send_keys(producto)
        search_input.send_keys(Keys.RETURN)
        print(f"Buscando: {producto}")

        time.sleep(5)  # Esperar a que cargue la página de resultados

        pagina_actual = 1
        max_paginas = 10
        while pagina_actual <= max_paginas:
            try:
                # Esperar a que carguen los productos
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.product"))
                )
                items = driver.find_elements(By.CSS_SELECTOR, "div.product")
            except TimeoutException:
                
                break

            for item in items:
                try:
                    # Extraer nombre
                    nombre_elem = item.find_element(By.CSS_SELECTOR, "span.fz-15.prod-name")
                    nombre = nombre_elem.text.strip()
                
                    # Extraer link
                    link_elem = item.find_element(By.CSS_SELECTOR, "a.prod-image")
                    link = link_elem.get_attribute("href")

                    # Extraer precio
                    precio_elem = item.find_element(By.CSS_SELECTOR, "span.BestPrice")
                    precio_text = precio_elem.text.strip()
                    precio = float(re.sub(r"[^\d.]", "", precio_text))

                    # Extraer descuento (si existe)
                    descuento = None
                    try:
                        precio_lista_elem = item.find_element(By.CSS_SELECTOR, "span.ListPrice")
                        precio_lista_text = precio_lista_elem.text.strip()
                        precio_lista = float(re.sub(r"[^\d.]", "", precio_lista_text))
                        descuento = int(((precio_lista - precio) / precio_lista) * 100)
                    except NoSuchElementException:
                        pass

                    # Extraer imagen
                    imagen_elem = item.find_element(By.CSS_SELECTOR, "div.productImage img")
                    imagen = imagen_elem.get_attribute("src")

                    if nombre and precio and link:
                        resultados.append({
                            "nombre": nombre,
                            "precio": precio,
                            "link": link,
                            "tienda": "oechsle",
                            "descuento": descuento,
                            "imagen": imagen
                        })

                except Exception as e:
                    continue

            try:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)

                # Actualizar selector del botón siguiente
                next_button = driver.find_element(By.CSS_SELECTOR, "a.page-link.next")
                if next_button and next_button.is_enabled():
                    driver.execute_script("arguments[0].click();", next_button)
                    pagina_actual += 1
                    time.sleep(random.uniform(4, 7))
                else:
                    break
            except (NoSuchElementException, TimeoutException):
                break

    except Exception as e:
        print(f"Error al buscar en Oechsle: {e}")
    finally:
        driver.quit()

    return resultados