import asyncio
import re
import random
from playwright.async_api import async_playwright

async def _extract_product_data(item, base_url="https://simple.ripley.com.pe"):
    """Extrae los datos de un elemento de producto individual."""
    try:
        # Extraer nombre
        nombre_elem = await item.query_selector("div.catalog-product-details__name")
        nombre = await nombre_elem.inner_text() if nombre_elem else ""
        
        if not nombre:
            return None
        
        # Extraer link
        link_elem = await item.query_selector("a.catalog-product-item")
        link_relativo = await link_elem.get_attribute("href") if link_elem else ""
        
        if not link_relativo:
            return None
        
        link = f"{base_url}{link_relativo}"
        
        # Extraer precio
        precio_elem = await item.query_selector("li.catalog-prices__offer-price")
        precio_text = await precio_elem.inner_text() if precio_elem else "0"
        
        # Limpiar y convertir precio
        precio_limpio = re.sub(r"[^\d.]", "", precio_text)
        try:
            precio = float(precio_limpio) if precio_limpio else 0.0
        except ValueError:
            precio = 0.0
        
        if precio <= 0:
            return None
        
        # Extraer imagen
        imagen_elem = await item.query_selector(".images-preview-item.is-active img")
        imagen_src = await imagen_elem.get_attribute("src") if imagen_elem else ""  
        imagen = f"https://www.ripley.com.pe{imagen_src}" if imagen_src and not imagen_src.startswith('http') else imagen_src
        
        # Extraer descuento
        descuento_porcentaje = None
        descuento_tag = await item.query_selector('div.catalog-product-details__discount-tag')
        if descuento_tag:
            descuento_texto = await descuento_tag.inner_text()
            try:
                descuento_porcentaje = int(descuento_texto.replace('%', '').replace('-', ''))
            except (ValueError, AttributeError):
                descuento_porcentaje = None
        
        return {
            'nombre': nombre.strip(),
            'precio': precio,
            'link': link,
            'tienda': 'ripley',
            'imagen': imagen,
            'descuento': descuento_porcentaje
        }
        
    except Exception:
        return None

async def _setup_browser_context():
    """Configura el navegador con optimizaciones."""
    p = async_playwright()
    playwright_instance = await p.start()
    
    browser = await playwright_instance.chromium.launch(
        headless=True,
        args=[
            '--no-sandbox',
            '--disable-dev-shm-usage',
            '--disable-gpu',
            '--disable-background-timer-throttling',
            '--disable-backgrounding-occluded-windows',
            '--disable-renderer-backgrounding'
        ]
    )
    
    context = await browser.new_context(
        viewport={'width': 1920, 'height': 1080},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    
    # Bloquear recursos innecesarios
    await context.route("**/*.{png,jpg,jpeg,gif,webp}", lambda route: route.abort())
    await context.route("**/*.{css,woff,woff2,ttf}", lambda route: route.abort())
    await context.route("**/analytics/**", lambda route: route.abort())
    await context.route("**/gtm/**", lambda route: route.abort())
    await context.route("**/facebook.com/**", lambda route: route.abort())
    await context.route("**/google-analytics.com/**", lambda route: route.abort())
    
    return browser, context, playwright_instance

async def _process_page_items(page):
    """Procesa todos los elementos de producto en una página."""
    items = await page.query_selector_all("div.catalog-product-item")
    productos = []
    
    for item in items:
        producto_data = await _extract_product_data(item)
        if producto_data:
            productos.append(producto_data)
    
    return productos

async def _navigate_to_next_page(page):
    """Navega a la siguiente página si está disponible."""
    next_button = await page.query_selector("a.page-link[aria-label='Siguiente']:not(.disabled)")
    if next_button:
        await next_button.click()
        await page.wait_for_timeout(random.randint(2000, 4000))
        return True
    return False

async def buscar_en_ripley_playwright(producto):
    """
    Scraper de Ripley usando Playwright para mejor rendimiento.
    Utiliza asincronía y optimizaciones de carga para mayor velocidad.
    """
    resultados = []
    browser = None
    context = None
    playwright_instance = None
    
    try:
        print(f"Iniciando búsqueda en Ripley con Playwright para: {producto}")
        
        # Configurar navegador
        browser, context, playwright_instance = await _setup_browser_context()
        page = await context.new_page()
        
        # Navegar a Ripley y buscar
        await page.goto("https://www.ripley.com.pe/", timeout=60000)
        search_input = await page.wait_for_selector('input[type="search"]', timeout=15000)
        await search_input.fill(producto)
        await search_input.press('Enter')
        
        # Procesar páginas
        max_paginas = 10
        for pagina_actual in range(1, max_paginas + 1):
            print(f"Ripley Playwright: procesando página {pagina_actual}")
            
            try:
                await page.wait_for_selector("div.catalog-product-item", timeout=15000)
            except Exception:
                print(f"Ripley Playwright: No se encontraron productos en la página {pagina_actual}")
                break
            
            # Procesar productos de la página actual
            productos_pagina = await _process_page_items(page)
            resultados.extend(productos_pagina)
            
            print(f"Ripley Playwright: {len(productos_pagina)} productos encontrados en página {pagina_actual}")
            
            # Intentar ir a la siguiente página
            if pagina_actual < max_paginas:
                if not await _navigate_to_next_page(page):
                    print("Ripley Playwright: No hay más páginas disponibles")
                    break
        
        print(f"Ripley Playwright: Búsqueda completada. Total: {len(resultados)} productos")
        
    except Exception as e:
        print(f"Error en el scraper de Ripley con Playwright: {e}")
    finally:
        if context:
            await context.close()
        if browser:
            await browser.close()
        if playwright_instance:
            await playwright_instance.stop()
    
    return resultados

def buscar_en_ripley_async_wrapper(producto):
    """Wrapper para ejecutar la función asíncrona desde código síncrono."""
    return asyncio.run(buscar_en_ripley_playwright(producto))

# Para pruebas directas
if __name__ == '__main__':
    import time
    
    start_time = time.time()
    productos = asyncio.run(buscar_en_ripley_playwright("laptop"))
    end_time = time.time()
    
    print("\n=== RESULTADOS DE PRUEBA ===")
    print(f"Productos encontrados: {len(productos)}")
    print(f"Tiempo total: {end_time - start_time:.2f} segundos")
    
    if productos:
        print("\nPrimer producto encontrado:")
        print(f"- Nombre: {productos[0]['nombre']}")
        print(f"- Precio: S/ {productos[0]['precio']:.2f}")
        print(f"- Tienda: {productos[0]['tienda']}")
        print(f"- Link: {productos[0]['link']}")
