import os
import logging
import json
import time
import asyncio
import threading
from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS
from backup.descuentos.backend.scrapping.ripley import buscar_en_ripley
from backup.descuentos.backend.scrapping.falabella import buscar_en_falabella
from backup.descuentos.backend.scrapping.oechsle import buscar_en_oechsle
from backup.descuentos.backend.scrapping.estilos import buscar_en_estilos   
from backup.descuentos.backend.scrapping.tailoy import buscar_en_tailoy
from backup.descuentos.backend.scrapping.realplaza import buscar_en_realplaza
from backup.descuentos.backend.scrapping.plazavea import buscar_en_plazavea
from backup.descuentos.backend.scrapping.hiraoka import buscar_en_hiraoka
from backup.descuentos.backend.scrapping.metro import buscar_en_metro
from backup.descuentos.backend.notifications import enviar_notificacion_async, validar_numero_telefono
from backup.descuentos.backend.scrapping.ripley_playwright import buscar_en_ripley_async_wrapper
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configurar logging
logging.getLogger().setLevel(logging.ERROR)
logging.getLogger('selenium').setLevel(logging.ERROR)
logging.getLogger('urllib3').setLevel(logging.ERROR)
logging.getLogger('WDM').setLevel(logging.ERROR)
os.environ['WDM_LOG_LEVEL'] = '0'

app = Flask(__name__, 
            static_folder='backup/descuentos/frontend',
            static_url_path='')
CORS(app)

# Asegurarse de que las rutas sean absolutas
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_FOLDER = os.path.join(BASE_DIR, 'backup/descuentos/frontend')

# Configuración de recursos y timeouts
MAX_WORKERS = 2  # Reducir workers
TIMEOUT = 600  # Aumentar timeout a 10 minutos
MAX_TIENDAS = 3  # Limitar número de tiendas simultáneas

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(app.static_folder, path)

@app.route('/')
def index():
    index_path = os.path.join(STATIC_FOLDER, 'index.html')
    if os.path.exists(index_path):
        return send_from_directory(STATIC_FOLDER, 'index.html')
    return "No index.html file found in the static folder."

# Función para ejecutar scrapers asíncronos en el ThreadPoolExecutor
def run_async_scraper(scraper_func, product):
    """Ejecuta un scraper asíncrono en un contexto síncrono."""
    return asyncio.run(scraper_func(product))

@app.route('/buscar', methods=['GET'])
def buscar():
    producto = request.args.get('producto')
    telefono = request.args.get('telefono', '').strip()
    notificar = request.args.get('notificarWsp', '').lower() == 'true'
    
    if not producto:
        return jsonify({'error': 'No se ingresó un producto'}), 400

    # Validar teléfono si se solicita notificación
    if notificar and telefono:
        es_valido, telefono_limpio, error = validar_numero_telefono(telefono)
        if not es_valido:
            return jsonify({'error': f'Número de teléfono inválido: {error}'}), 400
        telefono = telefono_limpio

    def generate():
        resultados = []
        
        # Configurar tiendas con opción de usar Playwright
        tiendas = [
            ('ripley_playwright', buscar_en_ripley_async_wrapper),  # Usar Playwright para Ripley
            ('falabella', buscar_en_falabella),
            ('oechsle', buscar_en_oechsle)
        ]

        completed = 0
        futures = {}
        start_times = {}

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            for tienda, funcion in tiendas:
                if tienda == 'ripley_playwright':
                    # Para scrapers asíncronos, usar el wrapper
                    future = executor.submit(run_async_scraper, buscar_en_ripley_async_wrapper, producto)
                else:
                    future = executor.submit(funcion, producto)
                    
                futures[future] = tienda.replace('_playwright', '')  # Mostrar nombre limpio
                start_times[tienda] = time.time()

            for future in as_completed(futures):
                tienda_display = futures[future]
                completed += 1
                tiempo_busqueda = round(time.time() - start_times.get(tienda_display, time.time()), 2)
                
                try:
                    resultados_tienda = future.result()
                    status = "✓" if resultados_tienda else "Sin resultados"
                    num_resultados = len(resultados_tienda) if resultados_tienda else 0
                    if resultados_tienda:
                        resultados.extend(resultados_tienda)

                    progress = {
                        'type': 'progress',
                        'store': tienda_display.title(),
                        'completed': completed,
                        'total': len(tiendas),
                        'tiempo': tiempo_busqueda,
                        'status': status,
                        'resultados': num_resultados
                    }
                    yield json.dumps(progress, ensure_ascii=False).strip() + '\n'

                except Exception as e:
                    logging.error(f"Error en {tienda_display}: {e}")
                    yield json.dumps({
                        'type': 'progress',
                        'store': tienda_display.title(),
                        'completed': completed,
                        'total': len(tiendas),
                        'tiempo': tiempo_busqueda,
                        'status': 'Error',
                        'resultados': 0
                    }, ensure_ascii=False).strip() + '\n'

        # Ordenar resultados finales
        final_results_list = sorted(resultados, key=lambda x: x['precio'])
        
        # Enviar notificación si se solicitó
        if notificar and telefono and final_results_list:
            try:
                enviar_notificacion_async(telefono, producto, final_results_list)
                logging.info(f"Notificación WhatsApp programada para {telefono}")
            except Exception as e:
                logging.error(f"Error programando notificación WhatsApp: {e}")

        # Enviar resultados finales
        final_results = {
            'type': 'results',
            'results': final_results_list,
            'notificacion_enviada': notificar and telefono and bool(final_results_list)
        }
        yield json.dumps(final_results, ensure_ascii=False).strip() + '\n'

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