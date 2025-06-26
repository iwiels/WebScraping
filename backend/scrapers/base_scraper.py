import re
import time
import random
import os
from abc import ABC, abstractmethod
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

class BaseScraper(ABC):
    """
    Clase base para todos los scrapers de tiendas.
    Proporciona funcionalidad común como configuración del driver,
    manejo de user-agents, utilidades de limpieza de precios, etc.
    """
    
    def __init__(self, tienda_nombre):
        self.tienda = tienda_nombre
        self.driver = None
        self.user_agents = self._obtener_user_agents()
    
    def _obtener_user_agents(self):
        """Obtiene la lista de user agents desde el archivo."""
        user_agents = []
        current_dir = os.path.dirname(os.path.abspath(__file__))
        filepath = os.path.join(current_dir, "user_agents.txt")
        
        try:
            with open(filepath, 'r') as file:
                for line in file:
                    user_agents.append(line.strip())
        except FileNotFoundError:
            print(f"Error: Archivo '{filepath}' no encontrado.")
            user_agents = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            ]
        return user_agents
    
    def _setup_driver(self):
        """Configura y retorna el driver de Selenium con opciones optimizadas."""
        if not self.user_agents:
            print("Error: Lista de User-Agents vacía.")
            return None
            
        options = ChromeOptions()
        options.add_argument("--headless")
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-software-rasterizer')
        options.add_argument('--window-size=1920,1080')
        
        try:
            service = ChromeService(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": random.choice(self.user_agents)
            })
            return driver
        except Exception as e:
            print(f"Error al configurar el driver para {self.tienda}: {e}")
            return None
    
    def _clean_price(self, price_text):
        """Utilidad para limpiar texto de precios y convertir a float."""
        try:
            cleaned = re.sub(r'[^\d.]', '', str(price_text))
            return float(cleaned) if cleaned else 0.0
        except (ValueError, TypeError):
            return 0.0
    
    def _wait_for_element(self, selector, timeout=15, by=By.CSS_SELECTOR):
        """Espera por un elemento y lo retorna."""
        try:
            return WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, selector))
            )
        except TimeoutException:
            return None
    
    def _wait_for_clickable_element(self, selector, timeout=15, by=By.CSS_SELECTOR):
        """Espera por un elemento clickeable y lo retorna."""
        try:
            return WebDriverWait(self.driver, timeout).until(
                EC.element_to_be_clickable((by, selector))
            )
        except TimeoutException:
            return None
    
    def _safe_find_element(self, element, selector, by=By.CSS_SELECTOR):
        """Busca un elemento de forma segura, retorna None si no se encuentra."""
        try:
            return element.find_element(by, selector)
        except NoSuchElementException:
            return None
    
    def _safe_get_text(self, element):
        """Obtiene el texto de un elemento de forma segura."""
        try:
            return element.text.strip() if element else ""
        except AttributeError:
            return ""
    
    def _safe_get_attribute(self, element, attribute):
        """Obtiene un atributo de un elemento de forma segura."""
        try:
            return element.get_attribute(attribute) if element else ""
        except AttributeError:
            return ""
    
    def _build_full_url(self, base_url, relative_url):
        """Construye una URL completa a partir de una URL base y una relativa."""
        if not relative_url:
            return ""
        if relative_url.startswith('http'):
            return relative_url
        return base_url.rstrip('/') + '/' + relative_url.lstrip('/')
    
    # Métodos abstractos que deben ser implementados por cada scraper
    @abstractmethod
    def _get_base_url(self):
        """Retorna la URL base de la tienda."""
        pass
    
    @abstractmethod
    def _navigate_to_search(self, producto):
        """Navega a la página de la tienda y realiza la búsqueda del producto."""
        pass
    
    @abstractmethod
    def _get_product_elements(self):
        """Retorna la lista de elementos de producto en la página actual."""
        pass
    
    @abstractmethod
    def _extract_data_from_element(self, element):
        """Extrae los datos (nombre, precio, link, etc.) de un elemento de producto."""
        pass
    
    @abstractmethod
    def _go_to_next_page(self):
        """Navega a la siguiente página. Retorna True si fue exitoso, False si no hay más páginas."""
        pass
    
    def _process_page(self, pagina_actual):
        """Procesa una página individual y retorna los productos encontrados."""
        print(f"{self.tienda.title()}: procesando página {pagina_actual}")
        
        product_elements = self._get_product_elements()
        if not product_elements:
            print(f"{self.tienda.title()}: No se encontraron productos en la página {pagina_actual}")
            return []
        
        productos_pagina = []
        for element in product_elements:
            data = self._extract_data_from_element(element)
            if data and self._is_valid_product_data(data):
                productos_pagina.append(data)
        
        print(f"{self.tienda.title()}: {len(productos_pagina)} productos encontrados en página {pagina_actual}")
        return productos_pagina
    
    def buscar(self, producto, max_paginas=10):
        """Método principal para buscar productos."""
        resultados = []
        self.driver = self._setup_driver()
        
        if not self.driver:
            return resultados
        
        try:
            print(f"Iniciando búsqueda en {self.tienda.title()} para: {producto}")
            self._navigate_to_search(producto)
            time.sleep(random.uniform(3, 5))
            
            for pagina_actual in range(1, max_paginas + 1):
                productos_pagina = self._process_page(pagina_actual)
                resultados.extend(productos_pagina)
                
                if pagina_actual < max_paginas and not self._go_to_next_page():
                    print(f"{self.tienda.title()}: No hay más páginas disponibles")
                    break
                
                if pagina_actual < max_paginas:
                    time.sleep(random.uniform(3, 6))
            
            print(f"{self.tienda.title()}: Búsqueda completada. Total: {len(resultados)} productos")
            
        except Exception as e:
            print(f"Error en el scraper de {self.tienda}: {e}")
        finally:
            if self.driver:
                self.driver.quit()
        
        return resultados
    
    def _is_valid_product_data(self, data):
        """Valida que los datos del producto sean válidos."""
        return (
            data and 
            isinstance(data, dict) and
            data.get('nombre') and 
            data.get('precio', 0) > 0 and
            data.get('link')
        )
