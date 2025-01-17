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

def buscar_en_plazavea(producto):
    """Busca un producto en Plaza Vea usando Selenium."""
    resultados = []
    user_agents = obtener_user_agents()
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

    service = Service(executable_path="C:/Users/victo/OneDrive/Documentos/descuentos/backend/scrapping/msedgedriver.exe")
    driver = webdriver.Edge(service=service, options=options)

    try:
        driver.get("https://www.plazavea.com.pe")
        
        # Esperar y encontrar el campo de búsqueda
        search_input = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.ID, "search_box"))
        )
        search_input.clear()
        search_input.send_keys(producto)
        search_input.send_keys(Keys.RETURN)

        time.sleep(3)

        # ...existing code for pagination and product extraction...
        pagina_actual = 1
        max_paginas = 10

        while pagina_actual <= max_paginas:
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "Showcase--non-food"))
                )

                productos = driver.find_elements(By.CLASS_NAME, "Showcase--non-food")

                for item in productos:
                    try:
                        nombre = item.find_element(By.CLASS_NAME, "Showcase__name").text.strip()
                        marca = item.find_element(By.CLASS_NAME, "brand").text.strip()
                        link = item.find_element(By.CLASS_NAME, "Showcase__link").get_attribute("href")
                        imagen = item.find_element(By.CLASS_NAME, "showcase__image").get_attribute("src")
                        
                        # Extraer precios
                        precio_regular = None
                        precio_oferta = None
                        precio_oh = None
                        
                        try:
                            precio_regular = float(re.sub(r'[^\d.]', '', 
                                item.find_element(By.CLASS_NAME, "Showcase__oldPrice").text))
                        except:
                            pass
                            
                        try:
                            precio_oferta = float(re.sub(r'[^\d.]', '', 
                                item.find_element(By.CLASS_NAME, "Showcase__salePrice").text))
                        except:
                            pass
                            
                        try:
                            precio_oh = float(re.sub(r'[^\d.]', '', 
                                item.find_element(By.CLASS_NAME, "Showcase__ohPrice").text))
                        except:
                            pass
                        
                        # Usar el precio más bajo disponible
                        precios = [p for p in [precio_regular, precio_oferta, precio_oh] if p is not None]
                        if precios:
                            precio_final = min(precios)
                            
                            # Calcular descuento
                            descuento = None
                            if precio_regular and precio_final < precio_regular:
                                descuento = int(((precio_regular - precio_final) / precio_regular) * 100)
                            
                            resultados.append({
                                'nombre': f"{marca} {nombre}".strip(),
                                'precio': precio_final,
                                'link': link,
                                'tienda': 'plazavea',
                                'imagen': imagen,
                                'descuento': descuento
                            })

                    except Exception as e:
                        continue

                # Intentar pasar a la siguiente página
                try:
                    next_button = driver.find_element(By.CSS_SELECTOR, "button.page-link[aria-label='Siguiente']")
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
        print(f"Error al buscar en Plaza Vea: {e}")
    finally:
        driver.quit()

    return resultados
