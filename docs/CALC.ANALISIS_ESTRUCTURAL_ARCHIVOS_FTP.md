# Análisis estructural de archivos para CALC

Fecha del análisis: 10 de noviembre de 2026  
Modalidad: solo lectura

## Objetivo y alcance

Se analizaron los siguientes ocho archivos:

- `stock_STH(1).xls`
- `zones.csv`
- `customers.xls`
- `fuel.xls`
- `postcodes.xls`
- `products(2).xls`
- `rates_all(2).xls`
- `stock(4).xls`

El análisis cubrió todas las hojas, encabezados, columnas y filas mediante perfilado automatizado. No se realizó una interpretación manual celda por celda y no se modificaron los archivos originales ni la aplicación CALC.

## Disponibilidad de documentación y código de CALC

La carpeta de trabajo de CALC no contenía archivos `.md`, repositorio ni código de importación. El material accesible estaba limitado a los ocho archivos indicados.

Por este motivo, no fue posible verificar:

- Qué columnas consume actualmente CALC.
- Si CALC depende del nombre del archivo o de la hoja.
- Qué conversiones de tipo realiza.
- Qué claves, relaciones o normalizaciones aplica.
- Cómo trata duplicados, referencias faltantes, ceros iniciales y campos vacíos.
- Cómo interpreta las expresiones y unidades de `rates_all`.
- Cuáles son sus límites de filas y memoria.

Las observaciones de este documento describen los archivos reales. No se atribuye ningún comportamiento a CALC sin código, documentación o una prueba controlada de la aplicación.

## Resumen del inventario

Todos los libros Excel contienen una sola hoja visible y ninguna fórmula. Las cantidades siguientes excluyen la fila de encabezados.

| Archivo | Hoja | Filas | Columnas | Clave individual verificable |
|---|---|---:|---:|---|
| `stock(4).xls` | `stock` | 21.378 | 8 | Ninguna |
| `rates_all(2).xls` | `rates_all` | 8.727 | 27 | `rate_no` |
| `products(2).xls` | `products` | 39.104 | 23 | `code` |
| `postcodes.xls` | `postcodes` | 18.101 | 4 | `index` |
| `fuel.xls` | `fuel` | 19 | 5 | `rate_no`; `name` también es único |
| `customers.xls` | `cust02_7kh0v815v` | 111 | 14 | `code` |
| `zones.csv` | No aplica | 211.329 | 9 | Ninguna |
| `stock_STH(1).xls` | `Sheet1` | 913 | 8 | Ninguna |

## Inventario de columnas y tipos

### `stock(4).xls`

Encabezados:

`customer`, `product`, `description`, `quantity`, `category`, `serial_no`, `cubic`, `weight`

Tipos lógicos:

- Texto o identificador: `customer`, `product`, `description`, `category`, `serial_no`.
- Entero: `quantity`.
- Decimal: `cubic`, `weight`.

Campos incompletos:

- `description`: 5 vacíos.
- `serial_no`: 12.833 vacíos.

Cardinalidad y límites principales:

- `customer`: 90 valores distintos.
- `product`: 15.872 valores distintos.
- `quantity`: valores entre 1 y 199.999.998.
- `cubic`: incluye un valor negativo; máximo 99.999,999.
- `weight`: máximo aproximado 999.959,996.
- Filas exactamente duplicadas: 121.

### `stock_STH(1).xls`

Encabezados y tipos iguales a `stock(4).xls`.

Campos incompletos:

- `serial_no`: 42 vacíos.

Cardinalidad y límites principales:

- `customer`: un único cliente.
- `product`: 136 valores distintos.
- `quantity`: entre 1 y 400.
- `cubic`: entre 0 y 11,824.
- `weight`: entre 0 y 3.400.
- No hay filas exactamente duplicadas.

### `rates_all(2).xls`

Encabezados:

`master_rate`, `rate_no`, `break`, `item_no`, `code`, `run_rate`, `name`, `filter_field`, `from`, `greater`, `upto`, `to`, `band`, `each`, `unit`, `rate`, `basic_charge`, `min_charge`, `cubic`, `gl_code`, `analysis`, `gst_code`, `rcst`, `rc_name`, `rtst`, `group1`, `rate_code`

