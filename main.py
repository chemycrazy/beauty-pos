import flet as ft
import psycopg2
import bcrypt
import os
import webbrowser
import urllib.parse # <--- NUEVO: Para crear el link de WhatsApp
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm

# --- CONFIGURACIÓN ---
# ⚠️ PON TU CONTRASEÑA AQUÍ
URL_CONEXION = "postgresql://postgres.swavrpqagshyddhjaipf:R57667115#g@aws-0-us-west-2.pooler.supabase.com:6543/postgres"

# ==========================================
# VARIABLES GLOBALES
# ==========================================
usuario_actual_id = None
usuario_actual_nombre = ""
usuario_actual_rol = ""

# Memoria temporal venta
id_variante_seleccionada = None 
precio_venta_seleccionado = 0.0
nombre_producto_seleccionado = "" 

def main(page: ft.Page):
    page.title = "Beauty POS - Con WhatsApp"
    page.window.width = 1300
    page.window.height = 900
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = "#f5f5f5"

    # ==============================================================================
    # 1. LOGIN
    # ==============================================================================
    def verificar_login(e):
        global usuario_actual_id, usuario_actual_nombre, usuario_actual_rol
        user = txt_user_login.value
        pwd = txt_pass_login.value
        btn_login.text = "Verificando..."
        page.update()

        try:
            conn = psycopg2.connect(URL_CONEXION)
            cursor = conn.cursor()
            cursor.execute("SELECT id, password_hash, rol FROM usuarios WHERE username = %s", (user,))
            res = cursor.fetchone()
            conn.close()

            if res and bcrypt.checkpw(pwd.encode(), res[1].encode()):
                usuario_actual_id = res[0]
                usuario_actual_nombre = user
                usuario_actual_rol = res[2]
                page.clean()
                construir_interfaz() 
                page.snack_bar = ft.SnackBar(ft.Text(f"Bienvenido {user}"), bgcolor="green"); page.snack_bar.open = True
            else:
                lbl_error_login.value = "❌ Datos incorrectos"
        except Exception as err:
            lbl_error_login.value = f"Error: {err}"
        
        btn_login.text = "INICIAR SESIÓN"
        page.update()

    txt_user_login = ft.TextField(label="Usuario", width=300)
    txt_pass_login = ft.TextField(label="Contraseña", password=True, width=300)
    btn_login = ft.ElevatedButton("ENTRAR", on_click=verificar_login, bgcolor="purple", color="white", width=300)
    lbl_error_login = ft.Text("", color="red")

    vista_login = ft.Container(alignment=ft.alignment.center, padding=50, content=ft.Column([
        ft.Icon(ft.Icons.LOCK, size=50, color="purple"),
        ft.Text("Beauty POS", size=30), 
        txt_user_login, txt_pass_login, btn_login, lbl_error_login
    ], horizontal_alignment="center"))

    # ==============================================================================
    # 2. CONSTRUCTOR DEL SISTEMA
    # ==============================================================================
    def construir_interfaz():
        
        # --- A. GENERADOR DE PDF ---
        def generar_ticket_pdf(nombre_prod, precio, telefono):
            try:
                if not os.path.exists("tickets"): os.makedirs("tickets")
                nombre_archivo = f"tickets/ticket_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                c = canvas.Canvas(nombre_archivo, pagesize=A4)
                
                c.setFont("Helvetica-Bold", 16); c.drawString(2*cm, 28*cm, "BEAUTY POS - TICKET DE VENTA")
                c.setFont("Helvetica", 12)
                c.drawString(2*cm, 27*cm, f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                c.drawString(2*cm, 26.5*cm, f"Vendedor: {usuario_actual_nombre.upper()}")
                c.drawString(2*cm, 26*cm, f"Cliente: {telefono if telefono else 'General'}")
                c.line(2*cm, 25.5*cm, 19*cm, 25.5*cm) 
                
                c.setFont("Helvetica-Bold", 14)
                c.drawString(2*cm, 24.5*cm, "PRODUCTO"); c.drawString(15*cm, 24.5*cm, "PRECIO")
                c.setFont("Helvetica", 12)
                c.drawString(2*cm, 23.5*cm, nombre_prod); c.drawString(15*cm, 23.5*cm, f"${precio:,.2f}")
                c.line(2*cm, 22.5*cm, 19*cm, 22.5*cm) 
                
                c.setFont("Helvetica-Bold", 16); c.drawString(12*cm, 21.5*cm, f"TOTAL: ${precio:,.2f}")
                c.setFont("Helvetica-Oblique", 10); c.drawString(2*cm, 20*cm, "¡Gracias por su compra!")
                c.save()
                os.startfile(os.path.abspath(nombre_archivo)) 
            except: pass

        # --- B. LÓGICA WHATSAPP (NUEVO) ---
        def enviar_whatsapp(telefono, nombre_prod, precio):
            if not telefono: return
            
            # Limpieza del número
            tel_limpio = telefono.strip().replace(" ", "").replace("-", "")
            
            # Si es número de 10 dígitos (México), agregamos 52
            if len(tel_limpio) == 10:
                tel_limpio = "52" + tel_limpio
            
            # Crear el mensaje
            mensaje = f"Hola! Gracias por tu compra en Beauty POS.\n\n✅ Producto: {nombre_prod}\n💰 Total: ${precio:,.2f}\n\n¡Esperamos verte pronto!"
            
            # Codificar mensaje para URL (cambia espacios por %20, etc)
            mensaje_codificado = urllib.parse.quote(mensaje)
            
            # Abrir navegador
            url = f"https://wa.me/{tel_limpio}?text={mensaje_codificado}"
            webbrowser.open(url)

        # --- C. LÓGICA VENTA ---
        txt_telefono_directo = ft.TextField(label="Teléfono Cliente (WhatsApp)", keyboard_type=ft.KeyboardType.PHONE, width=300, visible=False, prefix_icon=ft.Icons.PHONE)

        def ejecutar_venta_directa(e):
            print("--> INICIANDO COBRO...")
            global usuario_actual_id, id_variante_seleccionada, precio_venta_seleccionado, nombre_producto_seleccionado
            
            if id_variante_seleccionada is None: return
            
            btn_vender_pos.text = "PROCESANDO..."; btn_vender_pos.disabled = True; page.update()
            telefono = txt_telefono_directo.value.strip()

            try:
                conn = psycopg2.connect(URL_CONEXION); cursor = conn.cursor()
                cursor.execute("UPDATE inventario SET stock_actual = stock_actual - 1 WHERE variante_id = %s AND stock_actual > 0 RETURNING stock_actual", (id_variante_seleccionada,))
                res = cursor.fetchone()
                
                if res:
                    stock_restante = res[0]
                    cursor.execute("INSERT INTO ventas (usuario_id, variante_id, precio_venta, cliente_telefono) VALUES (%s, %s, %s, %s)", 
                                   (usuario_actual_id, id_variante_seleccionada, precio_venta_seleccionado, telefono))
                    conn.commit()
                    
                    # 1. PDF
                    generar_ticket_pdf(nombre_producto_seleccionado, precio_venta_seleccionado, telefono)
                    
                    # 2. WHATSAPP (Si puso teléfono)
                    if telefono:
                        enviar_whatsapp(telefono, nombre_producto_seleccionado, precio_venta_seleccionado)
                    
                    page.snack_bar = ft.SnackBar(ft.Text(f"✅ VENTA OK. Quedan: {stock_restante}"), bgcolor="green"); page.snack_bar.open = True
                    
                    # Limpieza
                    txt_busqueda_pos.value = ""; txt_busqueda_pos.focus(); info_pos.value = ""; btn_vender_pos.visible = False; txt_telefono_directo.visible = False; txt_telefono_directo.value = ""; id_variante_seleccionada = None
                    if usuario_actual_rol in ["gerente", "admin"]: cargar_reporte_dia(); cargar_inv()
                else:
                    page.snack_bar = ft.SnackBar(ft.Text("⚠️ Error: Ya no hay stock"), bgcolor="red"); page.snack_bar.open = True
                conn.close()
            except Exception as err: 
                page.snack_bar = ft.SnackBar(ft.Text(f"Error: {err}"), bgcolor="red"); page.snack_bar.open = True
            
            btn_vender_pos.text = "COBRAR, TICKET Y WHATSAPP"; page.update()

        # --- D. BUSCADOR ---
        def buscar_producto_pos(e):
            global id_variante_seleccionada, precio_venta_seleccionado, nombre_producto_seleccionado
            tono = txt_busqueda_pos.value; id_variante_seleccionada = None 
            if not tono: return
            try:
                conn = psycopg2.connect(URL_CONEXION); cursor = conn.cursor()
                query = """SELECT v.id, p.nombre, v.nombre_variante, v.precio_venta, i.stock_actual 
                           FROM variantes v JOIN productos p ON v.producto_id = p.id 
                           JOIN inventario i ON v.id = i.variante_id WHERE v.numero_tono = %s"""
                cursor.execute(query, (tono,)); res = cursor.fetchone(); conn.close()
                if res:
                    id_variante_seleccionada = res[0]; nombre_producto_seleccionado = f"{res[1]} {res[2]}"; precio_venta_seleccionado = float(res[3]); stock = res[4]
                    info_pos.value = f"{res[1]} - {res[2]}\nPrecio: ${res[3]}\nStock: {stock}"
                    info_pos.color = "black" if stock > 0 else "red"
                    if stock > 0:
                        btn_vender_pos.disabled = False; btn_vender_pos.visible = True; txt_telefono_directo.visible = True
                    else:
                        btn_vender_pos.disabled = True; btn_vender_pos.visible = True; txt_telefono_directo.visible = False; info_pos.value += " (AGOTADO)"
                else:
                    info_pos.value = "❌ No encontrado"; btn_vender_pos.visible = False; txt_telefono_directo.visible = False
            except Exception as err: info_pos.value = f"Error: {err}"
            page.update()

        txt_busqueda_pos = ft.TextField(label="Buscar Tono (ej. 7.0)", on_submit=buscar_producto_pos, text_size=20)
        info_pos = ft.Text("", size=20)
        btn_vender_pos = ft.ElevatedButton("COBRAR, TICKET Y WHATSAPP", bgcolor="green", color="white", visible=False, on_click=ejecutar_venta_directa, height=60)
        
        vista_ventas = ft.Container(padding=30, content=ft.Column([
            ft.Text("Punto de Venta", size=30), txt_busqueda_pos, ft.ElevatedButton("BUSCAR PRECIO", on_click=buscar_producto_pos), ft.Divider(), info_pos, txt_telefono_directo, btn_vender_pos
        ]))

        # --- E. REPORTES ---
        tabla_reporte = ft.DataTable(columns=[ft.DataColumn(ft.Text("Hora")), ft.DataColumn(ft.Text("Vendedor")), ft.DataColumn(ft.Text("Producto")), ft.DataColumn(ft.Text("Monto"))], rows=[])
        lbl_total_dia = ft.Text("Total: $0.00", size=30, weight="bold", color="green")
        def cargar_reporte_dia():
            tabla_reporte.rows.clear(); total = 0.0
            try:
                conn = psycopg2.connect(URL_CONEXION); cursor = conn.cursor()
                query = """SELECT TO_CHAR(ven.fecha, 'HH24:MI'), u.username, p.nombre, v.numero_tono, ven.precio_venta 
                           FROM ventas ven JOIN usuarios u ON ven.usuario_id = u.id 
                           JOIN variantes v ON ven.variante_id = v.id JOIN productos p ON v.producto_id = p.id 
                           WHERE DATE(ven.fecha) = CURRENT_DATE ORDER BY ven.fecha DESC"""
                cursor.execute(query); filas = cursor.fetchall(); conn.close()
                for f in filas:
                    total += float(f[4])
                    tabla_reporte.rows.append(ft.DataRow(cells=[ft.DataCell(ft.Text(f[0])), ft.DataCell(ft.Text(f[1])), ft.DataCell(ft.Text(f"{f[2]} ({f[3]})")), ft.DataCell(ft.Text(f"${f[4]}"))]))
                lbl_total_dia.value = f"Total Hoy: ${total:,.2f}"
            except: pass
            page.update()
        vista_reportes = ft.Container(padding=30, content=ft.Column([ft.Text("Corte de Caja", size=30), ft.ElevatedButton("ACTUALIZAR", icon=ft.Icons.REFRESH, on_click=lambda e: cargar_reporte_dia()), lbl_total_dia, ft.Column([tabla_reporte], scroll="always", height=400)]))

        # --- F. AGREGAR PRODUCTOS ---
        txt_nueva_marca = ft.TextField(label="Nombre Nueva Marca", width=250)
        def crear_marca(e):
            if not txt_nueva_marca.value: return
            try:
                conn = psycopg2.connect(URL_CONEXION); cur = conn.cursor()
                cur.execute("INSERT INTO productos (nombre, marca_id, categoria_id) VALUES (%s, (SELECT id FROM marcas LIMIT 1), (SELECT id FROM categorias LIMIT 1))", (txt_nueva_marca.value,))
                conn.commit(); conn.close()
                page.snack_bar = ft.SnackBar(ft.Text("Marca Creada"), bgcolor="green"); page.snack_bar.open=True; txt_nueva_marca.value = ""; cargar_dd_prods()
            except: pass
        dd_linea = ft.Dropdown(label="Selecciona Marca Existente", width=400)
        txt_sku = ft.TextField(label="SKU", width=200); txt_tono_add = ft.TextField(label="Tono", width=200)
        txt_precio_add = ft.TextField(label="Precio", width=200, keyboard_type=ft.KeyboardType.NUMBER)
        txt_stock_add = ft.TextField(label="Stock", width=200, keyboard_type=ft.KeyboardType.NUMBER)
        def cargar_dd_prods():
            try:
                conn = psycopg2.connect(URL_CONEXION); cur = conn.cursor()
                cur.execute("SELECT id, nombre FROM productos ORDER BY nombre"); dd_linea.options = [ft.dropdown.Option(str(x[0]), x[1]) for x in cur.fetchall()]; conn.close(); page.update()
            except: pass
        def guardar_prod(e):
            if not dd_linea.value: return
            try:
                conn = psycopg2.connect(URL_CONEXION); cur = conn.cursor()
                cur.execute("INSERT INTO variantes (producto_id, sku, nombre_variante, numero_tono, precio_venta, precio_compra) VALUES (%s, %s, %s, %s, %s, 0) RETURNING id", 
                            (dd_linea.value, txt_sku.value, f"Tono {txt_tono_add.value}", txt_tono_add.value, float(txt_precio_add.value)))
                nid = cur.fetchone()[0]
                cur.execute("INSERT INTO inventario (variante_id, stock_actual) VALUES (%s, %s)", (nid, int(txt_stock_add.value)))
                conn.commit(); conn.close()
                page.snack_bar = ft.SnackBar(ft.Text("✅ Producto Agregado"), bgcolor="green"); page.snack_bar.open=True
                txt_sku.value=""; txt_tono_add.value=""; txt_stock_add.value=""; cargar_inv()
            except Exception as e: page.snack_bar = ft.SnackBar(ft.Text(f"Error: {e}"), bgcolor="red"); page.snack_bar.open=True
            page.update()
        vista_agregar = ft.Container(padding=30, content=ft.Column([ft.Text("Alta Productos", size=30), ft.Row([txt_nueva_marca, ft.ElevatedButton("CREAR MARCA", on_click=crear_marca)]), ft.Divider(), dd_linea, ft.Row([txt_sku, txt_tono_add]), ft.Row([txt_precio_add, txt_stock_add]), ft.Container(height=20), ft.ElevatedButton("GUARDAR PRODUCTO", on_click=guardar_prod, bgcolor="blue", color="white")]))

        # --- G. INVENTARIO ---
        col_inv = ft.Column(scroll="always", height=400)
        def borrar_item(id_v):
            try:
                conn=psycopg2.connect(URL_CONEXION); c=conn.cursor()
                c.execute("DELETE FROM inventario WHERE variante_id=%s",(id_v,)); c.execute("DELETE FROM variantes WHERE id=%s",(id_v,))
                conn.commit(); conn.close(); cargar_inv()
            except: pass
        def cargar_inv():
            col_inv.controls.clear()
            try:
                conn = psycopg2.connect(URL_CONEXION); cur = conn.cursor()
                cur.execute("SELECT v.id, p.nombre, v.numero_tono, i.stock_actual FROM variantes v JOIN productos p ON v.producto_id=p.id LEFT JOIN inventario i ON v.id=i.variante_id ORDER BY p.nombre")
                for f in cur.fetchall():
                    id_v, nom, ton, stk = f
                    col_inv.controls.append(ft.Container(padding=10, border=ft.border.all(1,"grey"), content=ft.Row([ft.Text(f"{nom} - {ton}: {stk} pzas"), ft.IconButton(ft.Icons.DELETE, icon_color="red", on_click=lambda e, x=id_v: borrar_item(x))], alignment="spaceBetween")))
                conn.close()
            except: pass
            page.update()
        vista_inv = ft.Container(padding=30, content=ft.Column([ft.Text("Inventario", size=30), ft.ElevatedButton("REFRESCAR", on_click=lambda e: cargar_inv()), col_inv]))

        # --- H. USUARIOS ---
        txt_new_u = ft.TextField(label="Nuevo Usuario"); txt_new_p = ft.TextField(label="Contraseña", password=True)
        dd_rol_user = ft.Dropdown(label="Rol", options=[ft.dropdown.Option("vendedor"), ft.dropdown.Option("gerente"), ft.dropdown.Option("admin")], value="vendedor")
        lbl_res_user = ft.Text("")
        col_lista_usuarios = ft.Column(scroll="always", height=300)
        def cargar_lista_usuarios():
            col_lista_usuarios.controls.clear()
            try:
                conn = psycopg2.connect(URL_CONEXION); cur = conn.cursor()
                cur.execute("SELECT id, username, rol FROM usuarios ORDER BY username")
                for u in cur.fetchall():
                    uid, uname, urol = u
                    btn_del = ft.IconButton(ft.Icons.DELETE, icon_color="red", on_click=lambda e, x=uid: eliminar_usuario(x))
                    col_lista_usuarios.controls.append(ft.Container(padding=10, border=ft.border.only(bottom=ft.border.BorderSide(1,"grey")), content=ft.Row([ft.Text(f"{uname} ({urol})", size=16), ft.Container(expand=True), btn_del])))
                conn.close()
            except: pass
            page.update()
        def eliminar_usuario(id_borrar):
            if id_borrar == usuario_actual_id: page.snack_bar = ft.SnackBar(ft.Text("⚠️ No puedes borrar tu cuenta"), bgcolor="orange"); page.snack_bar.open = True; page.update(); return
            try:
                conn = psycopg2.connect(URL_CONEXION); cur = conn.cursor()
                cur.execute("DELETE FROM usuarios WHERE id = %s", (id_borrar,))
                conn.commit(); conn.close()
                page.snack_bar = ft.SnackBar(ft.Text("🗑️ Eliminado"), bgcolor="blue"); page.snack_bar.open = True; cargar_lista_usuarios()
            except Exception as e: page.snack_bar = ft.SnackBar(ft.Text(f"Error: {e}"), bgcolor="red"); page.snack_bar.open = True; page.update()
        def crear_usuario_click(e):
            u = txt_new_u.value; p = txt_new_p.value; r = dd_rol_user.value
            if not u or not p: return
            try:
                h = bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()
                conn = psycopg2.connect(URL_CONEXION); cur = conn.cursor()
                cur.execute("INSERT INTO usuarios (username, password_hash, rol) VALUES (%s, %s, %s)", (u, h, r))
                conn.commit(); conn.close()
                lbl_res_user.value = f"✅ Creado: {u}"; lbl_res_user.color="green"; txt_new_u.value=""; txt_new_p.value=""; cargar_lista_usuarios()
            except Exception as err: lbl_res_user.value = f"Error: {err}"; lbl_res_user.color="red"
            page.update()
        vista_admin = ft.Container(padding=30, content=ft.Column([
            ft.Text("Gestión Usuarios", size=30), ft.Row([txt_new_u, txt_new_p, dd_rol_user]), 
            ft.ElevatedButton("CREAR USUARIO", on_click=crear_usuario_click), lbl_res_user,
            ft.Divider(), ft.Text("Lista de Usuarios", weight="bold"), col_lista_usuarios
        ]))

        # --- ARMADO FINAL ---
        tabs = []
        tabs.append(ft.Tab(text="Ventas", icon=ft.Icons.MONEY, content=vista_ventas))
        if usuario_actual_rol in ["gerente", "admin"]:
            tabs.append(ft.Tab(text="Reportes", icon=ft.Icons.ASSESSMENT, content=vista_reportes))
            tabs.append(ft.Tab(text="Agregar", icon=ft.Icons.ADD_BOX, content=vista_agregar))
            tabs.append(ft.Tab(text="Inventario", icon=ft.Icons.LIST, content=vista_inv))
            tabs.append(ft.Tab(text="Usuarios", icon=ft.Icons.ADMIN_PANEL_SETTINGS, content=vista_admin))
            cargar_reporte_dia(); cargar_dd_prods(); cargar_inv(); cargar_lista_usuarios()
        
        t = ft.Tabs(tabs=tabs, expand=1)
        btn_salir = ft.IconButton(ft.Icons.EXIT_TO_APP, tooltip="Salir", on_click=lambda e: reiniciar())
        page.add(ft.Row([ft.Text(f"Usuario: {usuario_actual_nombre} ({usuario_actual_rol})", weight="bold"), btn_salir], alignment="spaceBetween"), t)

    def reiniciar():
        global usuario_actual_id; usuario_actual_id = None; page.clean(); page.add(vista_login)

    page.add(vista_login)

ft.app(target=main)
