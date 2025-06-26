import os
import logging
import json
import time
import asyncio
import threading
from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
# Scrapers refactorizados para Playwright
from .scrapers.ripley_playwright import buscar_en_ripley_async_wrapper # Ya era Playwright, ahora usa BasePlaywrightScraper
from .scrapers.falabella import buscar_en_falabella        # Ahora Playwright
from .scrapers.oechsle import buscar_en_oechsle          # Ahora Playwright
from .scrapers.estilos import buscar_en_estilos            # Ahora Playwright
from .scrapers.tailoy import buscar_en_tailoy            # Ahora Playwright
from .scrapers.realplaza import buscar_en_realplaza        # Ahora Playwright
from .scrapers.plazavea import buscar_en_plazavea          # Ahora Playwright
from .scrapers.hiraoka import buscar_en_hiraoka          # Ahora Playwright
from .scrapers.metro import buscar_en_metro              # Ahora Playwright

from .notifications import enviar_notificacion_async, validar_numero_telefono, enviar_notificacion_bajada_precio_async
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configurar logging
# logging.getLogger().setLevel(logging.ERROR) # Ya no se usa esta configuración global
logging.getLogger('urllib3').setLevel(logging.ERROR)


# app.py ahora está en backend/, frontend/ está en ../frontend
STATIC_FOLDER_PATH = os.path.join(os.path.dirname(__file__), '../frontend')

app = Flask(__name__)

# Configuración del logger de Flask
# Establecer el nivel de logging para la app. DEBUG es muy verboso, INFO es bueno para producción.
app.logger.setLevel(logging.INFO)
# Evitar que los logs se propaguen al logger raíz si se desea un manejo aislado.
# app.propagate_exceptions = False # Esto es para excepciones, no para logs directamente.
# app.logger.propagate = False

# Formato para los logs de la aplicación
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# Añadir un handler (ej. StreamHandler para la consola) si no lo tiene por defecto Gunicorn/Flask
if not app.logger.handlers:
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    app.logger.addHandler(stream_handler)
    # También se podría añadir un FileHandler para guardar logs en un archivo:
    # file_handler = logging.FileHandler('app.log')
    # file_handler.setFormatter(formatter)
    # app.logger.addHandler(file_handler)

# Configurar Flask app para servir estáticos y CORS
app.static_folder = STATIC_FOLDER_PATH
app.static_url_path = ''
CORS(app)


# Asegurarse de que las rutas sean absolutas (aunque STATIC_FOLDER_PATH ya lo es)
# BASE_DIR ya no se usa directamente para STATIC_FOLDER en la app, pero puede ser útil para otras cosas.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# STATIC_FOLDER se usa en las rutas index() y serve_static(), así que lo actualizamos también.
STATIC_FOLDER = STATIC_FOLDER_PATH

# Configuración de recursos y timeouts
MAX_WORKERS = 2  # Reducir workers
TIMEOUT = 600  # Aumentar timeout a 10 minutos
MAX_TIENDAS = 0  # 0 o negativo para procesar todas las tiendas, N para las primeras N

# Almacenamiento en memoria para el historial de precios de productos
# La clave será una tupla (nombre_tienda, url_producto) para identificar unívocamente el producto
# El valor será un diccionario {'precio': float, 'timestamp': datetime}
product_price_history = {}
# Umbral de descuento para notificar (ej. 0.8 para 80%)
PRICE_DROP_THRESHOLD = 0.80

# Almacenamiento en memoria para suscripciones de alertas de bajada de precio
# Clave: (product_name_lowercase, user_identifier, channel_lowercase)
# Valor: {'product_name': str,
#         'user_identifier': str, # phone_number for whatsapp, chat_id for telegram
#         'notification_channel': str, # 'whatsapp' or 'telegram'
#         'desired_discount_percentage': float,
#         'last_known_prices': {product_store_url_key: price},
#         'notified_for_price': {product_store_url_key: price}
#        }
price_alert_subscriptions = {}

# List of all scraper functions and their names, to be used by the background job
# This should ideally be dynamically populated or managed if scrapers are added/removed frequently
ALL_SCRAPERS = [
    ('Ripley', buscar_en_ripley_async_wrapper),
    ('Falabella', buscar_en_falabella),
    ('Oechsle', buscar_en_oechsle),
    ('Estilos', buscar_en_estilos),
    ('Tailoy', buscar_en_tailoy),
    ('Real Plaza', buscar_en_realplaza),
    ('Plaza Vea', buscar_en_plazavea),
    ('Hiraoka', buscar_en_hiraoka),
    ('Metro', buscar_en_metro),
]

