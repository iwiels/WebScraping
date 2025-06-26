import time
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from .base_scraper import BaseScraper

class OechsleScraper(BaseScraper):
    """Scraper para la tienda Oechsle usando la clase base."""
    
    def __init__(self):
        super().__init__("oechsle")
    
    def _get_base_url(self):
        """Retorna la URL base de Oechsle."""
        return "https://www.oechsle.pe"
    
    def _navigate_to_search(self, producto):
        """Navega a Oechsle y realiza la búsqueda del producto."""
        self.driver.get(self._get_base_url())
        print("Accediendo a Oechsle...")
        
        search_input = self._wait_for_clickable_element("input.biggy-autocomplete__input")
        if not search_input:
            raise TimeoutException("No se pudo encontrar el campo de búsqueda en Oechsle")
        
        search_input.clear()
        search_input.send_keys(producto)
        search_input.send_keys(Keys.RETURN)
        print(f"Buscando: {producto}")
    
    def _get_product_elements(self):
        """Retorna la lista de elementos de producto en la página actual."""
        # Esperar a que carguen los productos
        if not self._wait_for_element("div.product", timeout=15):
            return []
        
        return self.driver.find_elements(By.CSS_SELECTOR, "div.product")
    
    def _extract_data_from_element(self, item):
        """Extrae los datos de un elemento de producto de Oechsle."""
        try:
            # Extraer nombre
            nombre_elem = self._safe_find_element(item, "span.fz-15.prod-name")
            nombre = self._safe_get_text(nombre_elem)
            if not nombre:
                return None
            
            # Extraer link
            link_elem = self._safe_find_element(item, "a.prod-image")
            link_relativo = self._safe_get_attribute(link_elem, "href")
            if not link_relativo:
                return None
            
            link = self._build_full_url(self._get_base_url(), link_relativo)
            
            # Extraer precio
            precio_elem = self._safe_find_element(item, "span.BestPrice")
            precio_texto = self._safe_get_text(precio_elem)
            precio = self._clean_price(precio_texto)
            
            if precio <= 0:
                return None
            
            # Extraer imagen
            imagen_elem = self._safe_find_element(item, "div.productImage img")
            imagen = self._safe_get_attribute(imagen_elem, "src")
            if imagen and not imagen.startswith('http'):
                imagen = self._build_full_url(self._get_base_url(), imagen)
            
            # Extraer descuento (si existe)
            descuento_porcentaje = None
            descuento_elem = self._safe_find_element(item, "div.product-discount-percent")
            if descuento_elem:
                descuento_texto = self._safe_get_text(descuento_elem)
                try:
                    descuento_porcentaje = int(re.sub(r'[^\d]', '', descuento_texto))
                except (ValueError, TypeError):
                    descuento_porcentaje = None
            
            return {
                'nombre': nombre,
                'precio': precio,
                'link': link,
                'tienda': self.tienda,
                'imagen': imagen,
                'descuento': descuento_porcentaje
            }
            
        except Exception as e:
            print(f"Error extrayendo datos de producto en Oechsle: {e}")
            return None
    
    def _go_to_next_page(self):
        """Navega a la siguiente página en Oechsle."""
        try:
            # Buscar el botón de siguiente página
            next_button = self._safe_find_element(
                self.driver, 
                "a.page-link.next:not(.disabled)"
            )
            
            if next_button:
                # Usar JavaScript para hacer clic para evitar problemas de visibilidad
                self.driver.execute_script("arguments[0].click();", next_button)
                time.sleep(2)  # Esperar a que cargue la nueva página
                return True
            
            return False
            
        except Exception as e:
            print(f"Error navegando a la siguiente página en Oechsle: {e}")
            return False

# Función de compatibilidad con el código existente
def buscar_en_oechsle(producto):
    """Función de compatibilidad para mantener la interfaz existente."""
    scraper = OechsleScraper()
    return scraper.buscar(producto)
