# Grafo de tarifas de Freight

El proyecto lee la carpeta hermana `Freight-Tarifas`. El grafo, el índice de pasajes y las herramientas de consulta se ejecutan localmente. La extracción y las consultas no requieren una cuenta ni una clave de IA.

## Consultar

En Codex, desde el proyecto, pregunta en lenguaje natural. Por ejemplo:

- «¿Qué tarifas especiales o excepciones están documentadas para Kangaroo Island? Cita la fuente y la página».
- «Busca la exención de manejo manual para las cuentas 5005I2 y FD6805. ¿A qué cuenta se refiere cada correo?».
- «Busca el recargo de combustible para septiembre de 2026. Indica el proveedor, el servicio y la fuente de cada cifra».

Desde la consola, en esta carpeta:

```powershell
$freightPython = uv python find 3.14
& $freightPython -X utf8 consultar.py explorar 'Kangaroo Island'
& $freightPython -X utf8 consultar.py buscar 'Kangaroo Island' --limite 8
& $freightPython -X utf8 consultar.py buscar 'exencion 5005I2 FD6805'
& $freightPython -X utf8 consultar.py documento ID_DEVUELTO_POR_LA_CONSULTA --inicio 0
& $freightPython -X utf8 consultar.py cobertura
graphify explain 'Kangaroo Island' --graph graphify-out/graph.json
```

`explorar` recorre las relaciones del grafo. `buscar` encuentra pasajes en los archivos y admite un filtro por ruta con `--archivo`. `documento` amplía el contexto y recupera la fuente canónica para los duplicados. `cobertura` indica qué archivos requieren revisión del original.

Abre `graphify-out/graph.html` para ver las conexiones y `cobertura.json` para comprobar el estado de un archivo. La vista HTML usa una biblioteca JavaScript que el navegador carga desde un CDN. Las consultas por consola y MCP funcionan sin esa vista. Los enlaces `menciona` indican dónde aparece un tema, lugar o cuenta. Comprueba la fecha, el servicio y la cuenta en la fuente antes de afirmar la vigencia, una exención o el importe. Los pasajes marcados como OCR requieren cotejo visual. Las hojas se leen con los valores guardados, sin recalcular sus fórmulas.

## Claude y otros clientes MCP

`.mcp.json` contiene la configuración para este equipo. Claude Code puede usarla al abrir esta carpeta como proyecto. En Claude Desktop abre **Settings → Developer → Edit Config**, agrega la entrada `freight_tarifas` al objeto `mcpServers` de tu configuración y reinicia Claude. Conserva las entradas de otros servidores. En otro cliente MCP usa el mismo comando y argumentos con transporte stdio.

El servidor entrega al cliente los pasajes solicitados. Si usas un servicio de IA alojado, el proveedor puede recibir esos pasajes como parte de la consulta. El corpus y el índice siguen como archivos locales.

## Reconstruir

Después de cambiar el contenido de `Freight-Tarifas`, ejecuta estas instrucciones desde esta carpeta. La primera línea instala las dependencias locales si todavía no están disponibles.

```powershell
uv pip install --python 3.14 --target .deps -r requirements.txt
$freightPython = uv python find 3.14
& $freightPython -X utf8 construir.py
graphify cluster-only . --no-label
```

Se conservan las rutas, las páginas u hojas cuando están disponibles y los vínculos entre copias idénticas. Consulta `cobertura.json` para los formatos sin lector, errores y extracciones parciales. Las imágenes incrustadas en correos quedan listadas como adjuntos y requieren inspección del original.
