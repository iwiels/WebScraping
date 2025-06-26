import asyncio
import time
import random
import re
from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError
from urllib.parse import urljoin, urlparse
from collections import OrderedDict
from .base_playwright_scraper import BasePlaywrightScraper


class FalabellaImageExtractor:
    VALID_IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp', '.gif')
    FALLBACK_IMAGE_URL = "/frontend/placeholder.jpg" # Relativa a la raíz del servidor frontend

    def __init__(self, base_url="https://www.falabella.com.pe/falabella-pe/"):
        self.base_url = base_url
        self.url_cache = OrderedDict()

    async def extract_image(self, item_element: 'ElementHandle', scraper: BasePlaywrightScraper) -> str:
        strategies = [
            lambda e: self._extract_from_picture_img(e, scraper),
            lambda e: self._extract_from_picture_source(e, scraper),
            lambda e: self._extract_from_img(e, scraper), # Puede ser muy genérico, usar con cuidado
            lambda e: self._extract_from_lazy_loading_attributes(e, scraper),
            lambda e: self._extract_from_section_img(e, scraper),
        ]

        for strategy in strategies:
            try:
                image_url = await strategy(item_element)
                if image_url and image_url != self.FALLBACK_IMAGE_URL : # Si una estrategia devuelve algo válido
                    return self._process_image_url(image_url) # Procesa y devuelve
            except PlaywrightError: # Errores al buscar elementos con query_selector
                continue
            except Exception: # Otros errores inesperados
                continue

        # Si ninguna estrategia funciona, devuelve la URL de fallback procesada (para que sea absoluta)
        return self._process_image_url(self.FALLBACK_IMAGE_URL)


    async def _get_image_url_from_img_element(self, img_element, scraper: BasePlaywrightScraper) -> str | None:
        if not img_element: return None
        image_url = await scraper._get_attribute(img_element, "src")

        if not image_url or "data:image" in image_url: # Evitar data URIs o src vacíos
            srcset = await scraper._get_attribute(img_element, "srcset")
            if srcset:
                image_url = self._get_image_url_from_srcset(srcset) # srcset es síncrono

        return image_url if image_url and "data:image" not in image_url else None

    def _get_image_url_from_srcset(self, srcset: str) -> str | None:
        if not srcset: return None
        urls = []
        for srcset_part in srcset.split(','):
            parts = srcset_part.strip().split()
            if parts:
                url = parts[0]
                if self._is_valid_image_url(url):
                    urls.append(url)
        return urls[-1] if urls else None # Devolver la de "mayor resolución" (última listada)

    def _is_valid_image_url(self, url: str) -> bool:
        return url and isinstance(url, str) and \
               url.lower().endswith(self.VALID_IMAGE_EXTENSIONS) and \
               (url.startswith('http') or url.startswith('//'))


    async def _extract_from_picture_img(self, item_element, scraper: BasePlaywrightScraper) -> str | None:
        img_element = await scraper._query_selector(item_element, "picture img")
        return await self._get_image_url_from_img_element(img_element, scraper)

    async def _extract_from_picture_source(self, item_element, scraper: BasePlaywrightScraper) -> str | None:
        source_element = await scraper._query_selector(item_element, "picture source")
        if not source_element: return None
        srcset = await scraper._get_attribute(source_element, "srcset")
        return self._get_image_url_from_srcset(srcset)

    async def _extract_from_img(self, item_element, scraper: BasePlaywrightScraper) -> str | None:
        # Selector más específico para Falabella, buscando dentro de contenedores comunes de imagen.
        # Ajustar según la estructura HTML de Falabella.
        # Ejemplo: '.image-container img', '.product-image-wrapper img', etc.
        # El selector original '.image-wrapper img' puede ser demasiado amplio.
        # Priorizar selectores más específicos si se conocen.
        img_element = await scraper._query_selector(item_element, "img.cs-home-merchandising-card-image__img") # Ajustar selector
        if not img_element : # Fallback a un selector más general si el específico falla
             img_element = await scraper._query_selector(item_element, "img[class*='image']") # Aún riesgoso
        return await self._get_image_url_from_img_element(img_element, scraper)


    async def _extract_from_lazy_loading_attributes(self, item_element, scraper: BasePlaywrightScraper) -> str | None:
        # Buscar img con data-src o data-srcset
        # Este selector es un ejemplo, ajustar al HTML real de Falabella
        img_element = await scraper._query_selector(item_element, "img[data-src], img[data-srcset]")
        if not img_element: return None

        image_url = await scraper._get_attribute(img_element, "data-src")
        if not image_url or "data:image" in image_url:
            srcset = await scraper._get_attribute(img_element, "data-srcset")
            if srcset:
                image_url = self._get_image_url_from_srcset(srcset)
        return image_url if image_url and "data:image" not in image_url else None

    async def _extract_from_section_img(self, item_element, scraper: BasePlaywrightScraper) -> str | None:
        # XPATH puede ser lento, usar con cuidado. Convertir a CSS selector si es posible.
        # XPATH: ".//div[contains(@class,'pod-head')]/div/section[contains(@class,'layout_grid-view') and contains(@class,'layout_view_4_GRID')]/img"
        # Esto es muy específico y podría romperse fácilmente.
        # Tratar de usar selectores CSS más estables.
        # Por ahora, se omite esta estrategia o se simplifica a un CSS selector si es posible.
        # Ejemplo simplificado (requiere inspección del HTML de Falabella):
        img_element = await scraper._query_selector(item_element, "section[class*='grid-view'] img")
        if img_element:
            return await self._get_image_url_from_img_element(img_element, scraper)

        img_element_picture = await scraper._query_selector(item_element, "section[class*='grid-view'] picture img")
        if img_element_picture:
            return await self._get_image_url_from_img_element(img_element_picture, scraper)

        return None

    def _process_image_url(self, image_url: str) -> str:
        if not image_url or not isinstance(image_url, str):
            # Si la URL de fallback también es inválida, devuelve un string vacío o una URL placeholder absoluta.
            return urljoin(self.base_url, self.FALLBACK_IMAGE_URL)


        # Manejar URLs relativas al protocolo
        if image_url.startswith('//'):
            image_url = "https:" + image_url

        # Unir con base_url si es relativa al path
        parsed_url = urlparse(image_url)
        if not parsed_url.netloc and not parsed_url.scheme:
            image_url = urljoin(self.base_url, image_url)

        # Optimización de Cloudflare/CDN si aplica (ejemplo de Falabella)
        if 'cdn-cgi/imagedelivery' in image_url:
            image_url = re.sub(
                r'(width=\d+,height=\d+,quality=\d+)',
                'width=480,height=480,quality=100', # Ajustar según necesidad
                image_url
            )

        # Cache (opcional)
        if image_url in self.url_cache: return image_url
        if len(self.url_cache) >= 100: self.url_cache.popitem(last=False)
        self.url_cache[image_url] = None

        return image_url


