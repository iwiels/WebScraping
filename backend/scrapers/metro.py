import asyncio
import time
import random
import re
from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError
from .base_playwright_scraper import BasePlaywrightScraper

class MetroPlaywrightScraper(BasePlaywrightScraper):
    def __init__(self):
        super().__init__("metro")
        self.processed_product_ids = set()

    async def _get_base_url(self):
        return "https://www.metro.pe"

    def _clean_price_metro(self, price_text: str) -> float: # Sobrescribir o usar el de la base si es compatible
        return super()._clean_price(price_text) # Asumiendo que el de la base es suficiente

    async def _navigate_to_search(self, producto: str) -> bool:
        base_url_val = await self._get_base_url()
        await self.page.goto(base_url_val + "/", timeout=self.DEFAULT_TIMEOUT * 2)

        search_selectors = [
            "input.vtex-styleguide-9-x-input",
            "input[placeholder='¿Que buscas hoy?']",
            "input.vtex-input",
            "input[id^='downshift-'][type='text']" # Para IDs dinámicos como downshift-0-input
        ]

        search_input_element = None
        for selector in search_selectors:
            try:
                element = await self.page.query_selector(selector)
                if element and await element.is_visible() and await element.is_enabled():
                    search_input_element = element
                    break
            except PlaywrightError:
                continue

        if not search_input_element:
            print(f"{self.tienda.title()}: Campo de búsqueda no encontrado con selectores probados.")
            return False

        try:
            await search_input_element.fill(producto, timeout=self.DEFAULT_TIMEOUT)
            await self.page.wait_for_timeout(random.randint(300,700)) # Pequeña pausa antes de enter
            await search_input_element.press("Enter")
            await self.page.wait_for_selector("section.vtex-product-summary-2-x-container", timeout=self.DEFAULT_TIMEOUT)
            return True
        except PlaywrightTimeoutError:
            print(f"{self.tienda.title()}: Timeout al buscar '{producto}'.")
            return False
        except PlaywrightError as e:
            print(f"{self.tienda.title()}: Error de Playwright en búsqueda: {e}")
            return False

    async def _get_product_elements(self) -> list:
        product_selector = "section.vtex-product-summary-2-x-container"
        try:
            await self.page.wait_for_selector(product_selector, state='visible', timeout=self.DEFAULT_TIMEOUT)
            # Scroll para cargar más productos si es carga infinita inicial
            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await self.page.wait_for_timeout(random.randint(2500,4500)) # Espera para carga post-scroll
            return await self.page.query_selector_all(product_selector)
        except PlaywrightTimeoutError:
            # print(f"{self.tienda.title()}: Timeout esperando elementos de producto.")
            return []


    async def _extract_data_from_element(self, element_handle) -> dict | None:
        raw_link_elem = await self._query_selector(element_handle, "a.vtex-product-summary-2-x-clearLink")
        raw_link = await self._get_attribute(raw_link_elem, "href")
        if not raw_link: return None

        # Generar ID de producto para evitar duplicados
        product_id_match = re.search(r'/([^/]+)/p$', raw_link)
        product_id = product_id_match.group(1) if product_id_match else raw_link

        if product_id in self.processed_product_ids:
            return None

        # Scroll suave al elemento para visibilidad (puede ayudar con lazy loading de imágenes)
        try:
            await element_handle.scroll_into_view_if_needed(timeout=5000) # Corto timeout para scroll
            await self.page.wait_for_timeout(random.randint(200,500)) # Pausa muy corta
        except PlaywrightError: # Continuar si el scroll falla
            pass

        nombre_elem = await self._query_selector(element_handle, "span.vtex-product-summary-2-x-productBrand")
        nombre = await self._get_text_content(nombre_elem)
        if not nombre: return None

        link = self._build_full_url(await self._get_base_url(), raw_link)

        img_elem = await self._query_selector(element_handle, "img.vtex-product-summary-2-x-imageNormal")
        raw_imagen = await self._get_attribute(img_elem, "src")
        imagen = self._build_full_url(await self._get_base_url(), raw_imagen) if raw_imagen else None

        precio_elem = await self._query_selector(element_handle, "span.vtex-product-price-1-x-sellingPriceValue")
        precio_text = await self._get_text_content(precio_elem)
        precio = self._clean_price_metro(precio_text) # Usar _clean_price_metro si es diferente al base
        if precio <= 0: return None

        descuento = None
        descuento_elem = await self._query_selector(element_handle, 'span.vtex-product-price-1-x-savingsPercentage')
        if descuento_elem:
            desc_text = await self._get_text_content(descuento_elem)
            match = re.search(r'(\d+)%', desc_text)
            if match: descuento = int(match.group(1))

        self.processed_product_ids.add(product_id)
        return {
            'nombre': nombre, 'precio': precio, 'link': link,
            'tienda': self.tienda, 'imagen': imagen, 'descuento': descuento
        }

    async def _go_to_next_page(self) -> bool:
        show_more_button_selector = "div.vtex-search-result-3-x-buttonShowMore button.vtex-button"
        try:
            show_more_button = await self.page.query_selector(show_more_button_selector)
            if show_more_button and await show_more_button.is_visible() and await show_more_button.is_enabled():
                await show_more_button.scroll_into_view_if_needed(timeout=5000)
                await self.page.wait_for_timeout(random.randint(500,1000))
                await show_more_button.click(timeout=self.DEFAULT_TIMEOUT)
                await self.page.wait_for_timeout(random.randint(3000, 5000)) # Espera para carga de nuevos productos
                return True
            return False
        except PlaywrightTimeoutError:
            # print(f"{self.tienda.title()}: Timeout/Botón 'Mostrar más' no encontrado.")
            return False
        except PlaywrightError as e:
            # print(f"{self.tienda.title()}: Error de Playwright al clickear 'Mostrar más': {e}")
            return False

