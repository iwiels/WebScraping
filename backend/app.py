import os
import logging
import json
import time
import asyncio
import threading
from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS
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

from .notifications import enviar_notificacion_async, validar_numero_telefono
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