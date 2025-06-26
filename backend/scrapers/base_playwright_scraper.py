import asyncio
import re
import random
import os
import logging # Importar logging
from abc import ABC, abstractmethod
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError

# Configurar un logger para la clase base y sus hijas
logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG) # Ajustar nivel según necesidad (DEBUG, INFO, WARNING, ERROR)
# # Crear un handler (ej. para consola) y formatter si se quiere una configuración más específica aquí
# # Si no, dependerá de la configuración de logging de la aplicación principal (app.py)
# if not logger.hasHandlers():
#     ch = logging.StreamHandler()
#     formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
#     ch.setFormatter(formatter)
#     logger.addHandler(ch)

class BasePlaywrightScraper(ABC):
    """
    Clase base para todos los scrapers de tiendas que usan Playwright.
    Proporciona funcionalidad común como configuración del navegador,
    manejo de user-agents, utilidades de limpieza de precios, etc.
    Todos los métodos que interactúan con Playwright deben ser asíncronos.
    """

    DEFAULT_TIMEOUT = 15000  # milisegundos

    def __init__(self, tienda_nombre):
        self.tienda = tienda_nombre
        self.user_agents = self._obtener_user_agents()
        self.playwright_instance = None
        self.browser = None
        self.context = None
        self.page = None
        self.logger = logging.getLogger(f"{__name__}.{self.tienda.replace(' ', '')}Scraper") # Logger específico por tienda

    def _obtener_user_agents(self):
        """Obtiene la lista de user agents desde el archivo."""
        user_agents_list = []
        current_dir = os.path.dirname(os.path.abspath(__file__))
        filepath = os.path.join(current_dir, "user_agents.txt")

        try:
            with open(filepath, 'r') as file:
                for line in file:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        user_agents_list.append(line)
            if not user_agents_list:
                raise FileNotFoundError # Tratar archivo vacío (sin user agents válidos) como no encontrado
            self.logger.debug(f"Cargados {len(user_agents_list)} User-Agents desde '{filepath}'")
        except FileNotFoundError:
            self.logger.warning(f"Archivo User-Agents '{filepath}' no encontrado o vacío. Usando User-Agent por defecto.")
            user_agents_list = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ]
        return user_agents_list

    async def _start_browser(self, headless=True, browser_type='chromium'):
        """Inicia Playwright, el navegador, contexto y página."""
        self.logger.info(f"Iniciando instancia de Playwright y navegador {browser_type} (headless={headless})...")
        try:
            self.playwright_instance = await async_playwright().start()
        except Exception as e:
            self.logger.error(f"Error al iniciar Playwright: {e}")
            raise # Re-lanzar para que el método `buscar` lo maneje

        if browser_type == 'chromium':
            browser_launcher = self.playwright_instance.chromium
        elif browser_type == 'firefox':
            browser_launcher = self.playwright_instance.firefox
        elif browser_type == 'webkit':
            browser_launcher = self.playwright_instance.webkit
        else:
            raise ValueError(f"Navegador no soportado: {browser_type}")

        self.browser = await browser_launcher.launch(
            headless=headless,
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu', # A menudo recomendado en headless
                '--disable-background-timer-throttling',
                '--disable-backgrounding-occluded-windows',
                '--disable-renderer-backgrounding'
            ]
        )

        self.context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080}, # Viewport estándar
            user_agent=random.choice(self.user_agents),
            java_script_enabled=True,
            ignore_https_errors=True
        )
        self.logger.debug("Contexto del navegador creado.")

        # Bloqueo de recursos (opcional, pero puede acelerar)
        # Es importante asegurarse de que esto no rompa la funcionalidad del sitio o la detección de elementos.
        resource_block_enabled = True # Cambiar a False para deshabilitar el bloqueo de recursos
        if resource_block_enabled:
            self.logger.debug("Habilitando bloqueo de recursos (imágenes, css, fuentes, trackers).")
            try:
                await self.context.route("**/*.{png,jpg,jpeg,gif,webp,svg,ico}", lambda route: route.abort())
                # No bloquear CSS por defecto ya que puede afectar la estructura de la página y selectores.
                # await self.context.route("**/*.{css}", lambda route: route.abort())
                await self.context.route("**/*.{woff,woff2,ttf,otf}", lambda route: route.abort()) # Fuentes

                common_block_patterns = [
                    "**/google-analytics.com/**", "**/googletagmanager.com/**",
                    "**/facebook.net/**", "**/facebook.com/**", "**/fbcdn.net/**",
                    "**/doubleclick.net/**", "**/googleadservices.com/**",
                    "**/scorecardresearch.com/**", "**/criteo.com/**", "**/adnxs.com/**",
                    "**/optimizely.com/**", "**/mixpanel.com/**"
                ]
                for pattern in common_block_patterns:
                    await self.context.route(pattern, lambda route: route.abort())
            except Exception as e:
                self.logger.warning(f"No se pudo aplicar el bloqueo de recursos: {e}")

        self.page = await self.context.new_page()
        self.logger.info("Navegador y página listos.")

    async def _close_browser(self):
        """Cierra la página, contexto, navegador e instancia de Playwright."""
        self.logger.info("Cerrando navegador y Playwright...")
        try:
            if self.page and not self.page.is_closed():
                await self.page.close()
                self.logger.debug("Página cerrada.")
            if self.context:
                await self.context.close()
                self.logger.debug("Contexto cerrado.")
            if self.browser:
                await self.browser.close()
                self.logger.debug("Navegador cerrado.")
            if self.playwright_instance:
                # No hay un método stop explícito en la instancia devuelta por async_playwright().start()
                # La gestión de la instancia de Playwright (proceso) es manejada por el objeto `Playwright` en sí.
                # Al cerrar el navegador, los recursos principales se liberan.
                # playwright_instance.stop() es para el objeto Playwright global si se usó `playwright.stop()`.
                # Aquí, simplemente limpiamos la referencia.
                self.playwright_instance = None
                self.logger.debug("Instancia de Playwright (referencia) limpiada.")
        except Exception as e:
            self.logger.error(f"Error al cerrar el navegador: {e}")
        self.logger.info("Navegador cerrado.")


    def _clean_price(self, price_text):
        """Utilidad para limpiar texto de precios y convertir a float."""
        if price_text is None:
            self.logger.debug("Texto de precio es None, devolviendo 0.0")
            return 0.0
        if price_text is None: return 0.0
        try:
            # Primero, quitar símbolos de moneda comunes y espacios
            cleaned = str(price_text).replace('S/', '').replace('$', '').replace('€', '').strip()
            # Quitar separadores de miles (puntos o comas)
            # Asumir que el último punto o coma es el separador decimal
            if '.' in cleaned and ',' in cleaned: # Ej: 1.234,50 o 1,234.50
                if cleaned.rfind('.') > cleaned.rfind(','): # Decimal es punto: 1,234.50
                    cleaned = cleaned.replace(',', '')
                else: # Decimal es coma: 1.234,50
                    cleaned = cleaned.replace('.', '').replace(',', '.')
            elif '.' in cleaned: # Solo puntos, ej: 1.234.50 (mal) o 1234.50 (bien)
                 if cleaned.count('.') > 1: # Si hay más de un punto, son separadores de miles
                     cleaned = cleaned.replace('.', '', cleaned.count('.') -1)
            elif ',' in cleaned: # Solo comas, ej: 1,234,50 (mal) o 1234,50 (bien)
                if cleaned.count(',') > 1:
                     cleaned = cleaned.replace(',', '', cleaned.count(',') -1)
                cleaned = cleaned.replace(',', '.') # Convertir coma decimal a punto

            # Quitar cualquier cosa que no sea dígito o el único punto decimal
            cleaned = re.sub(r'[^\d.]', '', cleaned)
            if cleaned:
                return float(cleaned)
            else:
                self.logger.debug(f"Texto de precio '{price_text}' resultó en string vacío después de limpiar.")
                return 0.0
        except (ValueError, TypeError) as e:
            self.logger.error(f"Error al convertir precio '{price_text}' a float: {e}")
            return 0.0

    def _build_full_url(self, base_url, relative_url):
        """Construye una URL completa a partir de una URL base y una relativa."""
        if not base_url: # Si no hay base_url, no se puede construir una URL completa desde una relativa.
            self.logger.warning(f"No se proporcionó base_url para URL relativa '{relative_url}'.")
            # Si la URL relativa ya es absoluta, se devuelve. Si no, podría devolverse vacía o la relativa tal cual.
            if relative_url and (relative_url.startswith('http://') or relative_url.startswith('https://') or relative_url.startswith('//')):
                 if relative_url.startswith('//'): return "https:" + relative_url
                 return relative_url
            return relative_url if relative_url else ""


        if not relative_url or not isinstance(relative_url, str):
            return "" # O retornar None, o la URL de placeholder
        if relative_url.startswith('http://') or relative_url.startswith('https://') or relative_url.startswith('//'):
            if relative_url.startswith('//'): # Protocol-relative URL
                return "https:" + relative_url # Asumir https
            return relative_url

        # Asegurar que la base_url termine con / y relative_url no empiece con /
        return base_url.rstrip('/') + '/' + relative_url.lstrip('/')

    def _is_valid_product_data(self, data):
        """Valida que los datos del producto sean válidos."""
        return (
            data and
            isinstance(data, dict) and
            data.get('nombre') and
            data.get('precio', 0.0) > 0 and # Permitir precios > 0
            data.get('link')
        )

    # --- Métodos auxiliares de Playwright ---
    async def _query_selector(self, parent_locator, selector, timeout=DEFAULT_TIMEOUT):
        try:
            element = await parent_locator.query_selector(selector, timeout=timeout)
            if not element:
                self.logger.debug(f"Selector '{selector}' no encontrado en {self.tienda} (padre: {parent_locator}).")
                return None
            return element
        except PlaywrightTimeoutError:
            self.logger.warning(f"Timeout ({timeout}ms) esperando por selector '{selector}' en {self.tienda} (padre: {parent_locator}).")
            return None
        except PlaywrightError as e:
            self.logger.error(f"Error de Playwright al buscar selector '{selector}': {e}")
            return None

        except PlaywrightError as e:
            self.logger.error(f"Error de Playwright al buscar selectores '{selector}' con query_selector_all: {e}")
            return [] # Retornar lista vacía en caso de error
        return await parent_locator.query_selector_all(selector) # Esta línea estaba duplicada, la elimino de aquí.
                                                                # La lógica correcta es retornarla dentro del try o una lista vacía en except.
                                                                # Corregido: la retornamos aquí porque si no hay error, es lo que queremos.

    async def _get_text_content(self, element_handle, default=""):
        if element_handle:
            try:
                text = await element_handle.text_content()
                return (text or default).strip()
            except PlaywrightError as e:
                self.logger.debug(f"Error obteniendo text_content (puede ser normal si el elemento se desprendió): {e}")
                return default
        return default

    async def _get_attribute(self, element_handle, attribute, default=""):
        if element_handle:
            try:
                attr_value = await element_handle.get_attribute(attribute)
                return (attr_value or default)
            except PlaywrightError as e:
                self.logger.debug(f"Error obteniendo atributo '{attribute}' (puede ser normal si el elemento se desprendió): {e}")
                return default
        return default

    async def _click_selector(self, selector, timeout=DEFAULT_TIMEOUT, **kwargs):
        try:
            self.logger.debug(f"Intentando hacer clic en selector '{selector}'")
            element = await self.page.wait_for_selector(selector, state='visible', timeout=timeout)
            await element.click(**kwargs)
            self.logger.debug(f"Clic exitoso en selector '{selector}'")
            return True
        except PlaywrightTimeoutError:
            self.logger.warning(f"Timeout al intentar hacer clic en '{selector}' en {self.tienda}")
            return False
        except PlaywrightError as e:
            self.logger.error(f"Error de Playwright al hacer clic en '{selector}' en {self.tienda}: {e}")
            return False

    # --- Métodos abstractos que deben ser implementados por cada scraper hijo ---
    @abstractmethod
    async def _get_base_url(self):
        """Retorna la URL base de la tienda (puede ser síncrono)."""
        pass

    @abstractmethod
    async def _navigate_to_search(self, producto: str) -> bool:
        """Navega a la página de la tienda y realiza la búsqueda del producto. Retorna True si tuvo éxito."""
        pass

    @abstractmethod
    async def _get_product_elements(self) -> list: # Debería retornar list[ElementHandle]
        """Retorna la lista de elementos de producto (ElementHandle) en la página actual."""
        pass

    @abstractmethod
    async def _extract_data_from_element(self, element_handle) -> dict | None:
        """Extrae los datos (nombre, precio, link, etc.) de un ElementHandle de producto."""
        pass

    @abstractmethod
    async def _go_to_next_page(self) -> bool:
        """Navega a la siguiente página. Retorna True si fue exitoso, False si no hay más páginas o error."""
        pass

    # --- Método principal de scraping ---
    async def _process_page_data(self, pagina_actual: int, producto_buscado: str) -> list:
        """Procesa una página individual y retorna los productos encontrados."""
        self.logger.info(f"Procesando página {pagina_actual} para '{producto_buscado}'")

        product_elements = await self._get_product_elements()
        if not product_elements:
            self.logger.info(f"No se encontraron elementos de producto en la página {pagina_actual}.")
            return []

        self.logger.debug(f"Encontrados {len(product_elements)} posibles elementos de producto en página {pagina_actual}.")
        productos_pagina = []

        # Usar asyncio.gather para procesar elementos concurrentemente
        tasks = [self._extract_data_from_element(element) for element in product_elements]
        results = await asyncio.gather(*tasks, return_exceptions=True) # Capturar excepciones de extracción

        for i, res_or_exc in enumerate(results):
            if isinstance(res_or_exc, Exception):
                self.logger.error(f"Error extrayendo datos del elemento {i+1} en pág {pagina_actual}: {res_or_exc}", exc_info=False) # exc_info=False para no duplicar traceback si ya se logueó dentro
            elif res_or_exc and self._is_valid_product_data(res_or_exc):
                productos_pagina.append(res_or_exc)
            elif res_or_exc: # Datos extraídos pero no válidos
                 self.logger.debug(f"Datos de producto extraídos del elemento {i+1} pero no válidos: {res_or_exc}")

        self.logger.info(f"{len(productos_pagina)} productos válidos encontrados en página {pagina_actual}.")
        return productos_pagina

    async def buscar(self, producto: str, max_paginas: int = 3) -> list:
        """Método principal para buscar productos usando Playwright."""
        self.logger.info(f"Iniciando búsqueda para '{producto}' (max_paginas={max_paginas}).")
        resultados_totales = []
        browser_started_by_this_instance = False
        try:
            if not self.playwright_instance: # Permitir reutilizar navegador si ya está iniciado externamente
                await self._start_browser()
                browser_started_by_this_instance = True

            if not await self._navigate_to_search(producto):
                self.logger.error(f"Fallo en la navegación inicial o búsqueda de '{producto}'.")
                if browser_started_by_this_instance: await self._close_browser()
                return resultados_totales

            self.logger.info(f"Navegación y búsqueda inicial para '{producto}' completada. URL: {self.page.url}")
            await self.page.wait_for_timeout(random.randint(2500, 4500)) # Pausa para carga dinámica

            for pagina_num in range(1, max_paginas + 1):
                productos_encontrados_pagina = await self._process_page_data(pagina_num, producto)
                resultados_totales.extend(productos_encontrados_pagina)

                if pagina_num < max_paginas:
                    self.logger.info(f"Intentando ir a la página siguiente ({pagina_num + 1})...")
                    if not await self._go_to_next_page():
                        self.logger.info("No hay más páginas o no se pudo navegar a la siguiente.")
                        break
                    self.logger.info(f"Navegado a página {pagina_num + 1}. URL: {self.page.url}")
                    await self.page.wait_for_timeout(random.randint(3000, 5000)) # Pausa post-navegación
                else:
                    self.logger.info(f"Límite de {max_paginas} páginas alcanzado.")

            self.logger.info(f"Búsqueda para '{producto}' completada. Total: {len(resultados_totales)} productos.")

        except PlaywrightTimeoutError as pte:
            self.logger.error(f"Playwright Timeout Error durante la búsqueda de '{producto}': {pte}", exc_info=True)
        except PlaywrightError as pe:
            self.logger.error(f"Playwright Error durante la búsqueda de '{producto}': {pe}", exc_info=True)
        except Exception as e:
            self.logger.error(f"Error general en el scraper '{self.tienda}' para '{producto}': {e}", exc_info=True)
        finally:
            if browser_started_by_this_instance: # Solo cerrar si este método lo inició
                await self._close_browser()
            else:
                self.logger.info("El navegador no fue iniciado por esta instancia de búsqueda, no se cerrará aquí.")
        return resultados_totales

# Wrapper para ejecutar desde código síncrono (si es necesario fuera de un contexto async)
# def run_scraper_sync(scraper_instance, producto, max_paginas=3):
# return asyncio.run(scraper_instance.buscar(producto, max_paginas))
