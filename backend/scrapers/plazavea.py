import asyncio
import time
import random
import re
from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError
from .base_playwright_scraper import BasePlaywrightScraper

class PlazaVeaPlaywrightScraper(BasePlaywrightScraper):
    def __init__(self):
        super().__init__("plazavea")

    async def _get_base_url(self):
        return "https://www.plazavea.com.pe"

    async def _navigate_to_search(self, producto: str) -> bool:
        base_url_val = await self._get_base_url()
        await self.page.goto(base_url_val + "/", timeout=self.DEFAULT_TIMEOUT * 2)

        try:
            # Modal de ubicación
            modal_close_selector = "div.modal-locationnew__content-address--close > svg"
            # Usar query_selector para no fallar si no está, y luego intentar click si existe
            close_button = await self.page.query_selector(modal_close_selector)
            if close_button:
                try:
                    await close_button.click(timeout=5000) # Corto timeout para el modal
                    await self.page.wait_for_timeout(500) # Pausa para que se cierre
                except PlaywrightError:
                    print(f"{self.tienda.title()}: No se pudo cerrar el modal de ubicación (puede que no haya aparecido).")

            search_input_selector = "input#search_box" # PlazaVea usa ID para el input
            await self.page.fill(search_input_selector, producto, timeout=self.DEFAULT_TIMEOUT)
            await self.page.press(search_input_selector, "Enter")

            # Esperar a que la página de resultados cargue (un contenedor principal)
            await self.page.wait_for_selector("div.Layout_Layout__BODY__3Lp3Z", timeout=self.DEFAULT_TIMEOUT)
            return True
        except PlaywrightTimeoutError:
            print(f"{self.tienda.title()}: Timeout al buscar '{producto}'.")
            return False
        except PlaywrightError as e:
            print(f"{self.tienda.title()}: Error de Playwright en búsqueda: {e}")
            return False

    async def _get_product_elements(self) -> list:
        grid_container_selector = "div.Layout_Layout__GRID__32gIq"
        product_item_selector = "div[class*='Showcase_Showcase__']" # Clase que contiene 'Showcase_Showcase__'
        try:
            await self.page.wait_for_selector(grid_container_selector, timeout=self.DEFAULT_TIMEOUT)
            container = await self.page.query_selector(grid_container_selector)
            if container:
                return await container.query_selector_all(product_item_selector)
            return []
        except PlaywrightTimeoutError:
            # print(f"{self.tienda.title()}: Timeout esperando contenedor de productos.")
            return []

    async def _extract_data_from_element(self, element_handle) -> dict | None:
        try:
            nombre_elem = await self._query_selector(element_handle, "span[class*='Showcase_Showcase__name']")
            nombre = await self._get_text_content(nombre_elem)

            marca_elem = await self._query_selector(element_handle, "span[class*='Showcase_Showcase__brand']")
            marca = await self._get_text_content(marca_elem)
            nombre_completo = f"{marca} {nombre}".strip() if marca else nombre
            if not nombre_completo: return None

            link_elem = await self._query_selector(element_handle, "a[class*='Showcase_Showcase__link']")
            raw_link = await self._get_attribute(link_elem, "href")
            link = self._build_full_url(await self._get_base_url(), raw_link)

            img_elem = await self._query_selector(element_handle, "img[class*='Showcase_Showcase__image']")
            raw_imagen = await self._get_attribute(img_elem, "src")
            imagen = self._build_full_url(await self._get_base_url(), raw_imagen) if raw_imagen else None

            precio_regular_text = await self._get_text_content(await self._query_selector(element_handle, "span[class*='Showcase_Showcase__oldPrice']"))
            precio_oferta_text = await self._get_text_content(await self._query_selector(element_handle, "span[class*='Showcase_Showcase__price']"))
            precio_oh_text = await self._get_text_content(await self._query_selector(element_handle, "span[class*='Showcase_Showcase__cardPrice']"))

            precio_regular = self._clean_price(precio_regular_text)
            precio_oferta = self._clean_price(precio_oferta_text)
            precio_oh = self._clean_price(precio_oh_text)

            precios_validos = [p for p in [precio_oferta, precio_oh, precio_regular] if p > 0]
            if not precios_validos: return None
            precio_final = min(precios_validos)

            precio_base_descuento = precio_regular if precio_regular > precio_final else 0
            if precio_base_descuento == 0 and precio_oferta > precio_final : # Si no hay oldPrice, usar oferta si es mayor
                 precio_base_descuento = precio_oferta

            descuento = None
            if precio_base_descuento > 0 and precio_final > 0 and precio_base_descuento > precio_final:
                calc_desc = ((precio_base_descuento - precio_final) / precio_base_descuento) * 100
                if calc_desc > 0: descuento = int(calc_desc)

            return {
                'nombre': nombre_completo, 'precio': precio_final, 'link': link,
                'tienda': self.tienda, 'imagen': imagen, 'descuento': descuento
            }
        except PlaywrightError:
            return None

    async def _go_to_next_page(self) -> bool:
        next_button_selector = "button.PageNumbers__button--next"
        try:
            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight*0.85)") # Scroll para visibilidad
            await self.page.wait_for_timeout(random.randint(400,800))

            next_button = await self.page.query_selector(next_button_selector)
            if next_button and await next_button.is_enabled() and "disabled" not in (await self._get_attribute(next_button, "class")):
                await next_button.click(timeout=self.DEFAULT_TIMEOUT)
                await self.page.wait_for_load_state('domcontentloaded', timeout=self.DEFAULT_TIMEOUT)
                await self.page.wait_for_timeout(random.randint(2500, 4000))
                return True
            return False
        except PlaywrightTimeoutError:
            return False
        except PlaywrightError:
            return False

def buscar_en_plazavea(producto: str) -> list:
    scraper = PlazaVeaPlaywrightScraper()
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
    async def main_test_plazavea():
        scraper = PlazaVeaPlaywrightScraper()
        return await scraper.buscar("laptop", max_paginas=2)

    start_time_main = time.time()
    productos_test = asyncio.run(main_test_plazavea())
    end_time_main = time.time()

    print(f"\n=== RESULTADOS DE PRUEBA ({PlazaVeaPlaywrightScraper().tienda}) ===")
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
