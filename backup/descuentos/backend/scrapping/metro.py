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

def buscar_en_metro(producto):
    """Busca un producto en Metro usando Selenium."""
    resultados = []
    user_agents = obtener_user_agents()  # Descomentar si se usa
    if not user_agents:
        return resultados

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

    try:
        driver.get("https://www.metro.pe")

        # Intentar diferentes selectores para el campo de búsqueda
        selectors = [
            "input.vtex-styleguide-9-x-input",
            "input[placeholder='¿Que buscas hoy?']",
            "input.vtex-input",
            "input#downshift-5-input"
        ]

        search_input = None
        for selector in selectors:
            try:
                search_input = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                if search_input:
                    break
            except TimeoutException:
                continue

        if not search_input:
            raise Exception("No se pudo encontrar el campo de búsqueda")
        # Asegurar que el elemento sea interactuable
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
        )

        # Limpiar y enviar la búsqueda
        driver.execute_script("arguments[0].value = '';", search_input)
        search_input.send_keys(producto)
        time.sleep(1)
        search_input.send_keys(Keys.RETURN)
        time.sleep(5)  # Esperar a que la página de resultados comience a cargar

        while True:
            # Esperar a que al menos un producto esté presente
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "section.vtex-product-summary-2-x-container"))
            )

            # Hacer scroll hasta el final de la página para cargar los productos dinámicamente
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

            time.sleep(8)  # Aumentado el tiempo de espera después del scroll
            productos = driver.find_elements(By.CSS_SELECTOR, "section.vtex-product-summary-2-x-container")

            for item in productos:
                try:
                    # Hacer scroll suave hasta el elemento
                    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", item)
                    time.sleep(1)  # Pequeña pausa para asegurar la carga

                    nombre = item.find_element(By.CSS_SELECTOR, "span.vtex-product-summary-2-x-productBrand").text.strip()
                    link = item.find_element(By.CSS_SELECTOR, "a.vtex-product-summary-2-x-clearLink").get_attribute("href")
                    imagen = item.find_element(By.CSS_SELECTOR, "img.vtex-product-summary-2-x-imageNormal").get_attribute("src")

                    # Nueva lógica para extraer precio, similar a Ripley
                    precio = None
                    try:
                        precio_elem = item.find_element(By.CSS_SELECTOR, "span.vtex-product-price-1-x-sellingPriceValue")
                        precio_text = precio_elem.text.strip()
                        # Imprimir el texto del precio para debug
                        
                        # Limpiar el precio
                        precio_text = re.sub(r'[^\d,.]', '', precio_text)
                        precio_text = precio_text.replace(',', '.')
                        
                        # Manejar casos con múltiples puntos
                        if precio_text.count('.') > 1:
                            precio_text = precio_text.replace('.', '', precio_text.count('.') - 1)
                        
                        if precio_text:
                            precio = float(precio_text)
                    except (NoSuchElementException, ValueError) as e:
                        continue
                    if not precio or precio <= 0:
                        continue

                    # Extracción de descuento simplificada
                    descuento = None
                    try:
                        descuento_tag = item.find_element(By.CSS_SELECTOR, 'span.vtex-product-price-1-x-savingsPercentage')
                        descuento_texto = descuento_tag.text.strip()
                        match = re.search(r'(\d+)%', descuento_texto)
                        if match:
                            descuento = int(match.group(1))
                    except NoSuchElementException:
                        pass

                    if nombre and precio and link:
                        resultados.append({
                            'nombre': nombre,
                            'precio': precio,
                            'link': link,
                            'tienda': 'metro',
                            'imagen': imagen,
                            'descuento': descuento
                        })
                except Exception as e:
                    continue

            # Modificación en el manejo del botón "Mostrar más"
            try:
                show_more_button = WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.vtex-search-result-3-x-buttonShowMore button.vtex-button"))
                )
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", show_more_button)
                time.sleep(3)  # Aumentado el tiempo de espera
                driver.execute_script("arguments[0].click();", show_more_button)
                time.sleep(8)  # Aumentado el tiempo de espera después del click
            except (TimeoutException, NoSuchElementException):
            
                break

    except Exception as e:
        print(f"Error al buscar en Metro: {e}")
    finally:
        driver.quit()

    return resultados