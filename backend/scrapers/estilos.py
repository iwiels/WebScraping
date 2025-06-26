import asyncio
import time
import random
import re
from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError
from .base_playwright_scraper import BasePlaywrightScraper

class EstilosPlaywrightScraper(BasePlaywrightScraper):
    def __init__(self):
        super().__init__("estilos")

    async def _get_base_url(self):
        return "https://www.estilos.com.pe"

    async def _navigate_to_search(self, producto: str) -> bool:
        base_url_val = await self._get_base_url()
        await self.page.goto(base_url_val + "/", timeout=self.DEFAULT_TIMEOUT * 2)

        search_input_selector = "input.vtex-styleguide-9-x-input" # Selector principal para VTEX
        try:
            await self.page.fill(search_input_selector, producto, timeout=self.DEFAULT_TIMEOUT)
            await self.page.press(search_input_selector, "Enter")
            # Esperar a que la página de resultados cargue (presencia de items de producto)
            await self.page.wait_for_selector("div.vtex-search-result-3-x-galleryItem", timeout=self.DEFAULT_TIMEOUT)
            return True
        except PlaywrightTimeoutError:
            print(f"{self.tienda.title()}: Timeout al buscar '{producto}'.")
            return False
        except PlaywrightError as e:
            print(f"{self.tienda.title()}: Error de Playwright en búsqueda: {e}")
            return False

    async def _get_product_elements(self) -> list:
        # El contenedor de productos en Estilos (VTEX)
        product_item_selector = "div.vtex-search-result-3-x-galleryItem"
        try:
            # Esperar a que al menos un producto esté visible
            await self.page.wait_for_selector(product_item_selector, state='visible', timeout=self.DEFAULT_TIMEOUT)
            return await self.page.query_selector_all(product_item_selector)
        except PlaywrightTimeoutError:
            print(f"{self.tienda.title()}: Timeout esperando elementos de producto.")
            return []
        except PlaywrightError as e:
            print(f"{self.tienda.title()}: Error de Playwright obteniendo elementos de producto: {e}")
            return []

    async def _extract_data_from_element(self, element_handle) -> dict | None:
        try:
            nombre_elem = await self._query_selector(element_handle, "span.vtex-product-summary-2-x-productBrand")
            nombre = await self._get_text_content(nombre_elem)
            if not nombre: return None

            link_elem = await self._query_selector(element_handle, "a.vtex-product-summary-2-x-clearLink")
            raw_link = await self._get_attribute(link_elem, "href")
            link = self._build_full_url(await self._get_base_url(), raw_link)

            precio_elem = await self._query_selector(element_handle, "span.vtex-product-price-1-x-sellingPriceValue")
            precio_text = await self._get_text_content(precio_elem)
            precio = self._clean_price(precio_text)
            if precio <= 0: return None

            descuento = None
            descuento_elem = await self._query_selector(element_handle, "span.vtex-product-price-1-x-savingsPercentage")
            if descuento_elem:
                desc_text = await self._get_text_content(descuento_elem)
                match = re.search(r'(\d+)%', desc_text) # VTEX suele mostrar descuentos como "(X%)" o "X%"
                if match: descuento = int(match.group(1))

            imagen_elem = await self._query_selector(element_handle, "img.vtex-product-summary-2-x-image")
            raw_imagen = await self._get_attribute(imagen_elem, "src")
            imagen = self._build_full_url(await self._get_base_url(), raw_imagen) if raw_imagen else None

            return {
                "nombre": nombre, "precio": precio, "link": link,
                "tienda": self.tienda, "descuento": descuento, "imagen": imagen
            }
        except PlaywrightError as e:
            # print(f"Error extrayendo datos de {self.tienda}: {e}")
            return None

    async def _go_to_next_page(self) -> bool:
        # Botón de "Siguiente" en VTEX
        next_button_selector = "a.page-link[aria-label='Siguiente']"
        try:
            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight*0.8)") # Scroll para visibilidad
            await self.page.wait_for_timeout(500)

            next_button = await self.page.query_selector(next_button_selector)
            if next_button: # No se necesita is_enabled() para 'a' si es clickable
                await next_button.click(timeout=self.DEFAULT_TIMEOUT)
                await self.page.wait_for_load_state('domcontentloaded', timeout=self.DEFAULT_TIMEOUT)
                await self.page.wait_for_timeout(random.randint(2000, 3500)) # Pausa post-navegación
                return True
            return False
        except PlaywrightTimeoutError:
            # print(f"{self.tienda.title()}: Timeout/Botón siguiente no encontrado.")
            return False
        except PlaywrightError as e:
            # print(f"{self.tienda.title()}: Error de Playwright al ir a siguiente página: {e}")
            return False

def buscar_en_estilos(producto: str) -> list:
    scraper = EstilosPlaywrightScraper()
    # Gestión del bucle de eventos similar a otros scrapers de Playwright
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            return asyncio.run(scraper.buscar(producto))
        else:
            return asyncio.run(scraper.buscar(producto))
    except RuntimeError as e:
        if "cannot be called from a running event loop" in str(e):
            print(f"ADVERTENCIA ({scraper.tienda}): Intentando ejecutar en un nuevo bucle de eventos.")
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                results = new_loop.run_until_complete(scraper.buscar(producto))
            finally:
                new_loop.close()
                asyncio.set_event_loop(None)
            return results
        raise e

if __name__ == '__main__':
    async def main_test_estilos():
        scraper = EstilosPlaywrightScraper()
        return await scraper.buscar("zapatillas", max_paginas=2)

    start_time_main = time.time()
    productos_test = asyncio.run(main_test_estilos())
    end_time_main = time.time()

    print(f"\n=== RESULTADOS DE PRUEBA ({EstilosPlaywrightScraper().tienda}) ===")
    print(f"Productos encontrados: {len(productos_test)}")
    print(f"Tiempo total: {end_time_main - start_time_main:.2f} segundos")
    if productos_test:
        for i, p_item in enumerate(productos_test[:2]): # Mostrar los primeros 2
            print(f"\nProducto {i+1}:")
            print(f"  Nombre: {p_item['nombre']}")
            print(f"  Precio: S/ {p_item['precio']:.2f}")
            print(f"  Link: {p_item['link']}")
            print(f"  Imagen: {p_item['imagen']}")
            print(f"  Descuento: {p_item.get('descuento')}%" if p_item.get('descuento') else "No disponible")