Tipos lógicos:

- Identificadores: `master_rate`, `rate_no`, `run_rate`.
- Enteros: `break`, `item_no`, `each`, `cubic`.
- Decimales: `greater`, `upto`, `rate`, `basic_charge`, `min_charge`.
- Texto, categorías o expresiones: las demás columnas.

Campos incompletos:

- `code`: 8.727 vacíos; la columna completa está vacía.
- `run_rate`: 8.416 vacíos.
- `filter_field`: 46 vacíos.
- `from`: 240 vacíos.
- `to`: 236 vacíos.
- `gl_code`: 8.691 vacíos.
- `analysis`: 1.668 vacíos.
- `gst_code`: 10 vacíos.
- `rate_code`: 407 vacíos.

Características:

- `rate_no` es único en las 8.727 filas.
- `master_rate`: 177 valores distintos.
- `filter_field`: 75 variantes.
- `unit`: 18 variantes.
- `rate_code`: 18 valores no vacíos distintos.
- Columnas constantes o completamente vacías: `code`, `band`, `each`, `rcst`, `rtst`.
- Hay 26 tarifas negativas.
- No existen filas con `greater > upto`.
- No hay filas exactamente duplicadas.
- La combinación `master_rate + break + item_no` tiene cuatro filas duplicadas.

La variante dominante de `filter_field` es `DEL_ZONE`, con 7.722 filas. También aparecen nombres de campo y expresiones procedurales complejas, por ejemplo condiciones sobre peso, cubicaje, pallets, comentarios e instrucciones.

### `products(2).xls`

Encabezados:

`customer`, `code`, `name`, `description`, `category`, `length`, `width`, `height`, `cubic`, `quantity`, `weight`, `pallet`, `comment`, `status`, `outer_l`, `outer_w`, `outer_h`, `inner_l`, `inner_w`, `inner_h`, `piece_l`, `piece_w`, `piece_h`

Tipos lógicos:

- Texto o identificador: `customer`, `code`, `name`, `description`, `category`, `comment`, `status`.
- Enteros: `length`, `width`, `height`, `pallet`, `outer_l`, `outer_w`, `outer_h`, `inner_l`, `inner_w`, `inner_h`, `piece_l`, `piece_w`, `piece_h`.
- Decimales: `cubic`, `quantity`, `weight`.

Campos incompletos:

- `customer`: 3 vacíos.
- `name`: 9 vacíos.
- `description`: 55 vacíos.
- `category`: 160 vacíos.
- `comment`: 19.142 vacíos.

Características:

- `code` es único en las 39.104 filas.
- `customer`: 119 valores distintos entre los no vacíos.
- `status` tiene un único valor en todas las filas.
- `length`, `width` y `height` son cero en aproximadamente 28.000 filas.
- `outer_l`, `outer_w` y `outer_h` son cero en 31.712 filas.
- Cada dimensión `inner_*` y `piece_*` solo está poblada con un valor distinto de cero en dos productos.
- No hay dimensiones negativas.
- No hay filas exactamente duplicadas.

### `postcodes.xls`

Encabezados:

`index`, `suburb`, `state`, `postcode`

Las cuatro columnas deben tratarse como texto. En especial, `postcode` debe preservar los ceros iniciales.

Características:

- No hay campos vacíos.
- `index` es único en las 18.101 filas.
- La combinación `suburb + state + postcode` también es única.
- `postcode`: 2.969 valores distintos.
- No hay filas exactamente duplicadas.

### `fuel.xls`

Encabezados:

`rate_no`, `carrier`, `name`, `surcharge`, `type`

Tipos lógicos:

- Identificador: `rate_no`.
- Texto: `carrier`, `name`, `type`.
- Decimal: `surcharge`.

Características:

- No hay campos vacíos.
- `rate_no` y `name` son únicos.
- `carrier`: 13 valores distintos.
- `surcharge`: entre 10,5 y 53.
- `type` tiene un único valor.
- No hay filas exactamente duplicadas.

### `customers.xls`

Encabezados:

