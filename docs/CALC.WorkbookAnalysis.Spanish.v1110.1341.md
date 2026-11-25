# CALC — Análisis de la planilla inicial

**Tipo de documento:** Análisis interno de workbook  
**Estado:** Inspección estructural y de fórmulas; no certifica resultados de cálculo  
**Versión:** v1110.1341  
**Fecha:** 10 de noviembre de 2026 (Australia/Adelaide)  
**Archivo analizado:** V2026.R2_Unlocked_STH_Freight_Calculator1(2).xlsx  
**SHA-256:** a21a0aae0eaa2d15ab1965394df99c5f6c7444c7d55728d8e39d4b39f79c74ae  
**Tamaño:** 13.381.702 bytes

## 1. Alcance y límites

Este documento analiza únicamente la planilla Excel indicada arriba: su organización, campos, fórmulas, referencias y dependencias. No es un análisis de operación de Rate Cards ni una aprobación de reglas comerciales.

La inspección se hizo sobre la estructura y las fórmulas del archivo. No se recalculó en Excel, no se ejecutó una cotización interactiva y no se comprobó el contenido actual de los archivos externos. Por lo tanto, las fórmulas permiten describir el diseño y el flujo, pero no certifican que los importes almacenados o visibles sean actuales ni correctos.

Las dimensiones de las hojas incluyen rangos auxiliares, fórmulas y celdas preparadas. No equivalen necesariamente a cantidades de registros comerciales.

## 2. Hallazgos ejecutivos

1. La planilla separa una pantalla de entrada, cálculos intermedios, tarifas, zonas, productos, combustible y hojas auxiliares.
2. La hoja Calculator tiene un origen fijo en la celda C4: Steadfast Australia, Woodville North, SA 5012. En este workbook el origen no aparece como una selección dinámica.
3. La hoja muestra destinos por suburbio, estado y postcode; líneas de envío; selección de producto o carga manual; cantidad; dimensiones; peso; tipo Pallet/Case; tailgate y modo de preselección de SKU.
4. BrokerTotals reúne por transportista/servicio componentes como básico, mínimo, tarifa, siguiente básico, conversión cúbica, sobrepeso, exceso de largo, combustible, cargos adicionales, tailgate y hand unload.
5. La lista de resultados se ordena por importe mediante fórmulas de mínimo sucesivo. La pantalla indica que son estimaciones de flete sin GST y que las tarifas son una guía.
6. El workbook tiene aproximadamente 378.289 celdas con fórmulas. Las hojas ZONES y SUBURBS concentran la mayor parte. Reproducir esta arquitectura de fórmulas en Django aumentaría el acoplamiento y dificultaría mantenimiento y diagnóstico.
7. La planilla contiene vínculos externos a archivos de productos y stock, además de una consulta web de combustible. Su funcionamiento depende de fuentes y actualizaciones que no están contenidas íntegramente en el archivo.
8. Cinco nombres definidos contienen #REF!. Esto confirma referencias rotas en el workbook, pero no demuestra por sí solo que una cotización activa esté equivocada. No se confirmó si esos nombres se usan en fórmulas o validaciones.
9. El workbook solicita recálculo completo al abrir. En este análisis no se recalcularon las fórmulas, por lo que los valores en caché no son evidencia suficiente de un resultado vigente.

## 3. Inventario de hojas

La siguiente tabla registra dimensiones y cantidad de fórmulas observadas. Las dimensiones son rangos usados/preparados, no recuentos de filas de negocio.

| Hoja | Función observada | Dimensiones | Fórmulas |
|---|---|---:|---:|
| Calculator | Entrada del envío y presentación de resultados | 39 × 25 | 207 |
| SettingFlags | Configuración, controles y valores auxiliares | 81 × 51 | 131 |
| FuelSurcharge | Configuración de transportistas/servicios y recargos | 135 × 52 | 234 |
| fuel | Tabla de combustible por tarjeta maestra | 38 × 6 | 0 |
| CalcLines | Cálculos por línea, totales y verificaciones | 41 × 24 | 229 |
| BrokerTotals | Componentes de tarifa y totales por transportista/servicio | 137 × 90 | 2.378 |
| SKUs | Productos, medidas y datos auxiliares de SKU | 233 × 36 | 2.399 |
| SKU-Kits | Soporte para kits o productos agrupados | 108 × 20 | 401 |
| ProductsImported | Datos de productos importados y columnas derivadas | 500 × 16 | 7.498 |
| StockImported | Datos de stock importados y columnas derivadas | 500 × 20 | 10.000 |
| Product Table | Tabla de referencia de productos | 251 × 6 | 0 |
| SUBURBS | Ubicaciones y claves de búsqueda auxiliares | 43.436 × 26 | 130.302 |
| ZONES | Relación de transportista/servicio/ubicación con zona | 109.481 × 12 | 218.958 |
| RATES | Tarifas aplanadas y claves de búsqueda | 5.552 × 20 | 5.550 |
| ZonePaster | Hoja auxiliar para preparar zonas | 21.057 × 10 | 2 |
| RatesPaster | Hoja auxiliar para preparar tarifas | 118 × 19 | 0 |

