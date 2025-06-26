import asyncio
import time
import random
import re
from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError
from .base_playwright_scraper import BasePlaywrightScraper

class TailoyPlaywrightScraper(BasePlaywrightScraper):
    def __init__(self):
        super().__init__("tailoy")

    async def _get_base_url(self):
        return "https://www.tailoy.com.pe"

    async def _navigate_to_search(self, producto: str) -> bool:
        base_url_val = await self._get_base_url()
        await self.page.goto(base_url_val + "/", timeout=self.DEFAULT_TIMEOUT * 2)

        # Tailoy parece usar Magento, el selector de búsqueda suele ser #search
        search_input_selector = "input#search"
        # El selector original era "input.vtex-styleguide-9-x-input", que es de VTEX. Se cambia a #search.

        try:
            # Tailoy puede tener un pop-up de suscripción o cookies. Intentar cerrarlo.
            # Selector común para botón de cierre de pop-ups (ajustar si es necesario)
            popup_close_selectors = [
                "button[aria-label='Cerrar']",
                "button.mfp-close",
                "div.modal-popup > button.action-close" #Magento popup
            ]
            for sel in popup_close_selectors:
                close_button = await self.page.query_selector(sel)
                if close_button and await close_button.is_visible():
                    try:
                        await close_button.click(timeout=3000)
                        await self.page.wait_for_timeout(500) # Pausa para que se cierre
                        break
                    except PlaywrightError:
                        pass # Continuar si el clic falla o no es el pop-up correcto

            await self.page.fill(search_input_selector, producto, timeout=self.DEFAULT_TIMEOUT)
            await self.page.press(search_input_selector, "Enter")

            # Esperar a que la página de resultados cargue
            await self.page.wait_for_selector("div.product-item-info", timeout=self.DEFAULT_TIMEOUT)
            return True
        except PlaywrightTimeoutError:
            print(f"{self.tienda.title()}: Timeout al buscar '{producto}'.")
            return False
        except PlaywrightError as e:
            print(f"{self.tienda.title()}: Error de Playwright en búsqueda: {e}")
            return False

    async def _get_product_elements(self) -> list:
        # Selector para los items de producto en Tailoy (Magento)
        product_item_selector = "li.product-item" # Contenedor de cada producto
        # El div.product-item-info está dentro de li.product-item
        try:
            await self.page.wait_for_selector(product_item_selector, state='visible', timeout=self.DEFAULT_TIMEOUT)
            return await self.page.query_selector_all(product_item_selector)
        except PlaywrightTimeoutError:
            # print(f"{self.tienda.title()}: Timeout esperando elementos de producto.")
            return []

    async def _extract_data_from_element(self, element_handle) -> dict | None:
        # Trabajar sobre el 'div.product-item-info' dentro del 'li.product-item'
        info_element = await self._query_selector(element_handle, "div.product-item-info")
        if not info_element:
            info_element = element_handle # Usar el handle principal si no se encuentra el sub-elemento

        try:
            nombre_elem = await self._query_selector(info_element, "a.product-item-link")
            nombre = await self._get_text_content(nombre_elem)
            if not nombre: return None

            raw_link = await self._get_attribute(nombre_elem, "href")
            link = self._build_full_url(await self._get_base_url(), raw_link)

            precio_elem = await self._query_selector(info_element, "span.price")
            precio_text = await self._get_text_content(precio_elem)
            precio = self._clean_price(precio_text)
            if precio <= 0: return None

            # Imagen: buscar primero 'img.product-image-photo', luego alternativas
            img_elem = await self._query_selector(element_handle, "img.product-image-photo")
            raw_imagen = await self._get_attribute(img_elem, "src")
            if not raw_imagen:
                 img_wrapper_elem = await self._query_selector(element_handle, "span.product-image-wrapper img")
                 raw_imagen = await self._get_attribute(img_wrapper_elem, "src")

            imagen = self._build_full_url(await self._get_base_url(), raw_imagen) if raw_imagen else None

            descuento = None
            # Magento a veces tiene old-price y special-price
            old_price_elem = await self._query_selector(info_element, "span[data-price-type='oldPrice'] span.price")
            special_price_elem = await self._query_selector(info_element, "span[data-price-type='finalPrice'] span.price") # precio actual ya es finalPrice

            if old_price_elem and special_price_elem : # Si ambos existen, es probable que haya descuento
                old_price_text = await self._get_text_content(old_price_elem)
                old_price = self._clean_price(old_price_text)
                if old_price > precio: # Precio es el special_price
                    descuento_calc = ((old_price - precio) / old_price) * 100
                    if descuento_calc > 0 : descuento = int(descuento_calc)
            else: # Buscar por etiqueta de porcentaje si existe (menos común en Magento default)
                descuento_tag_elem = await self._query_selector(info_element, "span.price-percentage .discount-value") # Ejemplo
                if descuento_tag_elem:
                    desc_text = await self._get_text_content(descuento_tag_elem)
                    match = re.search(r'(\d+)%', desc_text)
                    if match: descuento = int(match.group(1))

            marca = None # Tailoy no siempre muestra la marca prominentemente en la grilla
            # marca_elem = await self._query_selector(info_element, "div.brand-label span.label") # Si existiera
            # marca = await self._get_text_content(marca_elem)

            return {
                'nombre': nombre, 'precio': precio, 'link': link,
                'tienda': self.tienda, 'imagen': imagen, 'descuento': descuento,
                'marca': marca
            }
        except PlaywrightError:
            return None

    async def _go_to_next_page(self) -> bool:
        # Paginador tipo Magento: li.pages-item-next a.action.next
        next_button_selector = "li.pages-item-next a.action.next"
        # El selector original era "a.next", que es más genérico.
        try:
            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight*0.85)")
            await self.page.wait_for_timeout(random.randint(300,600))

            next_button = await self.page.query_selector(next_button_selector)
            if next_button:
                # Verificar si el botón está deshabilitado (Magento a veces añade clase 'disabled' al 'li' padre)
                parent_li = await self.page.query_selector(f"{next_button_selector}:xpath=../..") # Ir al 'li'
                if parent_li and "disabled" in (await self._get_attribute(parent_li, "class")):
                    return False

                await next_button.click(timeout=self.DEFAULT_TIMEOUT)
                await self.page.wait_for_load_state('domcontentloaded', timeout=self.DEFAULT_TIMEOUT)
                await self.page.wait_for_timeout(random.randint(2500, 4500))
                return True
            return False
        except PlaywrightTimeoutError:
            return False
        except PlaywrightError:
            return False

def buscar_en_tailoy(producto: str) -> list:
    scraper = TailoyPlaywrightScraper()
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
    async def main_test_tailoy():
        scraper = TailoyPlaywrightScraper()
        return await scraper.buscar("cuaderno", max_paginas=2)

    start_time_main = time.time()
    productos_test = asyncio.run(main_test_tailoy())
    end_time_main = time.time()

    print(f"\n=== RESULTADOS DE PRUEBA ({TailoyPlaywrightScraper().tienda}) ===")
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
            print(f"  Marca: {p_item.get('marca')}" if p_item.get('marca') else "No disponible")