import asyncio
import time
import random
import re
from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError
from .base_playwright_scraper import BasePlaywrightScraper

class OechslePlaywrightScraper(BasePlaywrightScraper):
    def __init__(self):
        super().__init__("oechsle")

    async def _get_base_url(self):
        return "https://www.oechsle.pe"

    async def _navigate_to_search(self, producto: str) -> bool:
        base_url_val = await self._get_base_url()
        await self.page.goto(base_url_val + "/", timeout=self.DEFAULT_TIMEOUT * 2)

        search_input_selector = "input.biggy-autocomplete__input"
        try:
            await self.page.fill(search_input_selector, producto, timeout=self.DEFAULT_TIMEOUT)
            # Oechsle a veces tiene un pop-up o sugerencias que pueden interferir.
            # Una pequeña pausa y luego presionar Enter puede ser más robusto.
            await self.page.wait_for_timeout(random.randint(300, 700))
            await self.page.press(search_input_selector, "Enter")

            await self.page.wait_for_selector("div.product", timeout=self.DEFAULT_TIMEOUT)
            return True
        except PlaywrightTimeoutError:
            print(f"{self.tienda.title()}: Timeout al buscar '{producto}'.")
            return False
        except PlaywrightError as e:
            print(f"{self.tienda.title()}: Error de Playwright en búsqueda: {e}")
            return False

    async def _get_product_elements(self) -> list:
        product_container_selector = "div.search-results"
        product_item_selector = "div.product"
        try:
            await self.page.wait_for_selector(product_container_selector, timeout=self.DEFAULT_TIMEOUT)
            container = await self.page.query_selector(product_container_selector)
            if container:
                return await container.query_selector_all(product_item_selector)
            return []
        except PlaywrightTimeoutError:
            print(f"{self.tienda.title()}: Timeout esperando contenedor de productos.")
            return []

    async def _extract_data_from_element(self, element_handle) -> dict | None:
        try:
            nombre_elem = await self._query_selector(element_handle, "span.fz-15.prod-name")
            nombre = await self._get_text_content(nombre_elem)
            if not nombre: return None

            link_elem = await self._query_selector(element_handle, "a.prod-image")
            raw_link = await self._get_attribute(link_elem, "href")
            link = self._build_full_url(await self._get_base_url(), raw_link)

            precio_elem = await self._query_selector(element_handle, "span.BestPrice")
            precio_text = await self._get_text_content(precio_elem)
            precio = self._clean_price(precio_text)
            if precio <= 0: return None

            descuento = None
            precio_lista_elem = await self._query_selector(element_handle, "span.ListPrice")
            if precio_lista_elem:
                precio_lista_text = await self._get_text_content(precio_lista_elem)
                precio_lista = self._clean_price(precio_lista_text)
                if precio_lista > 0 and precio_lista > precio:
                    calc_desc = ((precio_lista - precio) / precio_lista) * 100
                    if calc_desc > 0: descuento = int(calc_desc)

            img_elem = await self._query_selector(element_handle, "div.productImage img")
            raw_imagen = await self._get_attribute(img_elem, "src")
            imagen = self._build_full_url(await self._get_base_url(), raw_imagen) if raw_imagen and not raw_imagen.startswith('data:') else raw_imagen

            return {
                'nombre': nombre, 'precio': precio, 'link': link,
                'tienda': self.tienda, 'descuento': descuento, 'imagen': imagen
            }
        except PlaywrightError as e:
            # print(f"Error extrayendo datos de {self.tienda}: {e}")
            return None

    async def _go_to_next_page(self) -> bool:
        next_button_selector = "a.page-link.next"
        try:
            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight*0.8)")
            await self.page.wait_for_timeout(random.randint(300,600))

            next_button = await self.page.query_selector(next_button_selector)
            if next_button: # No se necesita is_enabled para 'a' si es clickable por JS
                await next_button.click(timeout=self.DEFAULT_TIMEOUT)
                await self.page.wait_for_load_state('domcontentloaded', timeout=self.DEFAULT_TIMEOUT)
                await self.page.wait_for_timeout(random.randint(2500, 4500))
                return True
            return False
        except PlaywrightTimeoutError:
            # print(f"{self.tienda.title()}: Timeout/Botón siguiente no encontrado.")
            return False
        except PlaywrightError:
            return False

def buscar_en_oechsle(producto: str) -> list:
    scraper = OechslePlaywrightScraper()
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
    async def main_test_oechsle():
        scraper = OechslePlaywrightScraper()
        return await scraper.buscar("televisor", max_paginas=2)

    start_time_main = time.time()
    productos_test = asyncio.run(main_test_oechsle())
    end_time_main = time.time()

    print(f"\n=== RESULTADOS DE PRUEBA ({OechslePlaywrightScraper().tienda}) ===")
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