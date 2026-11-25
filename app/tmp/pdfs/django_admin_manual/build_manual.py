from pathlib import Path
from io import BytesIO

from PIL import Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, Image as RLImage, PageBreak, PageTemplate,
    Paragraph, Spacer, Table, TableStyle, KeepTogether,
)

ROOT = Path('/app')
IMG_DIR = ROOT / 'tmp/pdfs/django_admin_manual'
OUT = ROOT / 'output/pdf/manual_administracion_django.pdf'
OUT.parent.mkdir(parents=True, exist_ok=True)

PAGE = landscape(A4)
W, H = PAGE
NAVY = colors.HexColor('#17324D')
BLUE = colors.HexColor('#2D6F91')
PALE = colors.HexColor('#EAF2F7')
GOLD = colors.HexColor('#D9A441')
INK = colors.HexColor('#1E2933')
MUTED = colors.HexColor('#5D6B76')


styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='TitleDV', fontName='Helvetica-Bold', fontSize=26, leading=31, textColor=NAVY, alignment=TA_LEFT, spaceAfter=8))
styles.add(ParagraphStyle(name='SubDV', fontName='Helvetica', fontSize=12, leading=17, textColor=MUTED))
styles.add(ParagraphStyle(name='H1DV', fontName='Helvetica-Bold', fontSize=19, leading=23, textColor=NAVY, spaceAfter=8))
styles.add(ParagraphStyle(name='H2DV', fontName='Helvetica-Bold', fontSize=11, leading=14, textColor=BLUE, spaceBefore=5, spaceAfter=3))
styles.add(ParagraphStyle(name='BodyDV', fontName='Helvetica', fontSize=9, leading=13, textColor=INK))
styles.add(ParagraphStyle(name='SmallDV', fontName='Helvetica', fontSize=7.5, leading=10, textColor=MUTED))
styles.add(ParagraphStyle(name='CellDV', fontName='Helvetica', fontSize=7.6, leading=10, textColor=INK))
styles.add(ParagraphStyle(name='CellBoldDV', fontName='Helvetica-Bold', fontSize=7.6, leading=10, textColor=NAVY))
styles.add(ParagraphStyle(name='WhiteDV', fontName='Helvetica-Bold', fontSize=8, leading=10, textColor=colors.white))
styles.add(ParagraphStyle(name='CaptionDV', fontName='Helvetica', fontSize=7.5, leading=10, textColor=MUTED, alignment=TA_CENTER))


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor('#CCD7DF'))
    canvas.line(14*mm, 10*mm, W-14*mm, 10*mm)
    canvas.setFont('Helvetica', 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(14*mm, 6*mm, 'Steadfast Freight Calculator v1.8.0 — Manual de administración')
    canvas.drawRightString(W-14*mm, 6*mm, f'Página {doc.page}')
    canvas.restoreState()


doc = BaseDocTemplate(str(OUT), pagesize=PAGE, leftMargin=14*mm, rightMargin=14*mm,
                      topMargin=12*mm, bottomMargin=14*mm, title='Manual de administración Django')
doc.addPageTemplates(PageTemplate(id='main', frames=[Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='body')], onPage=footer))


def p(text, style='BodyDV'):
    return Paragraph(text, styles[style])