`code`, `name`, `group`, `group1`, `group2`, `their_code`, `wh_pick_code`, `acn`, `abn`, `gst_code`, `sett_days`, `paydays_type`, `date`, `user`

Tipos lógicos:

- Texto o identificador: todas salvo `sett_days` y `date`.
- Entero: `sett_days`.
- Fecha: `date`.

`ACN` y `ABN` deben conservarse como identificadores, aunque su contenido parezca numérico.

Campos incompletos:

- `group`: 69 vacíos.
- `group2`: 4 vacíos.
- `their_code`: 109 vacíos.
- `wh_pick_code`: 7 vacíos.
- `acn`: 16 vacíos.
- `abn`: 69 vacíos.
- `gst_code`: 2 vacíos.
- `paydays_type`: 23 vacíos.
- `user`: 6 vacíos.

Características:

- `code` es único en las 111 filas.
- `name` contiene 109 valores distintos.
- No hay filas exactamente duplicadas.

### `zones.csv`

Encabezados:

`index`, `index2`, `carrier`, `suburb`, `state`, `postcode`, `zone`, `subzone`, `area`

El archivo usa codificación UTF-8 con encabezado y separador coma. Todas las columnas deberían tratarse como texto. `postcode`, `zone` y `subzone` contienen combinaciones numéricas y alfanuméricas.

Campos incompletos:

- `subzone`: 148.398 vacíos.
- `area`: 72.513 vacíos.
- Las otras columnas están completas.

Características:

- `index`: 202.617 valores literales distintos; no es único.
- `index2`: 2.052 valores distintos.
- `carrier`: 20 valores distintos.
- `postcode`: 4.742 representaciones literales distintas.
- `zone`: 1.614 valores distintos.
- `subzone`: 161 valores no vacíos distintos.
- `area`: 3.480 valores no vacíos distintos.
- Hay 105 filas exactamente duplicadas.
- Existen 6.306 grupos con `index` repetido; 6.271 de ellos enlazan contenidos diferentes.
- Un mismo `index` aparece hasta 170 veces.
- Existen cuatro filas con `state = 9`.
- `state` también incluye `NZ`, además de estados y territorios australianos.
- Cinco códigos postales tienen longitud 1, 855 tienen longitud 3 y 210.469 tienen longitud 4.

## Claves verificadas y claves no seguras

### Claves individuales confiables en estos archivos

- `rates_all.rate_no`.
- `products.code`.
- `postcodes.index`.
- `fuel.rate_no`.
- `fuel.name`.
- `customers.code`.

### Tablas sin clave individual confiable

#### `stock`

- `customer + product`: 7.004 filas participan en combinaciones repetidas.
- `customer + product + serial_no`: 558 filas participan en claves repetidas.
- Incluso cuando `serial_no` está informado, 189 filas continúan participando en claves repetidas.
- Se recomienda generar un identificador técnico de línea durante la importación.

#### `stock_STH`

- `customer + product` no es único.
- `customer + product + serial_no` es único cuando la serie está informada.
- Las 42 series vacías impiden usar esa combinación como clave general.

#### `zones`

- `index` no es único.
- `carrier + suburb + state + postcode` tampoco es completamente único.
- Debe utilizarse una clave técnica para cada regla de zona y conservar `index` como atributo de origen.

## Relaciones verificadas

| Relación propuesta | Filas de origen no vacías | Filas relacionadas | Cobertura | Valores distintos sin relación |
|---|---:|---:|---:|---:|
| `stock.customer -> customers.code` | 21.378 | 21.309 | 99,677% | 2 |
| `stock.product -> products.code` | 21.378 | 20.398 | 95,416% | 562 |
| `stock_STH.customer -> customers.code` | 913 | 913 | 100% | 0 |
| `stock_STH.product -> products.code` | 913 | 909 | 99,562% | 3 |
| `products.customer -> customers.code` | 39.101 | 38.287 | 97,918% | 17 |
| `zones.carrier -> fuel.carrier` | 211.329 | 146.757 | 69,445% | 9 |
| `fuel.rate_no -> rates_all.master_rate` | 19 | 17 | 89,474% | 2 |
| `fuel.name -> rates_all.rc_name` | 19 | 17 | 89,474% | 2 |
| `zones.postcode -> postcodes.postcode` | 211.329 | 207.416 | 98,148% | 1.725 |
| `zones.(suburb,state,postcode) -> postcodes.(suburb,state,postcode)` | 211.329 | 178.251 | 84,348% | 16.013 |

