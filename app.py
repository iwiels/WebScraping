import os
import logging
import json
import time
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
from concurrent.futures import ThreadPoolExecutor, as_completed

# Eliminar la importación de tqdm que no se usa

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

# Configurar el número máximo de workers
MAX_WORKERS = 3  # Reducir el número de workers
TIMEOUT = 300  # 5 minutos de timeout

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(app.static_folder, path)

@app.route('/')
def index():
    index_path = os.path.join(STATIC_FOLDER, 'index.html')
    if os.path.exists(index_path):
        return send_from_directory(STATIC_FOLDER, 'index.html')
    return "No index.html file found in the static folder."

@app.route('/buscar', methods=['GET'])
def buscar():
    producto = request.args.get('producto')
    
    if not producto:
        return jsonify({'error': 'No se ingresó un producto'}), 400

    def generate():
        resultados = []
        tiendas = [
            ('ripley', buscar_en_ripley),
            ('falabella', buscar_en_falabella),
            ('oechsle', buscar_en_oechsle)
        ]

        completed = 0
        futures = {}
        start_times = {}

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            for tienda, funcion in tiendas:
                future = executor.submit(funcion, producto)
                futures[future] = tienda
                start_times[tienda] = time.time()

            for future in as_completed(futures):
                tienda = futures[future]
                completed += 1
                tiempo_busqueda = round(time.time() - start_times[tienda], 2)
                
                try:
                    resultados_tienda = future.result()
                    status = "✓" if resultados_tienda else "Sin resultados"
                    num_resultados = len(resultados_tienda) if resultados_tienda else 0
                    if resultados_tienda:
                        resultados.extend(resultados_tienda)

                    # Modificar el formato del JSON para evitar problemas de parsing
                    progress = {
                        'type': 'progress',
                        'store': tienda.title(),
                        'completed': completed,
                        'total': len(tiendas),
                        'tiempo': tiempo_busqueda,
                        'status': status,
                        'resultados': num_resultados
                    }
                    yield json.dumps(progress, ensure_ascii=False).strip() + '\n'

                except Exception as e:
                    logging.error(f"Error en {tienda}: {e}")
                    yield json.dumps({
                        'type': 'progress',
                        'store': tienda.title(),
                        'completed': completed,
                        'total': len(tiendas),
                        'tiempo': tiempo_busqueda,
                        'status': 'Error',
                        'resultados': 0
                    }, ensure_ascii=False).strip() + '\n'

        # Enviar resultados finales
        final_results = {
            'type': 'results',
            'results': sorted(resultados, key=lambda x: x['precio'])
        }
        yield json.dumps(final_results, ensure_ascii=False).strip() + '\n'

    return Response(generate(), mimetype='application/json')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, timeout=TIMEOUT)