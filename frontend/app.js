$(document).ready(function() {
    let searchRequest = null;
    const loadingText = $('#loadingText'); // This is no longer directly used with a modal
    let resultadosGlobales = []; // Para almacenar todos los resultados
    let elementosPorPagina = 16; // Número de resultados por página
    let paginaActual = 1;

    $('#searchForm').submit(async (e) => {
        e.preventDefault();
        buscarProductos();
    });

    $('#filtroTienda, #ordenarPor, #minPrice, #maxPrice').change(() => {
        paginaActual = 1; // Resetear a la primera página al cambiar los filtros
        mostrarResultadosPaginados();
    });

    async function buscarProductos() {
        const producto = $('#producto').val();
        const ordenarPor = $('#ordenarPor').val();

        $('#resultados').empty();
        $('#pagination').empty();
        resultadosGlobales = [];
        paginaActual = 1;

        // Reset and show progress bar
        $('#searchProgress').show();
        $('#searchProgressBar').css('width', '0%').text('0%');
        $('#currentStore').text('Iniciando búsqueda...');
        $('#progressText').text(`Buscando productos: 0/9 tiendas`);

        if (searchRequest) {
            searchRequest.abort();
        }

        // Show loading state directly on the button
        const submitButton = $('#searchForm button[type="submit"]');
        submitButton.prop('disabled', true);
        submitButton.html('<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Buscando...');

        const controller = new AbortController();
        const signal = controller.signal;
        searchRequest = { controller, producto };

        try {
            const response = await fetch(`/buscar?producto=${encodeURIComponent(producto)}&ordenarPor=${encodeURIComponent(ordenarPor)}`, { signal });
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                
                const chunk = decoder.decode(value);
                try {
                    const data = JSON.parse(chunk);
                    if (data.type === 'progress') {
                        const progress = (data.completed / data.total) * 100;
                        $('#searchProgressBar').css('width', `${progress}%`).text(`${Math.round(progress)}%`);
                        $('#currentStore').text(`${data.store}: ${data.status} (${data.resultados} resultados) - ${data.tiempo}s`);
                        $('#progressText').text(`Buscando productos: ${data.completed}/${data.total} tiendas`);
                        
                        // Actualizar el estado de la tienda individual
                        const statusEl = document.getElementById(`status-${data.store.toLowerCase()}`);
                        if (statusEl) {
                            let statusText = `${data.store}: `;
                            if (data.status === "✓") {
                                statusText += `<span style="color:green;">${data.status}</span> `;
                            } else {
                                statusText += `<span style="color:red;">${data.status}</span> `;
                            }
                            statusText += `(${data.resultados} resultados - ${data.tiempo}s)`;
                            statusEl.innerHTML = statusText;
                        }
                    } else if (data.type === 'results') {
                        resultadosGlobales = data.results;
                        mostrarResultadosPaginados();
                    }
                } catch (e) {
                    console.error('Error parsing chunk:', e);
                }
            }
        } catch (error) {
            if (error.name === 'AbortError') {
                $('#resultados').html('<div class="col-12 text-center"><p>Búsqueda cancelada.</p></div>');
            } else {
                $('#resultados').html('<div class="col-12 text-center"><div class="alert alert-danger" role="alert">Error al buscar los productos.</div></div>');
                console.error(error);
            }
        } finally {
            submitButton.prop('disabled', false);
            submitButton.html('<i class="bi bi-search"></i> Buscar');
            $('#searchProgress').hide();
            searchRequest = null;
        }
    }

    function mostrarResultadosPaginados() {
        const resultadosFiltradosOrdenados = filtrarYOrdenarResultados(resultadosGlobales);
        const indiceInicio = (paginaActual - 1) * elementosPorPagina;
        const indiceFin = indiceInicio + elementosPorPagina;
        const resultadosPagina = resultadosFiltradosOrdenados.slice(indiceInicio, indiceFin);

        mostrarResultados(resultadosPagina);
        actualizarPaginacion(resultadosFiltradosOrdenados.length);
    }

    function filtrarYOrdenarResultados(resultados) {
        if (!Array.isArray(resultados)) {
            console.error('resultados no es un array:', resultados);
            return [];
        }

        const filtroTienda = $('#filtroTienda').val();
        const ordenarPor = $('#ordenarPor').val();
        const minPrice = parseFloat($('#minPrice').val()) || 0;
        const maxPrice = parseFloat($('#maxPrice').val()) || Infinity;

        let resultadosFiltrados = [...resultados];  // Create a copy of the array

        if (filtroTienda) {
            resultadosFiltrados = resultadosFiltrados.filter(r => r.tienda === filtroTienda);
        }

        resultadosFiltrados = resultadosFiltrados.filter(r => r.precio >= minPrice && r.precio <= maxPrice);

        if (ordenarPor === 'precioAsc') {
            resultadosFiltrados.sort((a, b) => a.precio - b.precio);
        } else if (ordenarPor === 'precioDesc') {
            resultadosFiltrados.sort((a, b) => b.precio - a.precio);
        } else if (ordenarPor === 'descuentoDesc') {
            resultadosFiltrados.sort((a, b) => (b.descuento || -1) - (a.descuento || -1));
        } else if (ordenarPor === 'recomendados') {
            resultadosFiltrados.sort((a, b) => {
                let puntajeA = (a.descuento || 0) * 5;
                const palabrasClaveA = $('#producto').val().toLowerCase().split(' '); // Split by space
                const nombreProductoA = a.nombre.toLowerCase();
                const coincidenciasA = palabrasClaveA.filter(palabra => nombreProductoA.includes(palabra)).length;
                puntajeA += coincidenciasA * 2;
                puntajeA -= (a.precio / 100);

                let puntajeB = (b.descuento || 0) * 5;
                const palabrasClaveB = $('#producto').val().toLowerCase().split(' '); // Split by space
                const nombreProductoB = b.nombre.toLowerCase();
                const coincidenciasB = palabrasClaveB.filter(palabra => nombreProductoB.includes(palabra)).length;
                puntajeB += coincidenciasB * 2;
                puntajeB -= (b.precio / 100);

                return puntajeB - puntajeA;
            });
        }

        return resultadosFiltrados;
    }

    function mostrarResultados(resultados) {
        $('#resultados').empty();
        const fragment = $(document.createDocumentFragment());
        resultados.forEach(r => {
            // Handle image URL and discount
            // Usamos un div vacío con fondo gris si no hay imagen
            let imagenHtml = r.imagen ? `<img src="${r.imagen}" class="card-img-top" alt="${r.nombre}">` : `<div class="card-img-top" style="background-color: #eee; height: 200px;"></div>`;
            let descuentoHtml = r.descuento !== null && r.descuento !== undefined ? `<span class="badge badge-success">-${r.descuento}%</span>` : '';

            const card = $(`
                <div class="col-md-4 mb-4 animated fadeInUp">
                    <div class="card h-100 shadow-sm">
                        ${imagenHtml}
                        <div class="card-body">
                            <h5 class="card-title">${r.nombre} ${descuentoHtml}</h5>
                            <p class="current-price">S/ ${r.precio.toFixed(2)}</p>
                            <p class="store-name"><i class="bi bi-shop"></i> ${r.tienda}</p>
                            <a href="${r.link}" target="_blank" class="btn btn-primary w-100 mt-3"><i class="bi bi-eye"></i> Ver en tienda</a>
                        </div>
                    </div>
                </div>
            `);
            fragment.append(card);
        });
        $('#resultados').append(fragment);
    }

    function actualizarPaginacion(totalResultados) {
        const numeroDePaginas = Math.ceil(totalResultados / elementosPorPagina);
        $('#pagination').empty();

        // Botón anterior
        const prevButton = $(`
            <li class="page-item ${paginaActual === 1 ? 'disabled' : ''}">
                <a class="page-link" href="#" data-page="${paginaActual - 1}" aria-label="Previous">
                    <span aria-hidden="true">«</span>
                    <span class="sr-only">Anterior</span>
                </a>
            </li>
        `);
        $('#pagination').append(prevButton);

        // Números de página
        let startPage = Math.max(1, paginaActual - 2);
        let endPage = Math.min(numeroDePaginas, paginaActual + 2);

        if (startPage > 1) {
            $('#pagination').append(`<li class="page-item"><a class="page-link" href="#" data-page="1">1</a></li>`);
            if (startPage > 2) {
                $('#pagination').append('<li class="page-item disabled"><span class="page-link">...</span></li>');
            }
        }

        for (let i = startPage; i <= endPage; i++) {
            const paginaActiva = i === paginaActual ? 'active' : '';
            const listItem = `<li class="page-item ${paginaActiva}"><a class="page-link" href="#" data-page="${i}">${i}</a></li>`;
            $('#pagination').append(listItem);
        }

        if (endPage < numeroDePaginas) {
            if (endPage < numeroDePaginas - 1) {
                $('#pagination').append('<li class="page-item disabled"><span class="page-link">...</span></li>');
            }
            $('#pagination').append(`<li class="page-item"><a class="page-link" href="#" data-page="${numeroDePaginas}">${numeroDePaginas}</a></li>`);
        }

        // Botón siguiente
        const nextButton = $(`
            <li class="page-item ${paginaActual === numeroDePaginas ? 'disabled' : ''}">
                <a class="page-link" href="#" data-page="${paginaActual + 1}" aria-label="Next">
                    <span aria-hidden="true">»</span>
                    <span class="sr-only">Siguiente</span>
                </a>
            </li>
        `);
        $('#pagination').append(nextButton);
    }

    // Update the event listener for pagination
    $(document).on('click', '#pagination .page-link', function(e) {
        e.preventDefault();
        const nuevaPagina = parseInt($(this).data('page'));

        if (!isNaN(nuevaPagina) && nuevaPagina !== paginaActual) {
            paginaActual = nuevaPagina;
            mostrarResultadosPaginados();
            // Smooth scroll to results section
            $('html, body').animate({ scrollTop: $('#resultados-section').offset().top - 100 }, 300);
        }
    });

    function actualizarEstadoTiendas(resultados) {
        if (!Array.isArray(resultados)) {
            console.error('resultados no es un array:', resultados);
            return;
        }

        const tiendas = [
            { id: 'ripley', nombre: 'Ripley' },
            { id: 'falabella', nombre: 'Falabella' },
            { id: 'oechsle', nombre: 'Oechsle' },
            { id: 'estilos', nombre: 'Estilos' },
            { id: 'tailoy', nombre: 'Tailoy' },
            { id: 'realplaza', nombre: 'Real Plaza' },
            { id: 'plazavea', nombre: 'Plaza Vea' },
            { id: 'hiraoka', nombre: 'Hiraoka' },
            { id: 'metro', nombre: 'Metro' }
        ];

        tiendas.forEach(({ id, nombre }) => {
            const statusEl = document.getElementById(`status-${id}`);
            if (!statusEl) return;
            const tieneResultados = Array.isArray(resultados) ? resultados.some(r => r.tienda === id) : false;

            if (tieneResultados) {
                statusEl.innerHTML = `${nombre}: <span style="color:green;">✓</span>`;
            } else {
                statusEl.innerHTML = `${nombre}: <span style="color:red;">Sin resultados</span>`;
            }
        });
    }

    // Price Alert Subscription Logic
    $('#subNotificationChannel').change(function() {
        const selectedChannel = $(this).val();
        const $identifierLabel = $('#subUserIdentifierLabel');
        const $identifierInput = $('#subUserIdentifier');
        const $identifierHelp = $('#subUserIdentifierHelp');

        if (selectedChannel === 'whatsapp') {
            $identifierLabel.text('Número de Teléfono (WhatsApp)');
            $identifierInput.attr('placeholder', '+51987654321');
            $identifierHelp.text('Para WhatsApp, incluye el código de país (ej: +51). Para Telegram, ingresa tu Chat ID.');
        } else if (selectedChannel === 'telegram') {
            $identifierLabel.text('Telegram Chat ID');
            $identifierInput.attr('placeholder', 'Tu Chat ID de Telegram');
            $identifierHelp.text('Debes iniciar una conversación con el bot primero para obtener tu Chat ID.');
        }
    });

    $('#subscriptionForm').submit(async function(e) {
        e.preventDefault();
        const $submitButton = $(this).find('button[type="submit"]');
        const $statusDiv = $('#subscriptionStatus');

        const productName = $('#subProductName').val().trim();
        const notificationChannel = $('#subNotificationChannel').val();
        const userIdentifier = $('#subUserIdentifier').val().trim();
        const desiredDiscountPercentage = $('#subDiscountPercentage').val().trim();

        $statusDiv.html('').removeClass('alert alert-success alert-danger');

        // Basic client-side validation
        if (!productName || !userIdentifier || !desiredDiscountPercentage) {
            $statusDiv.html('Por favor, completa todos los campos.').addClass('alert alert-danger');
            return;
        }
        if (isNaN(parseFloat(desiredDiscountPercentage)) || parseFloat(desiredDiscountPercentage) <= 0 || parseFloat(desiredDiscountPercentage) >= 100) {
            $statusDiv.html('El porcentaje de descuento debe ser un número entre 1 y 99.').addClass('alert alert-danger');
            return;
        }

        $submitButton.prop('disabled', true).html('<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Suscribiendo...');

        try {
            const response = await fetch('/subscribe-price-alert', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    product_name: productName,
                    notification_channel: notificationChannel,
                    user_identifier: userIdentifier,
                    desired_discount_percentage: desiredDiscountPercentage,
                }),
            });

            const result = await response.json();

            if (response.ok) {
                $statusDiv.html(`<strong>¡Suscripción exitosa!</strong> ${result.message || ''} (Clave: ${result.subscription_key.join(', ')})`).addClass('alert alert-success');
                $('#subscriptionForm')[0].reset(); // Reset form
                 // Reset label and placeholder for user identifier if needed by triggering change
                $('#subNotificationChannel').trigger('change');
            } else {
                $statusDiv.html(`<strong>Error:</strong> ${result.error || 'No se pudo completar la suscripción.'}`).addClass('alert alert-danger');
            }
        } catch (error) {
            console.error('Subscription error:', error);
            $statusDiv.html('Error de conexión al intentar suscribirse. Inténtalo de nuevo.').addClass('alert alert-danger');
        } finally {
            $submitButton.prop('disabled', false).html('<i class="bi bi-check-circle-fill"></i> Suscribirse');
        }
    });
});