Relaciones que no se verificaron:

- `rates_all.group1` no coincide con `customers.group1`; representan dominios diferentes pese a compartir nombre.
- `zones.index` no coincide con `postcodes.index`.
- `zones.index2` tampoco coincide con `postcodes.index`.

## Consistencia entre stock y productos

### `stock(4).xls`

- 20.398 filas tienen un producto presente en `products`.
- 980 filas no encuentran producto.
- Entre las filas relacionadas, la descripción coincide en 20.255 casos, equivalentes al 99,299%.
- Hay 143 diferencias de descripción.
- `stock.category` no coincide con `products.category` en ninguna fila relacionada.

### `stock_STH(1).xls`

- 909 filas tienen un producto presente en `products`.
- 4 filas no encuentran producto, correspondientes a 3 códigos distintos.
- Entre las filas relacionadas, la descripción coincide en 904 casos, equivalentes al 99,45%.
- Hay 5 diferencias de descripción.
- La categoría tampoco coincide con `products.category`.

La falta total de coincidencia en `category` indica que probablemente se utilizan taxonomías diferentes. No debe implementarse una igualdad obligatoria hasta confirmar el significado empresarial de ambos campos.

## Comparación entre los dos archivos de stock

La cobertura de `stock_STH` dentro de `stock` depende de la clave utilizada:

- Por `customer + product`: 883 de 913 filas, 96,714%.
- Por `customer + product + serial_no`: 767 de 913 filas, 84,009%.
- Por cliente, producto, serie, cantidad, cubicaje y peso: 760 de 913 filas, 83,242%.

Por lo tanto, `stock_STH` no es un subconjunto exacto verificable de `stock(4).xls`.

## Inconsistencias estructurales y riesgos

### Prioridad alta

1. `stock(4).xls` presenta una inconsistencia en su contenedor binario OLE. Su tamaño no está alineado con los sectores del formato y un lector estándar de `.xls` no pudo procesarlo, aunque Microsoft Excel sí pudo abrirlo.
2. Siete archivos utilizan el formato antiguo `.xls`.
3. `zones.csv` contiene 211.329 filas. La importación debería procesarlo por bloques y no cargar todo el archivo en la interfaz.
4. Los identificadores numéricos deben conservarse como texto para no perder ceros iniciales o transformar códigos.
5. Los nombres de hoja no siguen una convención estable: nombres funcionales, `Sheet1` y un nombre generado.

### Nombres de columnas problemáticos

Los encabezados `from`, `to`, `break`, `group`, `date` e `index` pueden colisionar con palabras reservadas o funciones de bases de datos y lenguajes. La nueva calculadora debería mapearlos a nombres internos seguros, conservando el encabezado original como metadato.

### Duplicados

- `stock`: 121 duplicados exactos.
- `zones`: 105 duplicados exactos.
- También existen claves repetidas con contenidos diferentes.

No deberían eliminarse automáticamente. El sistema debe distinguir:

- Duplicado exacto.
- Misma clave con contenido diferente.
- Línea repetida legítima según la regla de negocio.

### Valores que requieren reglas empresariales

- Una fila de stock tiene cubicaje negativo.
- Hay cantidades y pesos extremadamente altos.
- Hay 26 tarifas negativas.
- La mayoría de las dimensiones opcionales de productos son cero.
- Existen códigos postales de una y tres posiciones.
- Existen cuatro filas con estado `9`.

Estos casos deben producir advertencias o reglas configurables, no rechazos automáticos, hasta conocer su significado.

## Mejoras priorizadas para una nueva calculadora

### P0: importación segura y reproducible