## 4. Mapa funcional observado

### 4.1 Calculator

La hoja Calculator contiene:

- origen fijo en C4;
- destino con suburbio, estado y postcode;
- aviso de estado/postcode y sugerencias cuando no encuentra la ubicación;
- selección de carga manual o de SKU preseleccionado;
- campos de cantidad, tipo de carga, largo, ancho, alto y peso;
- indicador de tailgate;
- totales de peso y cubicaje;
- mensajes de validación;
- opciones de transportista, servicio y estimación ex GST.

En el archivo revisado, el listado de resultados usa fórmulas SMALL para ir seleccionando importes crecientes. La fórmula de la fila 24 solicita el puesto 20. La presentación y la capacidad real de la hoja deben comprobarse en Excel antes de fijarlas como límite funcional de la nueva aplicación.

La celda J2 consulta un CSV mediante WEBSERVICE en https://www.poscat.com.au/fuelsc/fuel.csv y muestra un mensaje si no logra acceder. La fórmula existe en el archivo; no se probó la disponibilidad actual del sitio ni el resultado de esa llamada.

### 4.2 CalcLines y BrokerTotals

CalcLines consolida líneas y prepara controles de validez. Sus encabezados incluyen cantidad, tailgate, dimensiones, peso, tipo Pallet/Carton, pallet, carton, peso total, cubicaje total y número de líneas.

La fila de totales suma cantidades, pesos y cubicajes de las líneas visibles. También contiene lógica relacionada con el modo de preselección y con las cantidades de pallets/cajas. Las fórmulas muestran que hay condiciones especiales; su significado completo debe leerse junto con los datos y referencias que alimentan cada celda.

BrokerTotals contiene, por transportista y servicio, columnas con:

- básico;
- mínimo;
- tarifa;
- básico por unidad adicional;
- total;
- conversión cúbica;
- sobrepeso;
- exceso de largo;
- combustible;
- recargos adicionales;
- tailgate;
- hand unload;
- manipulación.

Las fórmulas de la hoja consultan RATES y la configuración de FuelSurcharge. La hoja actúa como etapa de cálculo y agregación previa a mostrar las alternativas en Calculator.

### 4.3 SKU y productos

SKUs contiene código, largo/ancho/alto en centímetros y metros, peso, cubicaje y tipo. También incluye columnas de errores para medidas y comparaciones auxiliares de producto/stock.

ProductsImported y StockImported son hojas separadas y usan vínculos a archivos externos. En SKUs se observan fórmulas que consultan rangos de producto importado y stock para obtener datos relacionados con cubicaje y peso. Por ello, no se debe asumir que los datos de producto y stock tienen el mismo origen, fecha de actualización o función.

SKU-Kits y Product Table son hojas independientes. Su propósito operativo exacto y sus reglas de prioridad no quedan completamente determinados solo por el nombre y la estructura; deben verificarse en fórmulas, rangos nombrados y escenarios del workbook.

### 4.4 Zonas y tarifas

ZONES presenta campos explícitos para transportista, servicio, suburbio, estado, postcode, zone, subzone y area. Incluye claves concatenadas para buscar una zona por ubicación y por zona del transportista.

RATES presenta carrier, service, zone, subzone, area, weight break, other break, minimum charge, basic, per subsequent basic, per kg y columnas adicionales para cargos. La primera columna de búsqueda concatena componentes de la tarifa.

La representación de RATES es una tabla aplanada para búsquedas del workbook. No demuestra que ese sea el formato fuente original del sistema operacional ni que incluya por sí sola toda la lógica de selección, referencias y condiciones.

### 4.5 Combustible y configuración

La hoja fuel tiene campos master_rate, info, rate, updated, expires y warnings.

FuelSurcharge contiene orden, carrier, ratecard, service, fuel levy, extra surcharges, uprate, tailgate, warehouse handling, cubic conversion, controles de preparación y banderas de pallet/carton, hand unload, subzone, area y overlength. Esto muestra que la configuración del workbook puede variar por transportista y servicio.

Los valores que aparecen en las filas son contenido del workbook analizado. No deben copiarse como valores actuales sin confirmar vigencia, origen y activación.

