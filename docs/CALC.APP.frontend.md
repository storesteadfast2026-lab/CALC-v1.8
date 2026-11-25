# CALC — Plan base para reconstrucción y continuidad del proyecto

Actúa como analista de negocio senior, arquitecto de software y desarrollador senior. Ayúdame a preparar un plan verificable para continuar y, si se decide, reconstruir la Calculator App de Freight (CALC), manteniendo lo que ya funciona y corrigiendo las brechas identificadas.

## 1. Objetivo

El objetivo es construir una aplicación de cotización de fletes que conserve el flujo aprobado por los usuarios y calcule con datos operacionales actualizables, especialmente las Rate Cards de STH.

El objetivo principal no es igualar importes históricos. Los valores cambian. Se debe comprobar que cada nueva tarifa se aplique a la ruta, servicio, zona, peso/cubicaje y condiciones correctos, y que los casos no afectados permanezcan estables.

Antes de proponer código, migraciones o cambios de reglas:
- inspecciona el código y todos los archivos .md del snapshot actual;
- revisa la planilla original y los archivos de entrada disponibles;
- separa hechos verificados, inferencias y preguntas operativas;
- identifica el estado real del repositorio, distinguiendo snapshot, código aplicado y runtime;
- no asumas que una versión antigua representa la aplicación instalada actualmente.

## 2. Interfaz aprobada que se debe preservar

Mantén como baseline de producto, salvo que el análisis encuentre evidencia concreta de un defecto:

- acceso para usuarios internos de la empresa y usuarios externos de clientes;
- usuarios internos con acceso a las cotizaciones de los clientes que tienen autorizados;
- usuarios externos con acceso solo a sus propias cotizaciones;
- selección de una dirección de origen disponible para el cliente, sujeta a las restricciones actuales;
- búsqueda de destinos en Australia por suburbio, estado y postcode, manteniendo el formato actual;
- opciones actuales de la página y sus restricciones;
- creación de un shipment con una o varias líneas de productos;
- selección de SKU del cliente, cantidad y datos asociados;
- opción de agregar o eliminar líneas;
- opción de introducir carga personalizada cuando el flujo actual lo permita;
- Shipment Summary con número de ítems/líneas, peso total y cubicaje total;
- campo Cubic Margin con su comportamiento actual;
- botón Calculate Freight;
- lista de carriers y servicios con estimaciones ordenadas por precio y etiquetadas correctamente como estimaciones;
- administración de quotations, respetando roles, permisos y cliente autorizado.

No rediseñes ni elimines funciones visuales aprobadas sin explicar el problema comprobado y proponer el cambio mínimo.

## 3. Planilla electrónica como referencia funcional

Inspecciona directamente las hojas, fórmulas, tablas y rangos relevantes del workbook disponible. No te bases solo en resúmenes anteriores.

Documenta cómo se relacionan, al menos:
- Calculator;
- SettingFlags;
- FuelSurcharge y fuel;
- CalcLines;
- BrokerTotals;
- SKUs;
- SUBURBS;
- ZONES;
- RATES;
- hojas auxiliares de carga o actualización de datos.

Explica con datos y fórmulas inspeccionados:
- qué hace Preselect SKU Mode y cuándo se usa frente a la carga personalizada;
- cómo se consolida cantidad, peso y cubicaje;
- cómo se aplica el pallet tare y bajo qué condiciones;
- cómo se obtiene el peso/cubicaje cobrable;
- cómo se seleccionan zona, tarifa, mínimos, incrementos y cargos adicionales;
- cómo se considera fuel, tailgate, manejo, cubic conversion y otros cargos;
- cómo se ordenan y muestran los resultados.

Distingue la planilla de TransLogic: la planilla usa tablas aplanadas y fórmulas propias. No afirmes que sigue automáticamente referencias run_rate ni que demuestra lo que TransLogic hará ante una tarjeta ausente.

## 4. Archivos y cargas

Inventaría cada fuente real disponible, indicando:
- nombre, formato, fecha/hash cuando exista;
- hojas, encabezados y columnas;
- tipo de dato esperado;
- cliente/carrier/servicio al que aplica;
- estado: disponible, validada, aplicada o activa;
- campos que no coinciden con el modelo;
- referencias a otras fuentes o tarjetas;
- riesgos de pérdida de información.

Diseña la carga para admitir los formatos reales requeridos, incluidos XLS/XLSX y CSV donde corresponda. Valida con archivos originales que contienen datos reales.