1. Definir un contrato de importación versionado para cada archivo.
2. Especificar columnas obligatorias, opcionales, alias, tipos y claves esperadas.
3. Importar primero a un área temporal y publicar los datos solo cuando finalice la validación completa.
4. Preservar como texto códigos postales, productos, clientes, series, tarifas, ACN y ABN.
5. Procesar CSV y Excel por bloques.
6. Usar `.xlsx` y CSV como formatos preferidos.
7. Para `.xls`, aplicar una conversión controlada o devolver un error detallado si el contenedor está dañado.
8. Registrar hash del archivo, fecha, versión del esquema, filas aceptadas, advertidas y rechazadas.
9. Hacer la importación atómica: un fallo parcial no debe dejar mezcladas versiones antiguas y nuevas.

### P1: modelo relacional

1. Crear maestros explícitos para clientes, productos, ubicaciones, transportistas, tarifas y recargos.
2. Generar identificadores técnicos para líneas de stock y reglas de zona.
3. No utilizar `zones.index` como clave primaria.
4. Producir un informe de referencias faltantes después de cada importación.
5. Clasificar los duplicados antes de consolidarlos.
6. Mantener separadas las categorías de stock y productos hasta confirmar su significado.

### P1: motor de tarifas

1. Sustituir las expresiones libres de `filter_field` por reglas tipadas.
2. Modelar cada regla con campo, operador, valor o rango, unidad, prioridad y vigencia.
3. No ejecutar directamente las expresiones importadas.
4. Documentar las 18 unidades observadas.
5. Incorporar fecha de vigencia, versión y estado activo.
6. Relacionar explícitamente el combustible con `master_rate` o transportista.
7. Definir el comportamiento de los dos registros de combustible sin relación con `rates_all`.

### P2: validación y operación

1. Mostrar una vista previa antes de confirmar la importación.
2. Informar filas, duplicados, referencias faltantes, columnas ausentes y columnas desconocidas.
3. Separar errores bloqueantes de advertencias empresariales.
4. Permitir umbrales configurables para cantidades, peso, cubicaje y dimensiones.
5. Incorporar pruebas automáticas con estos ocho archivos.
6. Probar específicamente ceros iniciales, duplicados, series vacías, archivos grandes y tarifas negativas.

### P3: simplificación controlada

Evaluar columnas constantes o casi vacías como `rates_all.code`, `band`, `each`, `rcst`, `rtst` y `products.status`. No deben eliminarse hasta verificar que CALC actual y los procesos operativos no las utilizan.

## Hallazgos verificados

- Estructura, hojas, encabezados y dimensiones de los ocho archivos.
- Tipos lógicos y presencia de valores.
- Claves individuales y combinaciones evaluadas.
- Duplicados exactos y claves repetidas.
- Cobertura de las relaciones indicadas.
- Ausencia de fórmulas en los libros.
- Inconsistencia del contenedor de `stock(4).xls` para lectores estrictos.
- Presencia de expresiones complejas en `rates_all.filter_field`.

## Hipótesis pendientes de confirmación

- `stock_STH` podría ser un extracto operativo o temporal de stock.
- Un transportista ausente en `fuel` podría significar que no tiene recargo.
- Las tarifas negativas podrían representar descuentos o valores centinela.
- Los ceros de dimensiones podrían significar “no aplica” o “no mantenido”.
- Las diferencias entre `zones` y `postcodes` podrían incluir alias, ubicaciones extranjeras o datos históricos.
- Las dos columnas `category` probablemente representan conceptos diferentes.

Estas hipótesis no deben convertirse en reglas automáticas sin evidencia adicional.

## Trabajo pendiente para comparar con CALC actual

Se necesita el repositorio de CALC o, como mínimo, el código del importador y la documentación relacionada. La revisión debería cubrir:

1. Detección y selección de archivos.
2. Selección de hojas.
3. Reconocimiento de encabezados.
4. Conversión de tipos y normalización de texto.
5. Preservación de ceros iniciales.
6. Relaciones utilizadas realmente.
7. Manejo de duplicados y referencias faltantes.
8. Interpretación de `filter_field`, `unit`, `from`, `to`, `greater` y `upto`.
9. Límites de filas, memoria y tiempo.
10. Comportamiento frente al archivo `.xls` estructuralmente irregular.

Hasta disponer de ese material, cualquier afirmación sobre qué lee o ignora CALC debe considerarse pendiente y no verificada.
