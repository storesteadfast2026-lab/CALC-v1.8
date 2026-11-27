document.querySelectorAll('[data-api-console]').forEach((form) => {
    const button = form.querySelector('button[type="submit"]');
    const status = form.querySelector('[data-status]');
    const output = form.querySelector('[data-response]');

    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        if (button.disabled) return;

        const options = {
            method: form.method.toUpperCase(),
            credentials: 'same-origin',
            headers: { Accept: 'application/json' },
        };

        if (options.method === 'POST') {
            const payload = form.elements.payload.value;
            try {
                JSON.parse(payload);
            } catch {
                status.textContent = 'Invalid JSON';
                status.dataset.state = 'error';
                output.textContent = 'Check the JSON syntax and try again.';
                return;
            }
            options.body = payload;
            options.headers['Content-Type'] = 'application/json';
            options.headers['X-CSRFToken'] = form.elements.csrfmiddlewaretoken.value;
        }

        button.disabled = true;
        status.textContent = 'Sending…';
        status.dataset.state = 'pending';
        output.textContent = '';
        try {
            const response = await fetch(form.action, options);
            const contentType = response.headers.get('content-type') || '';
            output.textContent = contentType.includes('application/json')
                ? JSON.stringify(await response.json(), null, 2)
                : 'The server did not return JSON.';
            status.textContent = `HTTP ${response.status}`;
            status.dataset.state = response.ok ? 'success' : 'error';
        } catch {
            status.textContent = 'Could not read the response';
            status.dataset.state = 'error';
            output.textContent = 'Try sending the request again.';
        } finally {
            button.disabled = false;
        }
    });
});
