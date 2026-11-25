# Plan de mejora del backoffice Django de CALC

Actúa como analista de negocio, diseñador UX y arquitecto Django senior. Necesito preparar un plan para mejorar la administración del backoffice de CALC sin perder las funciones que ya trabajan bien.

## 1. Objetivo

Revisar el backoffice actual y proponer mejoras para que la importación y conciliación de archivos sean más claras, fáciles de administrar e intuitivas.

Antes de proponer cambios, inspecciona el código Django disponible y la documentación del proyecto. Describe lo que existe y cómo funciona actualmente. No inventes opciones, modelos, permisos ni flujos que no hayas comprobado.

En esta etapa, entrega un análisis y un plan. No modifiques código, base de datos ni reglas de negocio.

## 2. Funciones que queremos conservar

El backoffice actual funciona bien en varias áreas. Evalúa cómo mantener el comportamiento existente de:

- auditoría de eventos;
- administración de clientes;
- carriers y servicios;
- permisos y controles actuales;
- las funciones que ya están comprobadas y no forman parte de este pedido.

No propongas rediseñar estas áreas sin identificar primero un problema concreto.

## 3. Áreas que necesitan revisión

### Importación de archivos

La sección de importaciones se siente compleja de administrar. Revisa cómo se cargan, validan, revisan y aplican los archivos actualmente.

Algunas opciones para consultar el estado o los detalles de los registros parecen estar escondidas detrás de palabras o enlaces azules dentro del texto. Evalúa una navegación más clara, por ejemplo mediante menús, acciones visibles o secciones accesibles directamente desde la pantalla correspondiente.

El objetivo es que el usuario pueda entender con facilidad:

- qué archivos y registros está revisando;
- qué estado tiene cada registro;
- qué acciones están disponibles;
- qué ocurrirá antes de aplicar cambios.

No asumas que todos los tipos de archivo tienen el mismo flujo. Examina cada importador y señala las diferencias.

### Conciliaciones y corrección de registros

En las pantallas donde se revisan SKU y estados de importación, es común tener que corregir registros individualmente o en grupo antes de aplicar los datos a la base de datos.

Evalúa si el usuario puede hacer estas correcciones desde la misma pantalla de conciliación, sin tener que navegar a secciones anteriores y luego regresar para continuar.

La propuesta debe considerar:

- selección clara de registros;
- corrección individual;
- corrección grupal cuando los registros seleccionados compartan el mismo tipo de cambio;
- visibilidad de los cambios propuestos antes de aplicarlos;
- conservación del flujo actual de validación, permisos y auditoría;
- facilidad para volver a la conciliación y continuar desde donde quedó.

No combines automáticamente registros que necesiten decisiones distintas. Identifica qué acciones grupales son seguras según el comportamiento real del sistema.

### Rate Cards y Rates

Es correcto que Rates tenga un área específica para su revisión y resolución. Mantén separada esta área de las importaciones generales.

El flujo definitivo de Rates debe definirse después de la reunión de revisión operativa. Antes de esa reunión, inspecciona y documenta el estado actual, pero no cambies su lógica ni des por confirmadas reglas operativas.

## 4. Método de análisis

Presenta el resultado separando:

- **Verificado:** lo que observaste directamente en el código, la interfaz o la documentación.
- **Inferido:** interpretaciones razonables que aún requieren confirmación.
- **Pendiente de decisión:** temas que necesitan definición del dueño del proyecto o de la persona responsable del proceso.
- **Fuera de alcance:** funciones que deben conservarse y no se modificarán en esta etapa.

Para cada mejora propuesta, indica:

- problema observado;
- evidencia;
- flujo actual;
- cambio de interfaz o navegación propuesto;
- impacto para el usuario;
- riesgos para validación, permisos, auditoría o aplicación de datos;
- criterios de aceptación;
- pruebas necesarias;
- estrategia de reversión.

Prioriza mejoras pequeñas e incrementales. No propongas reescribir el backoffice completo si el problema puede resolverse mejorando la navegación o el flujo de conciliación existente.

## 5. Entregables de esta etapa

Entrega:

1. Un inventario breve de las secciones actuales del backoffice relacionadas con importaciones y conciliaciones.
2. Un mapa del flujo actual desde la carga hasta la aplicación de datos.
3. Una lista de dificultades de navegación y pasos innecesarios comprobados.
4. Una propuesta de mejoras para importaciones generales.
5. Una propuesta de mejoras para correcciones individuales y grupales desde conciliaciones.
6. Una sección separada para Rates, indicando qué debe esperar la reunión operativa.
7. Una matriz de prioridades con alcance, dependencias y criterios de aceptación.
8. Una lista de preguntas concretas que debamos resolver antes de implementar.

No implementes los cambios todavía. Primero necesito revisar y aprobar el plan.