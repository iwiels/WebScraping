import asyncio
import time
import random
import re
from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError
from .base_playwright_scraper import BasePlaywrightScraper

class RealPlazaPlaywrightScraper(BasePlaywrightScraper):
    def __init__(self):
        super().__init__("realplaza")
        self.visited_links = set()

    async def _get_base_url(self):
        return "https://www.realplaza.com"

    async def _navigate_to_search(self, producto: str) -> bool:
        base_url_val = await self._get_base_url()
        # Real Plaza a veces redirige a /s/, así que ir directo a la página de búsqueda puede ser mejor.
        # Formato URL: https://www.realplaza.com/buscar?q=laptop
        # Sin embargo, probaremos primero con la búsqueda en la página principal.
        await self.page.goto(base_url_val + "/", timeout=self.DEFAULT_TIMEOUT * 2)

        # El input de búsqueda es 'realplaza-store-components-0-x-omnichannelSearchInput__input'
        # o puede ser #search-input-desktop
        search_input_selector = "input.realplaza-store-components-0-x-omnichannelSearchInput__input"
        # Fallback selector
        search_input_selector_alt = "input#search-input-desktop"

        try:
            search_input = await self.page.query_selector(search_input_selector)
            if not search_input or not await search_input.is_visible():
                search_input = await self.page.query_selector(search_input_selector_alt)

            if not search_input:
                print(f"{self.tienda.title()}: Campo de búsqueda no encontrado.")
                return False

            await search_input.fill(producto, timeout=self.DEFAULT_TIMEOUT)
            await search_input.press("Enter")

            # Esperar a que la página de resultados cargue.
            # Un indicador puede ser el contenedor de productos o el título de la búsqueda.
            await self.page.wait_for_selector("div.vtex-search-result-3-x-gallery", timeout=self.DEFAULT_TIMEOUT)
            return True
        except PlaywrightTimeoutError:
            print(f"{self.tienda.title()}: Timeout al buscar '{producto}'.")
            return False
        except PlaywrightError as e:
            print(f"{self.tienda.title()}: Error de Playwright en búsqueda: {e}")
            return False

    async def _get_product_elements(self) -> list:
        # Los productos en Real Plaza suelen estar en contenedores VTEX
        product_item_selector = "div.vtex-product-summary-2-x-container"
        try:
            await self.page.wait_for_selector(product_item_selector, state='visible', timeout=self.DEFAULT_TIMEOUT)
            return await self.page.query_selector_all(product_item_selector)
        except PlaywrightTimeoutError:
            # print(f"{self.tienda.title()}: Timeout esperando elementos de producto.")
            return []

    async def _extract_data_from_element(self, element_handle) -> dict | None:
        try:
            nombre_elem = await self._query_selector(element_handle, ".vtex-product-summary-2-x-productBrand")
            nombre = await self._get_text_content(nombre_elem)

            marca_elem = await self._query_selector(element_handle, ".realplaza-product-custom-0-x-brandNameComponent") # Corregido el selector de marca
            marca = await self._get_text_content(marca_elem)

            nombre_completo = f"{marca} {nombre}".strip() if marca else nombre
            if not nombre_completo: return None

            link_elem = await self._query_selector(element_handle, "a.vtex-product-summary-2-x-clearLink")
            raw_link = await self._get_attribute(link_elem, "href")
            if not raw_link: return None

            link = self._build_full_url(await self._get_base_url(), raw_link)
            if link in self.visited_links: return None # Evitar duplicados
            self.visited_links.add(link)

            img_elem = await self._query_selector(element_handle, "img.vtex-product-summary-2-x-imageNormal")
            raw_imagen = await self._get_attribute(img_elem, "src")
            imagen = self._build_full_url(await self._get_base_url(), raw_imagen) if raw_imagen else None

            precio_regular_text = await self._get_text_content(await self._query_selector(element_handle, ".realplaza-product-custom-0-x-productSummaryPrice__Option__RegularPrice"))
            precio_oferta_text = await self._get_text_content(await self._query_selector(element_handle, ".realplaza-product-custom-0-x-productSummaryPrice__Option__OfferPrice"))

            precio_regular = self._clean_price(precio_regular_text)
            precio_oferta = self._clean_price(precio_oferta_text)

            precio_final = precio_oferta if precio_oferta > 0 else precio_regular
            if precio_final <= 0: return None

            descuento = None
            if precio_regular > 0 and precio_oferta > 0 and precio_regular > precio_oferta:
                calc_desc = ((precio_regular - precio_oferta) / precio_regular) * 100
                if calc_desc > 0: descuento = int(calc_desc)

            return {
                'nombre': nombre_completo, 'precio': precio_final, 'link': link,
                'tienda': self.tienda, 'imagen': imagen, 'descuento': descuento
            }
        except PlaywrightError:
            return None
        except Exception: # Captura general para otros errores
            return None


    async def _go_to_next_page(self) -> bool:
        # Botón de paginación en RealPlaza (VTEX)
        # El selector es 'button.realplaza-rpweb-10-x-paginationButton.realplaza-rpweb-10-x-enabled'
        # pero es mejor buscar un botón que no esté deshabilitado y sea el de "siguiente"
        # A menudo, el botón activo de "siguiente" no tiene 'disabled' y tiene un ícono o texto específico.
        # Vamos a buscar un botón dentro del contenedor de paginación que sea clickeable y parezca "siguiente"

        pagination_container = await self.page.query_selector("div.realplaza-rpweb-10-x-pagination__right-arrow")
        if not pagination_container:
            # print(f"{self.tienda.title()}: Contenedor de paginación (flecha derecha) no encontrado.")
            return False

        next_button = await self._query_selector(pagination_container, "button:not([disabled])")

        if next_button:
            try:
                await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight*0.8)")
                await self.page.wait_for_timeout(random.randint(300,600))
                await next_button.click(timeout=self.DEFAULT_TIMEOUT)
                await self.page.wait_for_load_state('domcontentloaded', timeout=self.DEFAULT_TIMEOUT)
                await self.page.wait_for_timeout(random.randint(2500, 4500))
                return True
            except PlaywrightTimeoutError:
                # print(f"{self.tienda.title()}: Timeout al clickear/cargar siguiente página.")
                return False
            except PlaywrightError:
                # print(f"{self.tienda.title()}: Error de Playwright al ir a siguiente página.")
                return False
        return False