class FalabellaPlaywrightScraper(BasePlaywrightScraper):
    def __init__(self):
        super().__init__("falabella")
        self.image_extractor = FalabellaImageExtractor(base_url=self._get_base_url_sync())

    def _get_base_url_sync(self): # Necesaria para el constructor de ImageExtractor
        return "https://www.falabella.com.pe/falabella-pe"

    async def _get_base_url(self):
        return self._get_base_url_sync()

    async def _navigate_to_search(self, producto: str) -> bool:
        base_url_val = await self._get_base_url()
        await self.page.goto(base_url_val, timeout=self.DEFAULT_TIMEOUT * 2)

        # Intentar cerrar modal de ubicación (si existe)
        modal_close_button_selector = "button#acc-alert-deny"
        try:
            modal_button = await self.page.query_selector(modal_close_button_selector)
            if modal_button:
                await modal_button.click(timeout=5000) # Corto timeout para el clic del modal
                await self.page.wait_for_timeout(500) # Pequeña pausa
        except PlaywrightError:
            print(f"{self.tienda.title()}: Modal de ubicación no encontrado o no se pudo cerrar.")

        search_input_selector = "input#testId-SearchBar-Input"
        try:
            await self.page.fill(search_input_selector, producto, timeout=self.DEFAULT_TIMEOUT)
            await self.page.press(search_input_selector, "Enter")
            await self.page.wait_for_selector("div#testId-searchResults-products", timeout=self.DEFAULT_TIMEOUT)
            return True
        except PlaywrightTimeoutError:
            print(f"{self.tienda.title()}: Timeout al buscar '{producto}'.")
            return False
        except PlaywrightError as e:
            print(f"{self.tienda.title()}: Error de Playwright en búsqueda: {e}")
            return False

    async def _get_product_elements(self) -> list:
        product_selector = "a.pod-link[data-pod='catalyst-pod']"
        try:
            await self.page.wait_for_selector(product_selector, state='visible', timeout=self.DEFAULT_TIMEOUT)
            return await self.page.query_selector_all(product_selector)
        except PlaywrightTimeoutError:
            print(f"{self.tienda.title()}: Timeout esperando elementos de producto.")
            return []

    async def _extract_data_from_element(self, element_handle) -> dict | None:
        try:
            nombre_elem = await self._query_selector(element_handle, "b.pod-subTitle")
            nombre = await self._get_text_content(nombre_elem)
            if not nombre: # Fallback
                nombre_elem_alt = await self._query_selector(element_handle, ".pod-title")
                nombre = await self._get_text_content(nombre_elem_alt)
            if not nombre: return None

            raw_link = await self._get_attribute(element_handle, "href")
            link = self._build_full_url(await self._get_base_url(), raw_link)

            precio_elem = await self._query_selector(element_handle, "li.prices-0 span")
            precio_text = await self._get_text_content(precio_elem)
            precio = self._clean_price(precio_text)
            if precio <= 0: return None

            descuento = None
            descuento_elem = await self._query_selector(element_handle, "div.discount-badge span")
            if descuento_elem:
                desc_text = await self._get_text_content(descuento_elem)
                match = re.search(r'(\d+)%', desc_text)
                if match: descuento = int(match.group(1))

            imagen = await self.image_extractor.extract_image(element_handle, self)

            return {
                "nombre": nombre, "precio": precio, "link": link,
                "tienda": self.tienda, "descuento": descuento, "imagen": imagen
            }
        except PlaywrightError as e:
            # print(f"Error extrayendo datos de Falabella: {e}")
            return None

    async def _go_to_next_page(self) -> bool:
        next_button_selector = "button#testId-pagination-top-arrow-right"
        try:
            # Scroll para asegurar que el botón sea visible
            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight*0.8)")
            await self.page.wait_for_timeout(500)

            next_button = await self.page.query_selector(next_button_selector)
            if next_button and await next_button.is_enabled():
                await next_button.click(timeout=self.DEFAULT_TIMEOUT)
                await self.page.wait_for_load_state('domcontentloaded', timeout=self.DEFAULT_TIMEOUT)
                await self.page.wait_for_timeout(random.randint(2000, 4000)) # Pausa post-navegación
                return True
            return False
        except PlaywrightTimeoutError:
            print(f"{self.tienda.title()}: Timeout/Botón siguiente no encontrado o no habilitado.")
            return False
        except PlaywrightError as e:
            print(f"{self.tienda.title()}: Error de Playwright al ir a siguiente página: {e}")
            return False