def run_scraper_for_product(scraper_func, product_name):
    """Helper to run a single scraper and handle its exceptions."""
    try:
        return scraper_func(product_name)
    except Exception as e:
        app.logger.error(f"Background scraper {scraper_func.__name__} failed for '{product_name}': {e}")
        return []

def check_subscribed_product_prices():
    """
    Background job to check prices for all subscribed products.
    This function will be executed by APScheduler.
    """
    with app.app_context(): # Need app context for logging and config
        app.logger.info("Background job: Starting check_subscribed_product_prices.")

        if not price_alert_subscriptions:
            app.logger.info("Background job: No active subscriptions. Skipping price checks.")
            return

        # Create a set of unique product names to search for to avoid redundant scraping
        unique_product_names_to_search = set()
        for sub_data in price_alert_subscriptions.values():
            unique_product_names_to_search.add(sub_data['product_name'])

        # Store all scraped results for all unique subscribed products
        # Key: product_name_original_case, Value: list of all items found across all stores
        all_scraped_results_map = {}

        # Use ThreadPoolExecutor for scraping in parallel within the job
        # MAX_WORKERS_JOB can be different from the API's MAX_WORKERS
        MAX_WORKERS_JOB = max(1, MAX_WORKERS // 2 if MAX_WORKERS > 1 else 1)

        for product_name_to_search in unique_product_names_to_search:
            app.logger.info(f"Background job: Scraping for subscribed product '{product_name_to_search}'.")
            current_product_results = []

            # We need to run all scrapers for this one product name
            # This can be slow if many products and many scrapers.
            # Consider if a global scrape then filter is better, or per-product scrape.
            # For now, per-product scrape to keep it aligned with subscription logic.

            scraper_futures = {}
            with ThreadPoolExecutor(max_workers=MAX_WORKERS_JOB) as executor:
                for store_name, scraper_func in ALL_SCRAPERS:
                    future = executor.submit(run_scraper_for_product, scraper_func, product_name_to_search)
                    scraper_futures[future] = store_name

                for future in as_completed(scraper_futures):
                    store_name = scraper_futures[future]
                    try:
                        store_results = future.result(timeout=TIMEOUT) # Use existing TIMEOUT
                        if store_results:
                            # Ensure items from this scraper have the store_name if not already present
                            for item in store_results:
                                item['tienda'] = item.get('tienda', store_name) # Ensure tienda field
                            current_product_results.extend(store_results)
                            app.logger.info(f"Background job: Found {len(store_results)} items for '{product_name_to_search}' from {store_name}.")
                    except TimeoutError:
                        app.logger.error(f"Background job: Timeout scraping {store_name} for '{product_name_to_search}'.")
                    except Exception as e:
                        app.logger.error(f"Background job: Error scraping {store_name} for '{product_name_to_search}': {e}", exc_info=True)

            all_scraped_results_map[product_name_to_search] = current_product_results
            app.logger.info(f"Background job: Finished scraping for '{product_name_to_search}', found {len(current_product_results)} total items.")

        # Now, iterate through subscriptions and check against the scraped results
        for sub_key, subscription in list(price_alert_subscriptions.items()): # Use list() for safe iteration if modifying
            product_name_subscribed = subscription['product_name']
            user_identifier = subscription['user_identifier']
            notification_channel = subscription['notification_channel']
            desired_discount = subscription['desired_discount_percentage'] # This is a fraction, e.g., 0.2

            # Get the results for the product this subscription is for
            # The product_name_subscribed should match one of the keys in all_scraped_results_map
            scraped_items_for_this_product = all_scraped_results_map.get(product_name_subscribed, [])

            if not scraped_items_for_this_product:
                app.logger.info(f"Background job: No items found for subscribed product '{product_name_subscribed}' (sub_key: {sub_key}) during this check. Skipping notifications for this sub.")
                # Update last_known_prices to empty or keep old ones? For now, keep old ones if nothing found.
                # Or, if it was previously found and now isn't, it might be "out of stock".
                # This part needs more thought on how to handle "product not found" for existing subscriptions.
                continue

            app.logger.info(f"Background job: Processing {len(scraped_items_for_this_product)} scraped items for subscription '{product_name_subscribed}' for {user_identifier} via {notification_channel} (sub_key: {sub_key}).")

            for item in scraped_items_for_this_product:
                if 'link' not in item or not item['link'] or 'precio' not in item:
                    app.logger.warning(f"Background job: Scraped item for '{product_name_subscribed}' is missing link or price: {item.get('nombre', 'N/A')}")
                    continue

                # tienda_name should be present due to augmentation during scraping
                tienda_name = item.get('tienda', 'UnknownStore').lower()
                item_product_key = (tienda_name, item['link'])
                new_price = item['precio']

                last_known_price_for_item = subscription['last_known_prices'].get(item_product_key)

                if last_known_price_for_item is not None: # We have a price history for this specific item (URL) in this store
                    if new_price < last_known_price_for_item:
                        actual_discount = (last_known_price_for_item - new_price) / last_known_price_for_item
                        app.logger.info(f"Background job: Price drop for '{item['nombre']}' ({item_product_key}) from S/{last_known_price_for_item} to S/{new_price}. Actual discount: {actual_discount*100:.2f}%. Desired: {desired_discount*100:.2f}%.")

                        if actual_discount >= desired_discount:
                            # Check if already notified for this price or a very similar one to avoid spam
                            previously_notified_price = subscription['notified_for_price'].get(item_product_key)
                            # Using a small tolerance for price comparison to avoid issues with float precision
                            if previously_notified_price is None or not (abs(previously_notified_price - new_price) < 0.01): # e.g. 1 cent tolerance
                                app.logger.info(f"Background job: Discount threshold met for '{item['nombre']}' for {user_identifier} via {notification_channel}. Sending notification.")

                                # Ensure 'tienda' field is correctly capitalized for notification if needed
                                item_for_notification = item.copy()
                                item_for_notification['tienda'] = item.get('tienda', tienda_name.title()) # Capitalize store name for notification

                                enviar_notificacion_bajada_precio_async(
                                    user_identifier, # This is now chat_id or phone_number
                                    item_for_notification,
                                    last_known_price_for_item,
                                    new_price,
                                    actual_discount * 100, # Pass percentage
                                    notification_channel=notification_channel
                                )
                                subscription['notified_for_price'][item_product_key] = new_price
                            else:
                                app.logger.info(f"Background job: Already notified for a similar price S/{previously_notified_price} for '{item['nombre']}' ({item_product_key}) for {user_identifier} via {notification_channel}. Skipping duplicate notification.")
                        else:
                             app.logger.info(f"Background job: Price drop for '{item['nombre']}' did not meet desired discount {desired_discount*100:.2f}%. Actual: {actual_discount*100:.2f}%.")
                else:
                    app.logger.info(f"Background job: New item '{item['nombre']}' ({item_product_key}) found for subscription '{product_name_subscribed}'. Price: S/{new_price}. Storing price, no discount comparison yet.")

                # Update last known price for this item in the subscription
                subscription['last_known_prices'][item_product_key] = new_price

        app.logger.info("Background job: Finished check_subscribed_product_prices.")


# Scheduler setup
scheduler = BackgroundScheduler(daemon=True)
# Configure the job to run, e.g., every 4 hours.
# For testing, you might use a shorter interval like 'interval', minutes=1
# Ensure job_defaults are reasonable, e.g., coalesce=True to prevent multiple queued runs if scheduler was down.
# misfire_grace_time can also be important.
scheduler.add_job(check_subscribed_product_prices, 'interval', hours=4, coalesce=True, misfire_grace_time=3600) # Check every 4 hours

# It's important to start the scheduler only once, typically not when Flask's reloader is active in debug mode.
# A common pattern is to start it if not os.environ.get('WERKZEUG_RUN_MAIN'):
# However, for simplicity in this context and assuming it might be run with gunicorn in prod:
# For now, let's ensure it starts when the app module is loaded.
# If running with Flask dev server (debug=True), it might run twice.
# A better approach for production is to manage this outside the app.run() call or use Flask-APScheduler extension.
if not scheduler.running:
    scheduler.start()
    app.logger.info("APScheduler started for background price checks.")
    # It's good practice to also handle shutdown:
    import atexit
    atexit.register(lambda: scheduler.shutdown() if scheduler.running else None)


@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(app.static_folder, path)

@app.route('/')
def index():
    index_path = os.path.join(STATIC_FOLDER, 'index.html')
    if os.path.exists(index_path):
        return send_from_directory(STATIC_FOLDER, 'index.html')
    return "No index.html file found in the static folder."

# La función run_async_scraper ya no es necesaria si cada `buscar_en_TIENDA` maneja asyncio.run()

@app.route('/buscar', methods=['GET'])
def buscar():
    producto = request.args.get('producto')
    telefono = request.args.get('telefono', '').strip()
    notificar = request.args.get('notificarWsp', '').lower() == 'true'

    app.logger.info(f"Solicitud /buscar recibida. Producto: '{producto}', Notificar: {notificar}, Teléfono: {'********' if telefono else 'N/A'}")

    if not producto:
        app.logger.warning("Intento de búsqueda sin producto.")
        return jsonify({'error': 'No se ingresó un producto'}), 400

    # Validar teléfono si se solicita notificación
    if notificar and telefono:
        es_valido, telefono_limpio, error_val_tel = validar_numero_telefono(telefono) # Renombrar variable error
        if not es_valido:
            app.logger.warning(f"Número de teléfono inválido: {telefono} - Error: {error_val_tel}")
            return jsonify({'error': f'Número de teléfono inválido: {error_val_tel}'}), 400
        telefono = telefono_limpio
        app.logger.info(f"Número de teléfono validado: {telefono}")


    def generate():
        resultados = []
        app.logger.info(f"Iniciando generación de resultados para: '{producto}'")

        # Todas las tiendas ahora usan Playwright y sus wrappers síncronos
        tiendas = [
            ('Ripley', buscar_en_ripley_async_wrapper),
            ('Falabella', buscar_en_falabella),
            ('Oechsle', buscar_en_oechsle),
            ('Estilos', buscar_en_estilos),
            ('Tailoy', buscar_en_tailoy),
            ('Real Plaza', buscar_en_realplaza),
            ('Plaza Vea', buscar_en_plazavea),
            ('Hiraoka', buscar_en_hiraoka),
            ('Metro', buscar_en_metro),
        ]

        # Limitar el número de tiendas a procesar si MAX_TIENDAS está definido y es menor
        tiendas_a_procesar = tiendas
        if MAX_TIENDAS > 0 and MAX_TIENDAS < len(tiendas):
            # Podríamos seleccionar aleatoriamente o las primeras N
            # Por ahora, las primeras N para consistencia en pruebas pequeñas
            tiendas_a_procesar = tiendas[:MAX_TIENDAS]
            # O aleatorio: random.sample(tiendas, MAX_TIENDAS) - requeriría import random

        completed = 0
        futures = {}
        start_times = {}

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            for tienda_nombre, funcion_scraper in tiendas_a_procesar:
                app.logger.info(f"Enviando tarea de scraping para '{producto}' en tienda '{tienda_nombre}' al executor.")
                future = executor.submit(funcion_scraper, producto)
                futures[future] = tienda_nombre
                start_times[tienda_nombre] = time.time()

            for future in as_completed(futures):
                tienda_display = futures[future]
                completed += 1
                tiempo_busqueda = round(time.time() - start_times.get(tienda_display, time.time()), 2)

                try:
                    app.logger.debug(f"Esperando resultado de {tienda_display} para '{producto}'...")
                    resultados_tienda = future.result(timeout=TIMEOUT) # Añadir timeout por si una tarea se cuelga

                    status = "✓" if resultados_tienda else "Sin resultados"
                    num_resultados = len(resultados_tienda) if resultados_tienda else 0
                    app.logger.info(f"Resultados de {tienda_display} para '{producto}': {num_resultados} items, Tiempo: {tiempo_busqueda}s, Estado: {status}")

                    if resultados_tienda:
                        current_time = datetime.now()
                        for item in resultados_tienda:
                            # Usar URL como parte de la clave para identificar unívocamente el producto en una tienda
                            # Algunos productos pueden no tener 'link', manejar eso.
                            if 'link' not in item or not item['link']:
                                app.logger.warning(f"Producto sin link en {tienda_display}: {item.get('nombre', 'Nombre Desconocido')}")
                                continue

                            product_key = (tienda_display.lower(), item['link'])

                            if product_key in product_price_history:
                                old_price_data = product_price_history[product_key]
                                old_price = old_price_data['precio']
                                new_price = item['precio']

                                if new_price < old_price:
                                    discount = (old_price - new_price) / old_price
                                    item['old_price'] = old_price # Añadir precio anterior para mostrar en frontend si es necesario
                                    item['discount_percentage'] = round(discount * 100, 2)
                                    app.logger.info(f"Price drop for {item['nombre']} at {tienda_display}: Old Price S/ {old_price}, New Price S/ {new_price}, Discount: {discount*100:.2f}%")

                                    # Aquí se podría añadir lógica para enviar notificaciones si el descuento supera el umbral
                                    # Por ahora, solo logueamos. La notificación real se manejará en notifications.py
                                    if discount >= PRICE_DROP_THRESHOLD:
                                        app.logger.critical(f"HUGE PRICE DROP DETECTED for {item['nombre']} at {tienda_display}: {discount*100:.2f}% discount. Old: S/{old_price}, New: S/{new_price}. Link: {item['link']}")
                                        if notificar and telefono: # Only send if user requested notifications and provided a phone number
                                            # Ensure 'tienda' is in the item, or use tienda_display
                                            item_for_notification = item.copy()
                                            if 'tienda' not in item_for_notification:
                                                item_for_notification['tienda'] = tienda_display

                                            enviar_notificacion_bajada_precio_async(
                                                telefono,
                                                item_for_notification,
                                                old_price,
                                                new_price,
                                                item['discount_percentage'], # Already calculated and stored
                                                notification_channel='whatsapp' # Explicitly WhatsApp for /buscar
                                            )
                                            app.logger.info(f"Price drop notification triggered for {item['nombre']} to {telefono} via WhatsApp.")

                            # Actualizar historial de precios
                            product_price_history[product_key] = {'precio': item['precio'], 'timestamp': current_time}

                        resultados.extend(resultados_tienda)

                    progress = {
                        'type': 'progress',
                        'store': tienda_display.title(),
                        'completed': completed,
                        'total': len(tiendas_a_procesar), # Usar tiendas_a_procesar para el total
                        'tiempo': tiempo_busqueda,
                        'status': status,
                        'resultados': num_resultados
                    }
                    yield json.dumps(progress, ensure_ascii=False).strip() + '\n'

                except TimeoutError: # Timeout de future.result()
                    app.logger.error(f"Timeout ({TIMEOUT}s) esperando resultado de {tienda_display} para '{producto}'.")
                    yield json.dumps({
                        'type': 'progress', 'store': tienda_display.title(), 'completed': completed,
                        'total': len(tiendas_a_procesar), 'tiempo': tiempo_busqueda,
                        'status': 'Error (Timeout)', 'resultados': 0
                    }, ensure_ascii=False).strip() + '\n'
                except Exception as e:
                    app.logger.error(f"Error procesando {tienda_display} para '{producto}': {e}", exc_info=True) # exc_info=True para traceback
                    yield json.dumps({
                        'type': 'progress',
                        'store': tienda_display.title(),
                        'completed': completed,
                        'total': len(tiendas_a_procesar), # Usar tiendas_a_procesar
                        'tiempo': tiempo_busqueda,
                        'status': 'Error',
                        'resultados': 0
                    }, ensure_ascii=False).strip() + '\n'

        app.logger.info(f"Todos los scrapers completados para '{producto}'. Total resultados antes de ordenar: {len(resultados)}")
        # Ordenar resultados finales
        final_results_list = sorted(resultados, key=lambda x: x['precio'])

        # Enviar notificación si se solicitó
        if notificar and telefono and final_results_list:
            app.logger.info(f"Intentando enviar notificación para '{producto}' a {telefono}")
            try:
                enviar_notificacion_async(telefono, producto, final_results_list)
                app.logger.info(f"Notificación WhatsApp programada para {telefono} sobre '{producto}'")
            except Exception as e:
                app.logger.error(f"Error programando notificación WhatsApp para {telefono}: {e}", exc_info=True)

        # Enviar resultados finales
        app.logger.info(f"Enviando {len(final_results_list)} resultados finales para '{producto}'.")
        final_results_payload = { # Renombrar variable para evitar confusión con la función
            'type': 'results',
            'results': final_results_list,
            'notificacion_enviada': notificar and telefono and bool(final_results_list)
        }
        yield json.dumps(final_results_payload, ensure_ascii=False).strip() + '\n'
        app.logger.info(f"Respuesta final enviada para '{producto}'.")

    return Response(generate(), mimetype='application/json')

@app.route('/validar-telefono', methods=['POST'])
def validar_telefono():
    """Endpoint para validar números de teléfono."""
    data = request.get_json()
    telefono = data.get('telefono', '') if data else ''

    es_valido, telefono_limpio, mensaje = validar_numero_telefono(telefono)

    return jsonify({
        'valido': es_valido,
        'telefono_limpio': telefono_limpio,
        'mensaje': mensaje
    })

@app.route('/test-playwright')
def test_playwright():
    """Endpoint para probar el scraper de Playwright."""
    try:
        productos = buscar_en_ripley_async_wrapper("laptop")
        return jsonify({
            'success': True,
            'productos_encontrados': len(productos),
            'muestra': productos[:3] if productos else []
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, timeout=TIMEOUT)


@app.route('/subscribe-price-alert', methods=['POST'])
def subscribe_price_alert():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    product_name = data.get('product_name')
    user_identifier_raw = data.get('user_identifier') # Can be phone for WhatsApp or chat_id for Telegram
    notification_channel_raw = data.get('notification_channel', 'whatsapp').lower() # Default to whatsapp
    desired_discount_percentage_str = data.get('desired_discount_percentage')

    if not all([product_name, user_identifier_raw, desired_discount_percentage_str]):
        return jsonify({'error': 'Missing fields: product_name, user_identifier, or desired_discount_percentage are required'}), 400

    if notification_channel_raw not in ['whatsapp', 'telegram']:
        return jsonify({'error': "Invalid notification_channel. Must be 'whatsapp' or 'telegram'."}), 400

    user_identifier_clean = ""
    if notification_channel_raw == 'whatsapp':
        is_valid_phone, clean_phone, phone_error_msg = validar_numero_telefono(user_identifier_raw)
        if not is_valid_phone:
            return jsonify({'error': f'Invalid phone number for WhatsApp: {phone_error_msg}'}), 400
        user_identifier_clean = clean_phone
    elif notification_channel_raw == 'telegram':
        # Basic validation for chat_id (string of digits, possibly negative for groups/channels)
        if not (isinstance(user_identifier_raw, str) and user_identifier_raw.lstrip('-').isdigit()):
            return jsonify({'error': 'Invalid chat_id for Telegram. Must be a string of digits (optionally starting with -).'}), 400
        user_identifier_clean = user_identifier_raw

    try:
        desired_discount_percentage = float(desired_discount_percentage_str)
        if not (0 < desired_discount_percentage <= 100):
            raise ValueError("Discount percentage must be between 0 and 100.")
    except ValueError as e:
        return jsonify({'error': f'Invalid desired_discount_percentage: {e}'}), 400

    # Using a more robust key: (product_name_lowercase, user_identifier_clean, notification_channel_raw)
    subscription_key = (product_name.lower(), user_identifier_clean, notification_channel_raw)

    if subscription_key in price_alert_subscriptions:
        # Update existing subscription
        price_alert_subscriptions[subscription_key]['desired_discount_percentage'] = desired_discount_percentage / 100.0 # Store as fraction
        app.logger.info(f"Updated subscription for {product_name} by {user_identifier_clean} via {notification_channel_raw} to {desired_discount_percentage}% discount. Key: {subscription_key}")
        message = "Subscription updated successfully."
    else:
        # Add new subscription
        price_alert_subscriptions[subscription_key] = {
            'product_name': product_name,
            'user_identifier': user_identifier_clean,
            'notification_channel': notification_channel_raw,
            'desired_discount_percentage': desired_discount_percentage / 100.0,  # Store as fraction
            'last_known_prices': {},
            'notified_for_price': {}
        }
        app.logger.info(f"New subscription for {product_name} by {user_identifier_clean} via {notification_channel_raw} for {desired_discount_percentage}% discount. Key: {subscription_key}")
        message = f"Subscribed successfully to {notification_channel_raw} alerts. You will be notified if the product reaches your desired discount."

    # Returning the key as a list of strings for JSON compatibility
    return jsonify({'message': message, 'subscription_key': [str(k) for k in subscription_key]}), 200