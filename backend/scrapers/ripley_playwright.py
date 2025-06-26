import asyncio
import re
import random
from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError
from .base_playwright_scraper import BasePlaywrightScraper

class RipleyPlaywrightScraper(BasePlaywrightScraper):
    def __init__(self):
        super().__init__("ripley")

    async def _get_base_url(self):
        # Ripley usa www.ripley.com.pe para busquedas, simple.ripley.com.pe para productos
        # Devolveremos la URL de búsqueda. La URL completa del producto se construye en _extract_data_from_element
        return "https://www.ripley.com.pe"

    async def _navigate_to_search(self, producto: str) -> bool:
        try:
            await self.page.goto(await self._get_base_url() + "/", timeout=self.DEFAULT_TIMEOUT * 2) # Mayor timeout para carga inicial

            # Ripley tiene un input de búsqueda general
            search_input_selector = 'input[type="search"]' # Selector común
            search_input = await self._query_selector(self.page, search_input_selector, timeout=self.DEFAULT_TIMEOUT)

            if not search_input:
                # Probar con un selector más específico si el general falla
                search_input_selector = 'input#search-input'
                search_input = await self._query_selector(self.page, search_input_selector, timeout=self.DEFAULT_TIMEOUT)

            if not search_input:
                print(f"{self.tienda.title()}: Campo de búsqueda no encontrado.")
                return False

            await search_input.fill(producto)
            await search_input.press('Enter')

            # Esperar a que la página de resultados de búsqueda cargue
            # Un indicador puede ser la presencia del contenedor de productos
            await self.page.wait_for_selector("div.catalog-container", timeout=self.DEFAULT_TIMEOUT)
            return True
        except PlaywrightTimeoutError:
            print(f"{self.tienda.title()}: Timeout al navegar o buscar '{producto}'.")
            return False
        except PlaywrightError as e:
            print(f"{self.tienda.title()}: Error de Playwright en navegación/búsqueda: {e}")
            return False

    async def _get_product_elements(self) -> list: # Retorna list[ElementHandle]
        # Los productos están contenidos en 'div.catalog-product-item'
        product_selector = "div.catalog-product-item"
        # Esperar a que al menos un producto esté visible
        try:
            await self.page.wait_for_selector(product_selector, state='visible', timeout=self.DEFAULT_TIMEOUT)
            return await self._query_selector_all(self.page, product_selector)
        except PlaywrightTimeoutError:
            print(f"{self.tienda.title()}: Timeout esperando elementos de producto.")
            return []
        except PlaywrightError as e:
            print(f"{self.tienda.title()}: Error de Playwright obteniendo elementos de producto: {e}")
            return []


    async def _extract_data_from_element(self, element_handle) -> dict | None:
        try:
            nombre_elem = await self._query_selector(element_handle, "div.catalog-product-details__name")
            nombre = await self._get_text_content(nombre_elem)
            if not nombre: return None

            link_elem = await self._query_selector(element_handle, "a.catalog-product-item")
            link_relativo = await self._get_attribute(link_elem, "href")
            if not link_relativo: return None
            # La URL base para productos en Ripley es simple.ripley.com.pe
            link = self._build_full_url("https://simple.ripley.com.pe", link_relativo)

            precio_elem = await self._query_selector(element_handle, "li.catalog-prices__offer-price")
            precio_text = await self._get_text_content(precio_elem, "0")
            precio = self._clean_price(precio_text)
            if precio <= 0: return None

            imagen_elem = await self._query_selector(element_handle, ".images-preview-item.is-active img")
            imagen_src = await self._get_attribute(imagen_elem, "src")
            # La URL base para imágenes puede ser diferente, o pueden ser absolutas.
            # Ripley a veces usa URLs relativas al dominio principal para imágenes.
            imagen = self._build_full_url("https://www.ripley.com.pe", imagen_src) if imagen_src and not imagen_src.startswith('http') else imagen_src

            descuento = None
            descuento_tag_elem = await self._query_selector(element_handle, 'div.catalog-product-details__discount-tag')
            if descuento_tag_elem:
                descuento_texto = await self._get_text_content(descuento_tag_elem)
                match = re.search(r'(\d+)%', descuento_texto)
                if match:
                    descuento = int(match.group(1))

            return {
                'nombre': nombre,
                'precio': precio,
                'link': link,
                'tienda': self.tienda,
                'imagen': imagen,
                'descuento': descuento
            }
        except PlaywrightError as e:
            # print(f"Error extrayendo datos de un elemento en {self.tienda}: {e}")
            return None
        except Exception as ex: # Captura general para errores inesperados en la extracción
            # print(f"Error inesperado extrayendo datos de un elemento en {self.tienda}: {ex}")
            return None

    async def _go_to_next_page(self) -> bool:
        next_button_selector = "a.page-link[aria-label='Siguiente']:not(.disabled)"
        try:
            next_button = await self._query_selector(self.page, next_button_selector)
            if next_button:
                await next_button.click()
                # Esperar a que la URL cambie o que el contenido de la página se actualice.
                # Una espera simple por timeout o por un evento de navegación.
                await self.page.wait_for_load_state('domcontentloaded', timeout=self.DEFAULT_TIMEOUT)
                # Podríamos añadir una espera adicional si el contenido carga dinámicamente después del DOM.
                await self.page.wait_for_timeout(random.randint(1500, 3000)) # Pausa adicional
                return True
            return False
        except PlaywrightTimeoutError:
            print(f"{self.tienda.title()}: Timeout esperando para clickear/cargar siguiente página.")
            return False
        except PlaywrightError: # Otros errores de Playwright al intentar clickear/navegar
            # print(f"{self.tienda.title()}: Error de Playwright al ir a la siguiente página.")
            return False