def buscar_en_falabella(producto: str) -> list:
    scraper = FalabellaPlaywrightScraper()
    # Esta función es llamada desde app.py que es síncrono.
    # Necesitamos correr la función async buscar.
    # La gestión del bucle de eventos de asyncio es crucial aquí.
    # Ver wrapper de ripley_playwright para una discusión más detallada.
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Si Flask ya corre en un bucle (ej. con Quart o un worker async de Gunicorn)
            # simplemente crear la tarea podría ser una opción, pero requiere que
            # la función Flask sea async y que el resultado se maneje apropiadamente.
            # Para un ThreadPoolExecutor síncrono, necesitamos un nuevo bucle o asyncio.run().
            # Si el error de "loop is running" persiste, app.py necesita una estrategia de ejecución async.
            # Por ahora, intentaremos asyncio.run() ya que es el más directo.
            return asyncio.run(scraper.buscar(producto))
        else:
            return asyncio.run(scraper.buscar(producto))
    except RuntimeError as e:
        if "cannot be called from a running event loop" in str(e):
            # Fallback temporal si asyncio.run() falla debido a un bucle existente.
            # Esto es una simplificación y puede no ser robusto.
            # Idealmente, la app Flask/Gunicorn debería manejar la ejecución de tareas async.
            print(f"ADVERTENCIA ({scraper.tienda}): Intentando ejecutar en un nuevo bucle de eventos debido a bucle existente.")
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                results = new_loop.run_until_complete(scraper.buscar(producto))
            finally:
                new_loop.close()
                asyncio.set_event_loop(None) # Restaurar el bucle de eventos original si es posible
            return results
        raise e


if __name__ == '__main__':
    async def main_test_falabella():
        scraper = FalabellaPlaywrightScraper()
        return await scraper.buscar("smart tv", max_paginas=2)

    start_time_main = time.time()
    productos_test = asyncio.run(main_test_falabella())
    end_time_main = time.time()

    print(f"\n=== RESULTADOS DE PRUEBA ({FalabellaPlaywrightScraper().tienda}) ===")
    print(f"Productos encontrados: {len(productos_test)}")
    print(f"Tiempo total: {end_time_main - start_time_main:.2f} segundos")
    if productos_test:
        for i, p_item in enumerate(productos_test[:3]):
            print(f"\nProducto {i+1}:")
            print(f"  Nombre: {p_item['nombre']}")
            print(f"  Precio: S/ {p_item['precio']:.2f}")
            print(f"  Link: {p_item['link']}")
            print(f"  Imagen: {p_item['imagen']}")
            print(f"  Descuento: {p_item.get('descuento')}%" if p_item.get('descuento') else "No disponible")