def buscar_en_metro(producto: str) -> list:
    scraper = MetroPlaywrightScraper()
    # Max_paginas para Metro se interpreta como número de veces que se presiona "Mostrar más"
    # El valor por defecto en BasePlaywrightScraper.buscar (3) puede ser suficiente.
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            return asyncio.run(scraper.buscar(producto, max_paginas=4)) # Ajustar max_paginas si es necesario
        else:
            return asyncio.run(scraper.buscar(producto, max_paginas=4))
    except RuntimeError as e:
        if "cannot be called from a running event loop" in str(e):
            print(f"ADVERTENCIA ({scraper.tienda}): Intentando ejecutar en un nuevo bucle de eventos.")
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                results = new_loop.run_until_complete(scraper.buscar(producto, max_paginas=4))
            finally:
                new_loop.close()
                asyncio.set_event_loop(None)
            return results
        raise e

if __name__ == '__main__':
    async def main_test_metro():
        scraper = MetroPlaywrightScraper()
        return await scraper.buscar("leche gloria", max_paginas=2)

    start_time_main = time.time()
    productos_test = asyncio.run(main_test_metro())
    end_time_main = time.time()

    print(f"\n=== RESULTADOS DE PRUEBA ({MetroPlaywrightScraper().tienda}) ===")
    print(f"Productos encontrados: {len(productos_test)}")
    # print(f"IDs procesados: {len(MetroPlaywrightScraper().processed_product_ids)}") # No funcionará así, la instancia es nueva
    print(f"Tiempo total: {end_time_main - start_time_main:.2f} segundos")
    if productos_test:
        for i, p_item in enumerate(productos_test[:3]):
            print(f"\nProducto {i+1}:")
            print(f"  Nombre: {p_item['nombre']}")
            print(f"  Precio: S/ {p_item['precio']:.2f}")
            print(f"  Link: {p_item['link']}")
            print(f"  Imagen: {p_item['imagen']}")
            print(f"  Descuento: {p_item.get('descuento')}%" if p_item.get('descuento') else "No disponible")