def table(rows, widths=None):
    data = [[p(c, 'WhiteDV') for c in rows[0]]]
    for row in rows[1:]:
        data.append([p(row[0], 'CellBoldDV')] + [p(c, 'CellDV') for c in row[1:]])
    t = Table(data, colWidths=widths, repeatRows=1, hAlign='LEFT')
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), NAVY),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('GRID', (0,0), (-1,-1), 0.35, colors.HexColor('#CBD5DD')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F6F9FB')]),
        ('LEFTPADDING', (0,0), (-1,-1), 5), ('RIGHTPADDING', (0,0), (-1,-1), 5),
        ('TOPPADDING', (0,0), (-1,-1), 4), ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    return t


def screenshot(name, caption, max_w=263*mm, max_h=118*mm, crop_height=1120):
    src = IMG_DIR / f'{name}.png'
    im = Image.open(src).convert('RGB')
    if crop_height and im.height > crop_height:
        im = im.crop((0, 0, im.width, crop_height))
    bio = BytesIO()
    im.save(bio, format='JPEG', quality=84, optimize=True)
    bio.seek(0)
    ratio = min(max_w/im.width, max_h/im.height)
    pic = RLImage(bio, width=im.width*ratio, height=im.height*ratio)
    return KeepTogether([pic, Spacer(1, 2*mm), p(caption, 'CaptionDV')])


story = []
story += [Spacer(1, 20*mm), p('Manual de administración', 'TitleDV'),
          p('Steadfast Freight Calculator — Django Admin v1.8.0', 'SubDV'), Spacer(1, 10*mm),
          p('<b>Objetivo.</b> Explicar brevemente las opciones visibles en la administración, en su orden real de aparición, con ejemplos prácticos y capturas de referencia.', 'BodyDV'),
          Spacer(1, 6*mm),
          table([
              ['Dato', 'Contenido'],
              ['Aplicación', 'Steadfast Freight Calculator'],
              ['Versión observada', 'v1.8.0'],
              ['Pantallas capturadas', '23 de noviembre de 2026'],
              ['Idioma de la interfaz', 'Inglés australiano; explicaciones de este manual en español'],
          ], [48*mm, 150*mm]), Spacer(1, 10*mm),
          p('<b>Regla simple:</b> use <i>View/Change</i> para revisar o modificar un registro existente y <i>Add</i> para crear uno nuevo. Los datos importados deben revisarse desde <i>Import Centre</i> antes de corregir registros manualmente.', 'BodyDV'),
          PageBreak()]

story += [p('Mapa del administrador', 'H1DV'),
          p('La pantalla inicial agrupa las opciones por función. El orden mostrado abajo es el mismo del menú actual.', 'BodyDV'), Spacer(1, 3*mm),
          screenshot('admin_home_full', 'Pantalla inicial del Django Admin: grupos y accesos disponibles.', max_h=145*mm, crop_height=None), PageBreak()]

story += [p('1. AUDIT', 'H1DV'),
          table([
              ['Opción', 'Qué hace', 'Ejemplo claro'],
              ['Audit events', 'Muestra el registro de acciones relevantes realizadas en la aplicación. Es una vista de consulta.', 'Buscar quién realizó una importación o cuándo ocurrió un cambio operativo.'],
          ], [48*mm, 105*mm, 105*mm]), Spacer(1, 5*mm),
          screenshot('audit_events', 'Audit events conserva trazabilidad con tipo de evento, usuario, mensaje y fecha.', max_h=135*mm), PageBreak()]

story += [p('2. CARRIERS', 'H1DV'),
          table([
              ['Opción', 'Qué hace', 'Ejemplo claro'],
              ['Carrier services', 'Define la combinación transportista + servicio que puede participar en una cotización.', 'TEAMEX + ROAD o TFMX + ROAD.'],
              ['Carriers', 'Mantiene el maestro de transportistas: código, nombre y estado activo.', 'Desactivar un transportista que ya no debe ofrecerse.'],
              ['Client carrier configs', 'Configura por cliente el ratecard, combustible, conversión cúbica y reglas habilitadas para cada servicio.', 'Para STH, asignar la tarjeta de TEAMEX y habilitar pallets o cartons.'],
          ], [48*mm, 105*mm, 105*mm]), Spacer(1, 5*mm),
          screenshot('carrier_configs', 'Client carrier configs: configuración operativa por cliente y servicio.', max_h=126*mm), PageBreak()]

story += [p('3. CUSTOMERS', 'H1DV'),
          table([
              ['Opción', 'Qué hace', 'Ejemplo claro'],
              ['Calculator Customers', 'Clientes habilitados para usar una calculadora propia. Incluye reglas de dimensiones y estado.', 'STH activo y asociado a su configuración de cálculo.'],
              ['Commercial Customers', 'Vista comercial del maestro de clientes, con sus secciones asociadas.', 'Revisar las divisiones comerciales registradas para una cuenta.'],
              ['Customer Sections', 'Relaciona una sección o división con un cliente del maestro.', 'Distinguir una sección logística dentro del cliente STH.'],
              ['Customer imports', 'Historial de cargas del archivo maestro de clientes.', 'Comprobar si la última planilla de clientes se importó correctamente.'],
              ['Customers', 'Maestro de clientes proveniente de Translogic; es independiente de Calculator Customers.', 'Buscar un código de cliente y luego habilitarlo como Calculator Customer.'],
              ['Freight calculators', 'Configura la calculadora asignada a cada cliente: versión, motor, margen cúbico e historial visible.', 'Habilitar cubic margin y definir las opciones 0–20 para STH.'],
          ], [48*mm, 105*mm, 105*mm]), Spacer(1, 4*mm),
          screenshot('calculator_customers', 'Calculator Customers: clientes que tienen acceso a una calculadora.', max_h=77*mm), PageBreak()]

story += [p('CUSTOMERS — segunda referencia', 'H1DV'),
          p('<b>No confundir:</b> <i>Customers</i> es el maestro general de Translogic; <i>Calculator Customers</i> contiene solo los clientes habilitados para calcular.', 'BodyDV'), Spacer(1, 4*mm),
          screenshot('commercial_customers', 'Commercial Customers: vista comercial del maestro y sus relaciones.', max_h=147*mm), PageBreak()]

story += [p('4. IMPORTS', 'H1DV'),
          table([
              ['Opción', 'Qué hace', 'Ejemplo claro'],
              ['Import Centre', 'Centraliza el calendario FTP y la recepción/revisión de Products, Stock, Fuel, Postcodes, Rates y Zones.', 'Ejecutar “Check inbox now”, revisar el resultado y confirmar qué versión está “In use”.'],
          ], [48*mm, 105*mm, 105*mm]), Spacer(1, 4*mm),
          p('<b>Uso recomendado:</b> esta es la entrada principal para datos externos. El calendario compartido se ejecuta en hora de Adelaide; los archivos habilitados se procesan para los clientes activos correspondientes.', 'BodyDV'), Spacer(1, 4*mm),
          screenshot('import_centre', 'Import Centre: programación, archivos operativos, estado y acciones de revisión.', max_h=127*mm), PageBreak()]

story += [p('5. LOCATIONS', 'H1DV'),
          table([
              ['Opción', 'Qué hace', 'Ejemplo claro'],
              ['From addresss', 'Mantiene las direcciones de origen por cliente y permite marcar una dirección predeterminada.', 'Definir el depósito de STH como origen por defecto.'],
              ['Suburbs', 'Maestro australiano de suburb, state y postcode usado para reconocer destinos.', 'Localizar “Adelaide SA 5000” al validar una dirección.'],
          ], [48*mm, 105*mm, 105*mm]), Spacer(1, 5*mm),
          screenshot('from_addresses', 'From addresss: puntos de origen disponibles en la calculadora.', max_h=135*mm), PageBreak()]

story += [p('6. PRODUCTS', 'H1DV'),
          table([
              ['Opción', 'Qué hace', 'Ejemplo claro'],
              ['Products', 'Maestro operativo de SKU por cliente: dimensiones, peso, volumen, tipo de carga, estado y fila de origen.', 'Revisar que un SKU de STH tenga peso y dimensiones válidos antes de cotizar.'],
          ], [48*mm, 105*mm, 105*mm]), Spacer(1, 4*mm),
          p('<b>Importante:</b> un producto puede ser tipo Pallet (P) o Case/Carton (C). Las dimensiones y el peso alimentan el cálculo del peso cobrable; las correcciones deben conservar la referencia a la fuente.', 'BodyDV'), Spacer(1, 4*mm),
          screenshot('products', 'Products: lista operativa de SKU y sus valores físicos.', max_h=127*mm), PageBreak()]

story += [p('7. RATES', 'H1DV'),
          table([
              ['Opción', 'Qué hace', 'Ejemplo claro'],
              ['Carrier tailgate charges', 'Define cargos de tailgate por cliente y transportista: mínimo, unidades posteriores y descarga manual.', 'Aplicar un cargo cuando el destino requiere plataforma elevadora.'],
              ['Freight rates', 'Contiene las filas de la tarjeta: zona, break, tipo de carga, mínimo, básico, por kg y otros cargos.', 'Buscar la fila TEAMEX/ROAD para la zona calculada y freight type P.'],
              ['Freight zones', 'Relaciona destino + servicio con zone, subzone y area.', 'Convertir un postcode de destino en la zona usada para buscar el rate.'],
          ], [48*mm, 105*mm, 105*mm]), Spacer(1, 5*mm),
          screenshot('freight_rates', 'Freight rates: filas de tarifa usadas por el procedimiento operacional.', max_h=119*mm), PageBreak()]

story += [p('RATES — zonas de destino', 'H1DV'),
          p('La secuencia principal es: <b>destino / Freight zone / Freight rate / cargos adicionales</b>. Si no se encuentra zona o tarifa, la cotización debe advertirlo en vez de inventar un valor.', 'BodyDV'), Spacer(1, 4*mm),
          screenshot('freight_zones', 'Freight zones: equivalencia entre suburb/postcode y la zona de cada servicio.', max_h=145*mm), PageBreak()]

story += [p('Flujos rápidos de ejemplo', 'H1DV'),
          table([
              ['Necesidad', 'Ruta recomendada', 'Resultado esperado'],
              ['Activar un nuevo cliente', 'Customers / Customers; después Calculator Customers; finalmente Freight calculators.', 'Cliente vinculado, activo y con calculadora configurada.'],
              ['Actualizar datos operativos', 'Imports / Import Centre / Check inbox now / revisar estado e historial.', 'Nueva versión validada; la columna Operational status indica si está en uso.'],
              ['Investigar una cotización sin tarifa', 'Rates / Freight zones; luego Freight rates; revisar también Client carrier configs.', 'Confirmar si falta zona, ratecard, freight type o configuración del servicio.'],
              ['Revisar un SKU', 'Products / Products; buscar por client o SKU.', 'Peso, dimensiones, cubic m³ y freight type coherentes.'],
              ['Comprobar quién hizo un cambio', 'Audit / Audit events.', 'Evento, usuario, fecha y detalle disponibles.'],
          ], [55*mm, 112*mm, 91*mm]), Spacer(1, 8*mm),
          p('<b>Consejo de operación:</b> antes de editar manualmente un dato importado, confirme si el siguiente proceso FTP lo reemplazará. Para datos externos, la evidencia principal debe quedar en Import Centre y Audit events.', 'BodyDV'),
          Spacer(1, 10*mm), p('Fin del manual', 'H2DV')]

doc.build(story)
print(OUT)
