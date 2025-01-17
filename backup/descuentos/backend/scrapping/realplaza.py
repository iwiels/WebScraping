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

def extraer_precio(texto):
    nums = re.findall(r'\d+\.?\d*', texto)
    return float(nums[0]) if nums else 0

def calcular_descuento(precio_regular, precio_oferta):
    if precio_regular > 0 and precio_oferta > 0:
        descuento = ((precio_regular - precio_oferta) / precio_regular) * 100
        return round(descuento)
    return 0

def extraer_precio_mejorado(elemento):
    try:
        precio_texto = elemento.get_attribute('innerHTML')
        if not precio_texto:
            precio_texto = elemento.text
        
        # Limpiar el texto de elementos HTML
        precio_texto = re.sub(r'<[^>]+>', '', precio_texto)
        precio_texto = precio_texto.replace('&nbsp;', ' ').strip()
        # Remove commas to handle thousand separators
        precio_texto = precio_texto.replace(',', '')
        
        # Estrategia 1: Buscar formato S/XXX.XX
        patron1 = r'S/\s*(\d+(?:\.\d{2})?)'
        match = re.search(patron1, precio_texto)
        if match:
            return float(match.group(1))
        
        # Estrategia 2: Buscar números con punto decimal
        patron2 = r'(\d+\.\d{2})'
        match = re.search(patron2, precio_texto)
        if match:
            return float(match.group(1))
        
        # Estrategia 3: Buscar cualquier número
        patron3 = r'(\d+)'
        match = re.search(patron3, precio_texto)
        if match:
            return float(match.group(1))
            
    except Exception as e:
        print(f"Error extrayendo precio: {str(e)}")
    return 0

def buscar_en_realplaza(producto):
    resultados = []
    visited_links = set()
    user_agents = obtener_user_agents()
    if not user_agents:
        print("Error: Lista de User-Agents vacía.")
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

    service = Service(executable_path="C:/Users/victo/OneDrive/Documentos/descuentos/backend/scrapping/msedgedriver.exe")
    driver = webdriver.Edge(service=service, options=options)

    try:
        driver.get('https://www.realplaza.com/')
        
        search_input = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.CLASS_NAME, "realplaza-store-components-0-x-omnichannelSearchInput__input"))
        )
        search_input.clear()
        search_input.send_keys(producto)
        search_input.send_keys(Keys.RETURN)

        time.sleep(5)

        pagina_actual = 1
        max_paginas = 10
        
        while pagina_actual <= max_paginas:
            try:
                productos = WebDriverWait(driver, 15).until(
                    EC.presence_of_all_elements_located((By.CLASS_NAME, "vtex-product-summary-2-x-container"))
                )

                for producto in productos:
                    try:
                        # Extraer nombre y marca
                        nombre_elem = producto.find_element(By.CSS_SELECTOR, ".vtex-product-summary-2-x-productBrand")
                        marca_elem = producto.find_element(By.CSS_SELECTOR, ".realplaza-product-custom-0-x-brancNameComponent")
                        nombre = nombre_elem.text.strip()
                        marca = marca_elem.text.strip()

                        # Extraer precios
                        precio_regular = 0
                        precio_oferta = 0
                        
                        try:
                            precio_regular_elem = producto.find_element(By.CSS_SELECTOR, 
                                ".realplaza-product-custom-0-x-productSummaryPrice__Option__RegularPrice")
                            precio_regular = extraer_precio_mejorado(precio_regular_elem)
                        except NoSuchElementException:
                            pass

                        try:
                            precio_oferta_elem = producto.find_element(By.CSS_SELECTOR,
                                ".realplaza-product-custom-0-x-productSummaryPrice__Option__OfferPrice")
                            precio_oferta = extraer_precio_mejorado(precio_oferta_elem)
                        except NoSuchElementException:
                            pass

                        # Solo agregar si tenemos al menos un precio
                        if precio_regular > 0 or precio_oferta > 0:
                            imagen = producto.find_element(By.CSS_SELECTOR, 
                                "img.vtex-product-summary-2-x-imageNormal").get_attribute("src")
                            link = producto.find_element(By.CSS_SELECTOR, 
                                "a.vtex-product-summary-2-x-clearLink").get_attribute("href")
                            if link in visited_links:
                                continue
                            visited_links.add(link)
                            
                            precio_final = precio_oferta if precio_oferta > 0 else precio_regular
                            descuento = None
                            if precio_regular > 0 and precio_oferta > 0:
                                descuento = int(((precio_regular - precio_oferta) / precio_regular) * 100)

                            resultados.append({
                                'nombre': f"{marca} {nombre}".strip(),
                                'precio': precio_final,
                                'link': link,
                                'tienda': 'realplaza',
                                'descuento': descuento,
                                'imagen': imagen
                            })

                    except Exception as e:
                        continue

                # Intentar pasar a la siguiente página
                try:
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(2)
                    next_button = driver.find_element(
                        By.CSS_SELECTOR, 
                        "button.realplaza-rpweb-10-x-paginationButton.realplaza-rpweb-10-x-enabled"
                    )
                    if next_button and next_button.is_enabled():
                        driver.execute_script("arguments[0].click();", next_button)
                        pagina_actual += 1
                        time.sleep(random.uniform(4, 7))
                    else:
                        break
                except NoSuchElementException:
                    break

            except TimeoutException:
                break

    except Exception as e:
        print(f"Error al buscar en Real Plaza: {e}")
    finally:
        driver.quit()

    return resultados