Presta atención a:
- codificación y BOM;
- delimitadores, comillas, comas dentro de textos y saltos de línea;
- caracteres acentuados, apóstrofes, nombres y direcciones;
- ceros iniciales en códigos, SKU y postcodes;
- espacios, duplicados, celdas vacías y encabezados alternativos;
- tipos numéricos, fechas y redondeo;
- preservación exacta del archivo fuente y trazabilidad de cada valor.

El flujo debe separar:
1. carga;
2. validación estructural;
3. revisión semántica y de aplicabilidad;
4. comparación/preview;
5. activación explícita;
6. verificación;
7. reversión.

No trates el estado Validated como sinónimo de activo para cotizar. No uses fuentes antiguas o la planilla como fallback silencioso.

## 5. Reglas de negocio y procedimiento

Antes de implementar, revisa las reglas aprobadas y conserva las que sigan vigentes.

Analiza con evidencia cada ruta STH desde el selector inicial hasta los cargos que componen la cotización. Para cada ruta o escenario, registra:
- cliente;
- carrier y servicio;
- origen y destino;
- shipment y tipo de carga;
- peso y cubicaje;
- zona/subzona/área y break;
- tarjeta inicial y cada referencia run_rate;
- condiciones evaluadas;
- cargos obtenidos y orden de aplicación;
- fuente y versión de los datos;
- resultado de planilla, TransLogic y app, cuando los tres existan.

Clasifica las referencias condicionales como:
- APPLICABLE;
- NOT_APPLICABLE;
- UNKNOWN.

Una referencia desconocida no equivale a cero ni demuestra que no se use. Tampoco conviertas una referencia del catálogo en un bloqueo para todas las rutas STH. Avanza con las rutas demostrablemente no afectadas y deja visibles los casos que no puedan certificarse como completos.

## 6. Validación operacional con quien hizo la planilla

Prepara una sesión estructurada de walkthrough para confirmar cómo TransLogic procesa transacciones reales. Presenta estas preguntas como validación del mapeo entre operación y aplicación:

- ¿Cuál es la ruta completa desde el cliente/servicio STH hasta el cargo final?
- ¿Qué tarjetas seleccionan carrier, servicio, zona y tipo de carga?
- ¿Cómo se evalúan las condiciones y los punteros run_rate?
- ¿Qué sucede si una tarjeta referenciada no existe, está cancelada o no aplica?
- ¿Qué significa cada campo utilizado por las reglas, incluido driver_zones.type y Price?
- ¿Cómo se aplican los mínimos WTR/WTRM, combustible, tailgate, pallets, cartons, cubic y cargos adicionales?
- ¿Qué atributos del trabajo activan cargos por pallet, por case o por consignación?
- ¿Cuál es el procedimiento operativo para actualizar las tarifas y verificar la versión activa?

Hay que  recorrer de principio a fin algunos casos STH reales y explique cada línea/cargo, no solo el total. Registra ejemplos, capturas o resultados permitidos, versión de la fuente y excepciones. No presentes como confirmada una regla hasta tener evidencia.

## 7. Estado del proyecto

Entrega una matriz con estas categorías:
- IMPLEMENTADO;
- PROBADO;
- VERIFICADO;
- PENDIENTE;
- DESCONOCIDO;
- LISTO PARA PRODUCCIÓN.

No uses esos estados como sinónimos. Indica evidencia, fecha, snapshot y alcance de cada uno.

Incluye por separado:
- interfaz aprobada;
- permisos y roles;
- cotizaciones guardadas;
- lógica de la planilla;
- importadores existentes;
- revisión estructural de Rate Cards;
- conexión de Rate Cards al motor;
- combustible y zonas;
- reglas no confirmadas;
- pruebas ejecutadas y no ejecutadas;
- rollback y readiness.

## 8. Plan por fases

Propón fases pequeñas, verificables y sin cambios de producción:

1. Inventario del snapshot actual y documentación.
2. Confirmación funcional de la interfaz que se conserva.
3. Mapeo workbook → reglas y datos actuales.
4. Walkthrough operacional de TransLogic con la persona encargada.
5. Diagnóstico read-only del importador y del quote engine actual.
6. Diseño mínimo de carga, trazabilidad, resolución de referencias y errores.
7. Pruebas aisladas con casos STH, incluyendo rutas normales y excepciones.
8. Revisión de resultados, regresiones y rollback.
9. Documentación de reglas confirmadas y pendientes.
10. Decisión de release GO/NO-GO basada en evidencia.

No implementes todavía. Primero entrega el análisis, el plan, las decisiones pendientes para la persona operativa y una lista de pruebas de aceptación. Espera revisión del dueño del proyecto antes de iniciar cambios de código, reglas o base de datos.