## 5. Dependencias externas y anomalías

### 5.1 Archivos externos de productos y stock

El workbook tiene vínculos a:

- T:\Steadfast\Excel Files\STH_FGT_CALC\product_sth.xlsx
- T:\Steadfast\Excel Files\STH_FGT_CALC\stock_sth.xlsx

ProductsImported y StockImported contienen fórmulas que referencian esos archivos. La ruta puede no existir en otro equipo o entorno. La importación web debe definir explícitamente cómo se carga, valida, concilia y activa cada fuente, sin depender de que la unidad T: esté conectada.

Los rangos de esas hojas llegan hasta la fila 500 en el workbook. Esto confirma el rango preparado en el archivo, no el tamaño real de los archivos fuente ni que exista un límite comercial de 500 registros.

### 5.2 Nombres definidos con referencias rotas

Se observaron cinco nombres definidos con #REF!:

- LOOKIPP
- NEW
- NEWEER
- TOLLEXRATES
- VLWEIGH

Es una anomalía estructural confirmada. Antes de reconstruir una función relacionada, comprobar si cada nombre aparece en fórmulas, validaciones, formato condicional u otras referencias. No reparar ni eliminar estos nombres a ciegas.

### 5.3 Recalculo y resultados en caché

El workbook tiene habilitado el recálculo completo al abrir. Además, depende de una consulta web para combustible y de libros externos para productos y stock. Los valores almacenados pueden no representar el estado actual si esas dependencias no están disponibles o Excel no recalcula.

La inspección de fórmulas no equivale a ejecutar Microsoft Excel. No se certificaron los importes visibles ni la operación interactiva.

## 6. Observaciones para reconstruir CALC

1. **Separar interfaz y motor:** conservar una interfaz simple para entrada y resultados; modelar zonas, tarifas y recargos en servicios y datos del backend.
2. **Evitar fórmulas de hoja como arquitectura:** migrar el comportamiento necesario, no cientos de miles de fórmulas ni dependencias implícitas de rangos nombrados.
3. **Definir fuentes:** productos, stock, zonas, tarifas y combustible necesitan contratos, versión, fecha y proceso propio de validación.
4. **Conservar trazabilidad:** cada opción debe poder explicar qué destino/zona resolvió, qué filas de datos consultó y qué componentes entraron al total.
5. **Separar datos de reglas:** una tabla de tarifas aplanada puede ser útil para comparar, pero no debe ocultar condiciones o referencias que la hoja original representa en otros lugares.
6. **No trasladar fallos de Excel:** las fórmulas con errores o nombres rotos se deben investigar; no convertir automáticamente su resultado en una regla nueva.
7. **Tratar los importes como datos versionados:** el workbook ofrece valores de una versión concreta. No son constantes permanentes ni prueba del precio vigente.
8. **Mantener las funciones de selección visibles:** suburbio, estado y postcode deben permanecer coherentes; los errores de entrada deben explicarse donde ocurren.

## 7. Aspectos que faltan para certificar el comportamiento

Para convertir este análisis estructural en una especificación de cálculo completa, todavía se necesita:

- recalcular una copia del workbook en Excel y comparar fórmulas con resultados;
- inspeccionar validaciones de datos, listas desplegables, formatos condicionales y rangos nombrados;
- revisar fórmulas completas de CalcLines y BrokerTotals por cada transportista/servicio activo;
- identificar qué nombres definidos con #REF! siguen referenciados y qué impacto tienen;
- confirmar las versiones y el contenido real de product_sth.xlsx, stock_sth.xlsx y la fuente de combustible;
- ejecutar casos de prueba repetibles con la misma entrada y los mismos datos de referencia;
- separar diferencias por datos cambiados de diferencias por lógica.

Hasta ejecutar esas comprobaciones, el estado correcto es **estructura inspeccionada; cálculo funcional no certificado**.

## 8. Política de uso de este análisis

Esta planilla es una referencia funcional histórica del calculador STH. Puede utilizarse para entender la pantalla, localizar pasos de cálculo y preparar comparaciones controladas. Conforme a la política CALC vigente, no debe permanecer como fuente productiva de tarifas/zonas, fallback silencioso ni fuente de constantes tarifarias copiadas.

Las comparaciones deben fijar la versión del workbook, datos de entrada, fuentes de zona/tarifa/combustible y resultado esperado. Un importe antiguo distinto no es por sí solo un defecto si los valores comerciales cambiaron.

## 9. Registro de cambios

- **v1110.1341 — 10 de noviembre de 2026:** análisis independiente del workbook STH. No incorpora reglas de conversaciones operativas, no activa datos y no certifica las fórmulas.