# Wrapper para ejecutar la función asíncrona desde código síncrono en app.py
def buscar_en_ripley_async_wrapper(producto: str) -> list:
    """
    Wrapper síncrono para el scraper asíncrono de Ripley.
    Este es el punto de entrada que será llamado por app.py.
    """
    scraper = RipleyPlaywrightScraper()
    # asyncio.run() es una forma de ejecutar una corutina desde código síncrono.
    # Crea un nuevo bucle de eventos o usa el existente si está disponible y configurado.
    # Es importante manejar cómo se gestiona el bucle de eventos en una app Flask.
    # Para Flask, a menudo se usa un executor o se integra con un servidor ASGI.
    # Por ahora, para mantener la compatibilidad con la llamada actual desde app.py:
    try:
        # Si ya hay un bucle de eventos corriendo (común en algunos entornos como Jupyter o si Flask usa uno)
        # asyncio.run() puede fallar. Intentar obtener el bucle existente.
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Si el bucle está corriendo, no podemos usar asyncio.run().
            # Esto requeriría una integración más profunda con el bucle de eventos de Flask/servidor.
            # Para una solución simple y si esto se llama en un hilo separado (como con ThreadPoolExecutor):
            # return asyncio.run(scraper.buscar(producto)) # Esto podría fallar si el hilo ya tiene un bucle.
            # Una alternativa es crear un nuevo bucle para este hilo si es necesario:
            # loop = asyncio.new_event_loop()
            # asyncio.set_event_loop(loop)
            # results = loop.run_until_complete(scraper.buscar(producto))
            # loop.close()
            # return results
            # La forma más simple que a veces funciona en hilos:
            return asyncio.run(scraper.buscar(producto))
        else:
            return asyncio.run(scraper.buscar(producto))
    except RuntimeError as e:
        if " asyncio.run() cannot be called from a running event loop" in str(e):
            # Este es un caso común. Necesitaríamos una estrategia diferente si el bucle ya está corriendo.
            # Por ahora, simplemente re-lanzamos para que sea visible el problema.
            # O podríamos intentar un fallback si es apropiado, pero es complejo.
            print("Error: asyncio.run() llamado desde un bucle de eventos ya en ejecución. Se necesita ajuste en app.py.")
            raise e
        else:
            # Otro RuntimeError
            raise e


if __name__ == '__main__':
    # Para pruebas directas del scraper
    start_time_main = time.time()

    # Usar el wrapper síncrono para simular la llamada desde app.py
    # productos_test = buscar_en_ripley_async_wrapper("smart tv")

    # O probar la corutina directamente si se ejecuta este script como principal
    async def main_test():
        scraper_test = RipleyPlaywrightScraper()
        return await scraper_test.buscar("smart tv", max_paginas=2)

    productos_test = asyncio.run(main_test())

    end_time_main = time.time()

    print(f"\n=== RESULTADOS DE PRUEBA ({RipleyPlaywrightScraper().tienda}) ===")
    print(f"Productos encontrados: {len(productos_test)}")
    print(f"Tiempo total: {end_time_main - start_time_main:.2f} segundos")

    if productos_test:
        for i, p_item in enumerate(productos_test[:3]): # Mostrar los primeros 3
            print(f"\nProducto {i+1}:")
            print(f"  Nombre: {p_item['nombre']}")
            print(f"  Precio: S/ {p_item['precio']:.2f}")
            print(f"  Link: {p_item['link']}")
            print(f"  Imagen: {p_item['imagen']}")
            print(f"  Descuento: {p_item.get('descuento')}%" if p_item.get('descuento') else "No disponible")