def buscar_en_realplaza(producto: str) -> list:
    scraper = RealPlazaPlaywrightScraper()
    try:
        # Gestión del bucle de eventos de asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                 # Si ya hay un bucle, no se puede usar asyncio.run() directamente.
                 # Esto puede pasar en algunos contextos (ej. Jupyter, o si Flask/Gunicorn usa su propio bucle).
                 # Una solución es usar `asyncio.create_task` si el contexto lo permite y se maneja el await externamente,
                 # o ejecutar en un nuevo hilo con su propio bucle.
                 # Para la integración con ThreadPoolExecutor de Flask, asyncio.run() suele ser lo que se intenta.
                 print(f"ADVERTENCIA ({scraper.tienda}): El bucle de eventos ya está corriendo. Intentando asyncio.run() de todas formas.")
                 # Esta llamada podría fallar.
                 return asyncio.run(scraper.buscar(producto))
            else:
                return asyncio.run(scraper.buscar(producto))
        except RuntimeError as e:
            if "cannot be called from a running event loop" in str(e) or "Event loop is closed" in str(e):
                print(f"ADVERTENCIA ({scraper.tienda}): Creando un nuevo bucle de eventos para la tarea async.")
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    results = new_loop.run_until_complete(scraper.buscar(producto))
                finally:
                    new_loop.close()
                    # Restaurar el bucle de eventos original si había uno podría ser necesario en algunos contextos
                    # pero es complejo y depende de cómo se gestione globalmente.
                    # Por ahora, simplemente no establecemos uno nuevo globalmente después de cerrar.
                return results
            raise e # Re-lanzar otros RuntimeErrors
    except Exception as e_global:
        print(f"Error global ejecutando scraper {scraper.tienda}: {e_global}")
        return []


if __name__ == '__main__':
    async def main_test_realplaza():
        scraper = RealPlazaPlaywrightScraper()
        # Incrementar max_paginas para probar paginación
        return await scraper.buscar("laptop gamer", max_paginas=2)

    start_time_main = time.time()
    productos_test = asyncio.run(main_test_realplaza())
    end_time_main = time.time()

    print(f"\n=== RESULTADOS DE PRUEBA ({RealPlazaPlaywrightScraper().tienda}) ===")
    print(f"Productos encontrados: {len(productos_test)}")
    print(f"Tiempo total: {end_time_main - start_time_main:.2f} segundos")
    if productos_test:
        for i, p_item in enumerate(productos_test[:2]): # Mostrar algunos resultados
            print(f"\nProducto {i+1}:")
            print(f"  Nombre: {p_item['nombre']}")
            print(f"  Precio: S/ {p_item['precio']:.2f}")
            print(f"  Link: {p_item['link']}")
            print(f"  Imagen: {p_item['imagen']}")
            print(f"  Descuento: {p_item.get('descuento')}%" if p_item.get('descuento') else "No disponible")

# Nota: Se corrigió .realplaza-product-custom-0-x-brancNameComponent a .realplaza-product-custom-0-x-brandNameComponent
# y se ajustó la lógica de paginación para ser más robusta.
