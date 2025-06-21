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

def buscar_en_tailoy(producto):
    """Busca un producto en Tailoy usando Selenium y recorre hasta 10 páginas de resultados."""
    user_agents = obtener_user_agents()
    if not user_agents:
        print("Error: Lista de User-Agents vacía.")
        return []

    options = ChromeOptions()
    options.add_argument("--headless")
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    
    resultados = []
    
    try:
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)

        driver.get("https://www.tailoy.com.pe/")
        
        search_input = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "input.vtex-styleguide-9-x-input"))
        )

        search_input.clear()
        search_input.send_keys(producto)
        search_input.send_keys(Keys.RETURN)

        pagina_actual = 1
        max_paginas = 10

        while pagina_actual <= max_paginas:
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.product-item-info"))
                )
                items = driver.find_elements(By.CSS_SELECTOR, "div.product-item-info")
            except TimeoutException:
                break

            for item in items:
                try:
                    # Extraer nombre
                    nombre_elem = item.find_element(By.CSS_SELECTOR, "a.product-item-link")
                    nombre = nombre_elem.text.strip()

                    # Extraer link
                    link = nombre_elem.get_attribute("href")

                    # Extraer precio
                    precio = None
                    try:
                        precio_elem = item.find_element(By.CSS_SELECTOR, "span.price")
                        precio_text = precio_elem.text.strip()
                        precio = float(re.sub(r"[^\d.]", "", precio_text))
                    except (NoSuchElementException, ValueError):
                        continue

                    # Extraer imagen
                    imagen = None
                    try:
                        img_elem = item.find_element(By.CSS_SELECTOR, "img.product-image-photo")
                        imagen = img_elem.get_attribute("src")
                        if not imagen:
                            # Buscar dentro del contenedor de imagen
                            img_container = item.find_element(By.CSS_SELECTOR, "span.product-image-wrapper img")
                            imagen = img_container.get_attribute("src")
                    except NoSuchElementException:
                        try:
                            # Intento alternativo usando el contenedor de imagen
                            img_container = item.find_element(By.CSS_SELECTOR, "span.product-image-container")
                            img_elem = img_container.find_element(By.TAG_NAME, "img")
                            imagen = img_elem.get_attribute("src")
                        except NoSuchElementException:
                            imagen = None
                    # También extraer el descuento si existe
                    descuento = None
                    try:
                        descuento_elem = item.find_element(By.CSS_SELECTOR, "span.price-percentage .discount-value")
                        descuento_text = descuento_elem.text.strip().replace("%", "").replace("-", "").strip()
                        descuento = int(descuento_text)
                    except (NoSuchElementException, ValueError):
                        pass
                
                    # Extraer marca
                    marca = None
                    try:
                        marca_elem = item.find_element(By.CSS_SELECTOR, "div.brand-label span.label")
                        marca = marca_elem.text.strip()
                    except NoSuchElementException:
                        pass

                    if nombre and precio and link:
                        resultados.append({
                            "nombre": nombre,
                            "precio": precio,
                            "link": link,
                            "tienda": "tailoy",
                            "imagen": imagen,
                            "marca": marca,
                            "descuento": descuento
                        })
                except Exception as e:
                    continue

            try:
                # Buscar botón siguiente
                next_button = driver.find_element(By.CSS_SELECTOR, "a.next")
                if next_button and next_button.is_enabled():
                    driver.execute_script("arguments[0].click();", next_button)
                    pagina_actual += 1
                    time.sleep(random.uniform(4, 7))
                else:
                    break
            except NoSuchElementException:
                break

    except Exception as e:
        print(f"Error al buscar en Tailoy: {e}")
        return resultados
    finally:
        if 'driver' in locals():
            driver.quit()

    return resultados