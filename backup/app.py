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
from backup.descuentos.backend.scrapping.metro import buscar_en_metro;
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

# Configurar logging
logging.getLogger().setLevel(logging.ERROR)
logging.getLogger('selenium').setLevel(logging.ERROR)
logging.getLogger('urllib3').setLevel(logging.ERROR)
logging.getLogger('WDM').setLevel(logging.ERROR)
os.environ['WDM_LOG_LEVEL'] = '0'

app = Flask(__name__, 
            static_folder='../frontend',
            static_url_path='')
CORS(app)

# Configurar el número máximo de workers
MAX_WORKERS = 9  # Ajusta este número según los cores de tu CPU

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(app.static_folder, path)

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

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
            ('oechsle', buscar_en_oechsle),
            ('estilos', buscar_en_estilos),
            ('tailoy', buscar_en_tailoy),
            ('realplaza', buscar_en_realplaza),
            ('plazavea', buscar_en_plazavea),
            ('hiraoka', buscar_en_hiraoka),
            ('metro', buscar_en_metro)
        ]

        completed = 0
        futures = {}
        start_times = {}

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Iniciar todas las búsquedas en paralelo y guardar tiempo inicial
            for tienda, funcion in tiendas:
                future = executor.submit(funcion, producto)
                futures[future] = tienda
                start_times[tienda] = time.time()

            # Monitorear la finalización de cada búsqueda
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
                except Exception as e:
                    logging.error(f"Error en {tienda}: {e}")
                    status = "Error"
                    num_resultados = 0

                # Enviar actualización de progreso
                yield json.dumps({
                    'type': 'progress',
                    'store': tienda.title(),
                    'completed': completed,
                    'total': len(tiendas),
                    'tiempo': tiempo_busqueda,
                    'status': status,
                    'resultados': num_resultados
                }) + '\n'

        # Enviar resultados finales ordenados
        yield json.dumps({
            'type': 'results',
            'results': sorted(resultados, key=lambda x: x['precio'])
        }) + '\n'

    return Response(generate(), mimetype='application/json')

if __name__ == '__main__':
    app.run(debug=False)