import asyncio
import time
import random
import re
from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError
from .base_playwright_scraper import BasePlaywrightScraper

class HiraokaPlaywrightScraper(BasePlaywrightScraper):
    def __init__(self):
        super().__init__("hiraoka")

    async def _get_base_url(self):
        return "https://hiraoka.com.pe"

    async def _navigate_to_search(self, producto: str) -> bool:
        base_url_val = await self._get_base_url()
        await self.page.goto(base_url_val + "/", timeout=self.DEFAULT_TIMEOUT * 2)

        search_input_selector = "input#search"
        try:
            await self.page.fill(search_input_selector, producto, timeout=self.DEFAULT_TIMEOUT)
            await self.page.press(search_input_selector, "Enter")
            # Esperar a que la página de resultados cargue
            await self.page.wait_for_selector("li.product-item", timeout=self.DEFAULT_TIMEOUT)
            return True
        except PlaywrightTimeoutError:
            print(f"{self.tienda.title()}: Timeout al buscar '{producto}'.")
            return False
        except PlaywrightError as e:
            print(f"{self.tienda.title()}: Error de Playwright en búsqueda: {e}")
            return False

    async def _get_product_elements(self) -> list:
        product_list_container_selector = "ol.product-items"
        product_item_selector = "li.product-item"
        try:
            await self.page.wait_for_selector(product_list_container_selector, timeout=self.DEFAULT_TIMEOUT)
            container = await self.page.query_selector(product_list_container_selector)
            if container:
                return await container.query_selector_all(product_item_selector)
            return []
        except PlaywrightTimeoutError:
            print(f"{self.tienda.title()}: Timeout esperando contenedor de productos.")
            return []

    async def _extract_data_from_element(self, element_handle) -> dict | None:
        try:
            marca_elem = await self._query_selector(element_handle, ".product-item-brand a")
            marca_text = await self._get_text_content(marca_elem)

            nombre_elem = await self._query_selector(element_handle, ".product-item-name a")
            nombre_text = await self._get_text_content(nombre_elem)
            nombre_completo = f"{marca_text} {nombre_text}".strip()
            if not nombre_completo: return None

            link_elem = await self._query_selector(element_handle, ".product-item-link")
            raw_link = await self._get_attribute(link_elem, "href")
            link = self._build_full_url(await self._get_base_url(), raw_link)

            img_elem = await self._query_selector(element_handle, ".product-image-photo")
            raw_imagen = await self._get_attribute(img_elem, "src")
            imagen = self._build_full_url(await self._get_base_url(), raw_imagen) if raw_imagen else None

            precio_actual_elem = await self._query_selector(element_handle, "span[data-price-type='finalPrice'] .price")
            precio_actual_text = await self._get_text_content(precio_actual_elem)
            precio_actual = self._clean_price(precio_actual_text)
            if precio_actual <= 0: return None

            precio_antiguo = 0.0
            precio_antiguo_elem = await self._query_selector(element_handle, "span[data-price-type='oldPrice'] .price")
            if precio_antiguo_elem:
                precio_antiguo_text = await self._get_text_content(precio_antiguo_elem)
                precio_antiguo = self._clean_price(precio_antiguo_text)

            descuento = None
            if precio_antiguo > 0 and precio_actual > 0 and precio_antiguo > precio_actual:
                calc_desc = ((precio_antiguo - precio_actual) / precio_antiguo) * 100
                if calc_desc > 0: descuento = int(calc_desc)

            return {
                'nombre': nombre_completo, 'precio': precio_actual, 'link': link,
                'tienda': self.tienda, 'imagen': imagen, 'descuento': descuento
            }
        except PlaywrightError as e:
            # print(f"Error extrayendo datos de {self.tienda}: {e}")
            return None

    async def _go_to_next_page(self) -> bool:
        next_button_selector = "li.pages-item-next:not(.disabled) a"
        try:
            next_button = await self.page.query_selector(next_button_selector)
            if next_button:
                await next_button.click(timeout=self.DEFAULT_TIMEOUT)
                await self.page.wait_for_load_state('domcontentloaded', timeout=self.DEFAULT_TIMEOUT)
                await self.page.wait_for_timeout(random.randint(2000, 3500))
                return True
            return False
        except PlaywrightTimeoutError:
            # print(f"{self.tienda.title()}: Timeout/Botón siguiente no encontrado.")
            return False
        except PlaywrightError:
            return False

def buscar_en_hiraoka(producto: str) -> list:
    scraper = HiraokaPlaywrightScraper()
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
    async def main_test_hiraoka():
        scraper = HiraokaPlaywrightScraper()
        return await scraper.buscar("refrigeradora", max_paginas=2)

    start_time_main = time.time()
    productos_test = asyncio.run(main_test_hiraoka())
    end_time_main = time.time()

    print(f"\n=== RESULTADOS DE PRUEBA ({HiraokaPlaywrightScraper().tienda}) ===")
    print(f"Productos encontrados: {len(productos_test)}")
    print(f"Tiempo total: {end_time_main - start_time_main:.2f} segundos")
    if productos_test:
        for i, p_item in enumerate(productos_test[:2]):
            print(f"\nProducto {i+1}:")
            print(f"  Nombre: {p_item['nombre']}")
            print(f"  Precio: S/ {p_item['precio']:.2f}")
            print(f"  Link: {p_item['link']}")
            print(f"  Imagen: {p_item['imagen']}")
            print(f"  Descuento: {p_item.get('descuento')}%" if p_item.get('descuento') else "No disponible")
