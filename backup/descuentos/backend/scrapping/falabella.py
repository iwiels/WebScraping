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
from urllib.parse import urljoin, urlparse
from collections import OrderedDict

class ImageExtractor:
    VALID_IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp', '.gif')
    FALLBACK_IMAGE_URL = "URL_DE_IMAGEN_POR_DEFECTO"

    def __init__(self, base_url="https://www.falabella.com.pe/falabella-pe/"):
        self.base_url = base_url
        self.url_cache = OrderedDict()

    def extract_image(self, item):
        strategies = [
            self._extract_from_picture_img,
            self._extract_from_picture_source,
            self._extract_from_img,
            self._extract_from_lazy_loading_attributes,
            self._extract_from_section_img,
        ]

        for strategy in strategies:
            try:
                image_url = strategy(item)
                if image_url:
                    return self._process_image_url(image_url)
            except NoSuchElementException:
                continue

        return self.FALLBACK_IMAGE_URL

    def _extract_from_picture_img(self, item):
        img_element = item.find_element(By.CSS_SELECTOR, "picture img")
        return self._get_image_url_from_img_element(img_element)

    def _extract_from_picture_source(self, item):
        source_element = item.find_element(By.CSS_SELECTOR, "picture source")
        return self._get_image_url_from_srcset(source_element.get_attribute("srcset"))

    def _extract_from_img(self, item):
        img_element = item.find_element(By.CSS_SELECTOR, ".image-wrapper img")
        return self._get_image_url_from_img_element(img_element)

    def _extract_from_lazy_loading_attributes(self, item):
        img_element = item.find_element(By.CSS_SELECTOR, ".image-wrapper img")
        image_url = img_element.get_attribute("data-src")
        if not image_url or image_url == "":
            srcset = img_element.get_attribute("data-srcset")
            if srcset:
                image_url = self._get_image_url_from_srcset(srcset)
        return image_url

    def _extract_from_section_img(self, item):
        """
        Extrae la URL de la imagen de un elemento <img> dentro de una <section>
        con clases específicas. Maneja casos donde la imagen está directamente
        dentro de <section> o dentro de un <picture> en <section>.
        """
        try:
            # Intenta encontrar la imagen directamente dentro de <section>
            img_element = item.find_element(By.XPATH, ".//div[contains(@class,'pod-head')]/div/section[contains(@class,'layout_grid-view') and contains(@class,'layout_view_4_GRID')]/img")
            return self._get_image_url_from_img_element(img_element)
        except NoSuchElementException:
            try:
                # Si no se encuentra directamente, busca dentro de <picture>
                img_element = item.find_element(By.XPATH, ".//div[contains(@class,'pod-head')]/div/section[contains(@class,'layout_grid-view') and contains(@class,'layout_view_4_GRID')]/picture/img")
                return self._get_image_url_from_img_element(img_element)
            except NoSuchElementException:
                return None

    def _get_image_url_from_img_element(self, img_element):
        image_url = img_element.get_attribute("src")
        if not image_url or image_url == "":
            srcset = img_element.get_attribute("srcset")
            if srcset:
                image_url = self._get_image_url_from_srcset(srcset)
        return image_url

    def _get_image_url_from_srcset(self, srcset):
        if not srcset:
            return None

        urls = []
        for srcset_part in srcset.split(','):
            parts = srcset_part.strip().split()
            if len(parts) > 0:
                url = parts[0]
                if self._is_valid_image_url(url):
                    urls.append(url)

        return urls[-1] if urls else None

    def _is_valid_image_url(self, url):
        return url.lower().endswith(self.VALID_IMAGE_EXTENSIONS) and url.startswith('http')

    def _process_image_url(self, image_url):
        parsed_url = urlparse(image_url)

        if not parsed_url.netloc:
            image_url = urljoin(self.base_url, image_url)

        if 'cdn-cgi/imagedelivery' in image_url:
            image_url = re.sub(
                r'(width=\d+,height=\d+,quality=\d+)',
                'width=480,height=480,quality=100',
                image_url
            )

        if len(self.url_cache) >= 100:
            self.url_cache.popitem(last=False)
        self.url_cache[image_url] = None

        return image_url

def buscar_en_falabella(producto):
    resultados = []
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

    service = Service(executable_path="backup/descuentos/backend/scrapping/msedgedriver.exe")
    driver = webdriver.Edge(service=service, options=options)

    try:
        driver.get("https://www.falabella.com.pe/falabella-pe")
        image_extractor = ImageExtractor()  # Initialize the image extractor

        # Cierra modal de ubicación si aparece
        try:
            WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button#acc-alert-deny"))
            ).click()
        except TimeoutException:
            pass

        try:
            search_input = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable((By.ID, "testId-SearchBar-Input"))
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
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div[id='testId-searchResults-products']"))
                )
                items = driver.find_elements(By.CSS_SELECTOR, "a.pod-link[data-pod='catalyst-pod']")

            except TimeoutException:
                break

            for item in items:
                nombre = "Nombre no encontrado"
                try:
                    nombre = item.find_element(By.CSS_SELECTOR, "b.pod-subTitle").text.strip()
                except NoSuchElementException:
                    pass

                link = item.get_attribute("href")

                precio = None
                try:
                    price_li = item.find_element(By.CSS_SELECTOR, "li.prices-0 span")
                    price_text = price_li.text.strip()
                    precio = float(re.sub(r"[^\d.]", "", price_text))
                except (NoSuchElementException, ValueError):
                    pass

                descuento = None
                try:
                    desc_elem = item.find_element(By.CSS_SELECTOR, "div.discount-badge span")
                    desc_text = desc_elem.text.strip().replace("%", "").replace("-", "")
                    descuento = int(desc_text)
                except (NoSuchElementException, ValueError):
                    pass

                # Usar el ImageExtractor para obtener la imagen
                imagen = image_extractor.extract_image(item)

                if nombre != "Nombre no encontrado" and precio and link:
                    resultados.append({
                        "nombre": nombre,
                        "precio": precio,
                        "link": link,
                        "tienda": "falabella",
                        "descuento": descuento,
                        "imagen": imagen
                    })

            try:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(5)
                next_button = driver.find_element(By.CSS_SELECTOR, "button#testId-pagination-top-arrow-right")
                if next_button.is_enabled():
                    driver.execute_script("arguments[0].click();", next_button)
                    pagina_actual += 1
                    time.sleep(random.uniform(4, 7))
                else:
                    break
            except (NoSuchElementException, TimeoutException):
                break

    except Exception as e:
        print(f"Error al buscar en Falabella: {e}")
    finally:
        driver.quit()

    return resultados