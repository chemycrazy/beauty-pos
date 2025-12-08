import flet as ft
import psycopg2
import bcrypt
import os
import urllib.parse
from datetime import datetime
import platform

# --- CONFIGURACIÓN ---
#⚠️ PON TU CONTRASEÑA AQUÍ
URL_CONEXION = "postgresql://postgres.swavrpqagshyddhjaipf:R57667115#g@aws-0-us-west-2.pooler.supabase.com:6543/postgres"

# VARIABLES GLOBALES
usuario_actual_id = None
usuario_actual_nombre = ""
usuario_actual_rol = ""
id_variante_seleccionada = None 
precio_venta_seleccionado = 0.0
nombre_producto_seleccionado = "" 

def main(page: ft.Page):
    page.title = "Beauty POS Web"
    page.scroll = "adaptive"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = "#f5f5f5"

    # ==========================================
    # 1. LOGIN
    # ==========================================
    def verificar_login(e):
        global usuario_actual_id, usuario_actual_nombre, usuario_actual_rol
        user = txt_user_login.value
        pwd = txt_pass_login.value
        btn_login.text = "Entrando..."
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
                # Normalizamos el rol (minúsculas y sin espacios)
                usuario_actual_rol = str(res[2]).strip().lower()
                
                print(f"DEBUG: Rol detectado: {usuario_actual_rol}") # Para ver en logs
                
                page.clean()
                construir_interfaz() 
            else:
                lbl_error_login.value = "❌ Datos incorrectos"
                btn_login.text = "ENTRAR"
        except Exception as err:
            lbl_error_login.value = f"Error: {err}"
            btn_login.text = "ENTRAR"
        page.update()

    txt_user_login = ft.TextField(label="Usuario", width=300)
    txt_pass_login = ft.TextField(label="Contraseña", password=True, width=300)
    btn_login = ft.ElevatedButton("ENTRAR", on_click=verificar_login, bgcolor="purple", color="white", width=300)
    lbl_error_login = ft.Text("", color="red")

    vista_login = ft.Container(alignment=ft.alignment.center, padding=20, content=ft.Column([
        ft.Icon(ft.Icons.SPA, size=60, color="purple"),
        ft.Text("Beauty POS", size=30, weight="bold"), 
        txt_user_login, txt_pass_login, btn_login, lbl_error_login
    ], horizontal_alignment="center"))

    # ==========================================
    # 2. SISTEMA PRINCIPAL
    # ==========================================
    def construir_interfaz():
        
        # --- FUNCIÓN CERRAR SESIÓN ---
        def cerrar_sesion(e):
            global usuario_actual_id, usuario_actual_nombre, usuario_actual_rol
            usuario_actual_id = None
            usuario_actual_nombre = ""
            usuario_actual_rol = ""
            page.clean()
            page.add(vista_login)
            page.update()

        # --- FUNCIONES AUXILIARES VENTA ---
        def enviar_whatsapp(telefono, nombre_prod, precio):
            if not telefono: return
            tel = telefono.strip().replace(" ", "").replace("-", "")
            if len(tel) == 10: tel = "52" + tel
            msg = f"Hola! Compra en Beauty POS.\nProducto: {nombre_prod}\nTotal: ${precio:,.2f}"
            page.launch_url(f"https://wa.me/{tel}?text={urllib.parse.quote(msg)}")

        def finalizar_venta(e):
            global id_variante_seleccionada, precio_venta_seleccionado
            tel = txt_tel.value.strip()
            btn_cobrar.disabled = True; page.update()

            try:
                conn = psycopg2.connect(URL_CONEXION); cur = conn.cursor()
                cur.execute("UPDATE inventario SET stock_actual = stock_actual - 1 WHERE variante_id = %s AND stock_actual > 0 RETURNING stock_actual", (id_variante_seleccionada,))
                res = cur.fetchone()
                if res:
                    cur.execute("INSERT INTO ventas (usuario_id, variante_id, precio_venta, cliente_telefono) VALUES (%s, %s, %s, %s)", 
                                (usuario_actual_id, id_variante_seleccionada, precio_venta_seleccionado, tel))
                    conn.commit()
                    if tel: enviar_whatsapp(tel, nombre_producto_seleccionado, precio_venta_seleccionado)
                    page.snack_bar = ft.SnackBar(ft.Text(f"✅ Venta OK. Restan: {res[0]}"), bgcolor="green"); page.snack_bar.open = True
                    txt_busqueda.value=""; info_prod.value=""; btn_cobrar.visible=False; txt_tel.visible=False; txt_tel.value=""
                    if usuario_actual_rol in ["gerente", "admin", "gerente de tienda"]: 
                        cargar_reporte(); cargar_inv()
                else:
                    page.snack_bar = ft.SnackBar(ft.Text("⚠️ Sin Stock"), bgcolor="red"); page.snack_bar.open = True
                conn.close()
            except Exception as err: print(err)
            btn_cobrar.disabled = False; page.update()

        def buscar_prod(e):
            global id_variante_seleccionada, precio_venta_seleccionado, nombre_producto_seleccionado
            tono = txt_busqueda.value; id_variante_seleccionada = None
            if not tono: return
            try:
                conn = psycopg2.connect(URL_CONEXION); c = conn.cursor()
                c.execute("SELECT v.id, p.nombre, v.nombre_variante, v.precio_venta, i.stock_actual FROM variantes v JOIN productos p ON v.producto_id=p.id JOIN inventario i ON v.id=i.variante_id WHERE v.numero_tono=%s", (tono,))
                r = c.fetchone(); conn.close()
                if r:
                    id_variante_seleccionada=r[0]; nombre_producto_seleccionado=f"{r[1]} {r[2]}"; precio_venta_seleccionado=float(r[3])
                    info_prod.value = f"{r[1]} {r[2]}\nPrecio: ${r[3]}\nStock: {r[4]}"
                    if r[4] > 0: btn_cobrar.visible=True; txt_tel.visible=True; btn_cobrar.disabled=False
                    else: info_prod.value += " (AGOTADO)"; btn_cobrar.visible=False
                else: info_prod.value = "No encontrado"; btn_cobrar.visible=False
            except: pass
            page.update()

        # --- VISTAS (PESTAÑAS) ---

        # 1. VENDER
        txt_busqueda = ft.TextField(label="Buscar Tono", on_submit=buscar_prod)
        info_prod = ft.Text("", size=18, weight="bold")
        txt_tel = ft.TextField(label="WhatsApp Cliente", keyboard_type=ft.KeyboardType.PHONE, visible=False)
        btn_cobrar = ft.ElevatedButton("COBRAR", bgcolor="green", color="white", visible=False, on_click=finalizar_venta, height=50)
        vista_ventas = ft.Column([ft.Text("Punto de Venta", size=25), txt_busqueda, ft.ElevatedButton("BUSCAR", on_click=buscar_prod), ft.Divider(), info_prod, txt_tel, btn_cobrar])

        # 2. REPORTES
        col_reporte = ft.Column(scroll="always", expand=True)
        def cargar_reporte():
            col_reporte.controls.clear()
            try:
                conn = psycopg2.connect(URL_CONEXION); c=conn.cursor()
                c.execute("SELECT TO_CHAR(fecha, 'HH24:MI'), precio_venta, cliente_telefono FROM ventas WHERE DATE(fecha)=CURRENT_DATE ORDER BY fecha DESC")
                total = 0
                for r in c.fetchall():
                    total += float(r[1])
                    col_reporte.controls.append(ft.Text(f"{r[0]} - ${r[1]} (Tel: {r[2]})"))
                col_reporte.controls.insert(0, ft.Text(f"Total Hoy: ${total:,.2f}", size=20, weight="bold", color="green"))
                conn.close()
            except: pass
            page.update()
        vista_reportes = ft.Column([ft.Text("Corte de Caja", size=25), ft.ElevatedButton("Actualizar", on_click=lambda e: cargar_reporte()), col_reporte])

        # 3. AGREGAR
        txt_new_sku = ft.TextField(label="SKU"); txt_new_tono = ft.TextField(label="Tono"); txt_new_precio = ft.TextField(label="Precio", keyboard_type="number"); txt_new_stock = ft.TextField(label="Stock", keyboard_type="number")
        def guardar_nuevo(e):
            page.snack_bar = ft.SnackBar(ft.Text("Función simplificada para web"), bgcolor="orange"); page.snack_bar.open=True; page.update()
        vista_agregar = ft.Column([ft.Text("Nuevo Producto", size=25), txt_new_sku, txt_new_tono, txt_new_precio, txt_new_stock, ft.ElevatedButton("GUARDAR", on_click=guardar_nuevo)])

        # 4. INVENTARIO (Faltaba esta vista)
        col_inv = ft.Column(scroll="always", expand=True)
        def cargar_inv():
            col_inv.controls.clear()
            try:
                conn = psycopg2.connect(URL_CONEXION); c=conn.cursor()
                c.execute("SELECT p.nombre, v.numero_tono, i.stock_actual FROM variantes v JOIN productos p ON v.producto_id=p.id JOIN inventario i ON v.id=i.variante_id ORDER BY p.nombre")
                for r in c.fetchall():
                    col_inv.controls.append(ft.Container(padding=10, border=ft.border.all(1, "grey"), content=ft.Text(f"{r[0]} - {r[1]}: {r[2]} pzas")))
                conn.close()
            except: pass
            page.update()
        vista_inv = ft.Column([ft.Text("Inventario Global", size=25), ft.ElevatedButton("Refrescar", on_click=lambda e: cargar_inv()), col_inv])

        # 5. USUARIOS (Faltaba esta vista)
        col_usuarios = ft.Column(scroll="always", expand=True)
        def cargar_usuarios():
            col_usuarios.controls.clear()
            try:
                conn = psycopg2.connect(URL_CONEXION); c=conn.cursor()
                c.execute("SELECT username, rol FROM usuarios")
                for r in c.fetchall():
                    col_usuarios.controls.append(ft.Text(f"- {r[0]} ({r[1]})"))
                conn.close()
            except: pass
            page.update()
        vista_users = ft.Column([ft.Text("Lista de Usuarios", size=25), ft.ElevatedButton("Refrescar", on_click=lambda e: cargar_usuarios()), col_usuarios])

        # --- ARMADO DE PESTAÑAS (SEGÚN ROL) ---
        tabs = [ft.Tab(text="Vender", icon=ft.Icons.MONEY, content=ft.Container(padding=20, content=vista_ventas))]
        
        # Permitimos variaciones del nombre del rol para que no falle
        roles_permitidos = ["gerente", "admin", "gerente de tienda", "administrador"]
        
        if usuario_actual_rol in roles_permitidos:
            tabs.append(ft.Tab(text="Reportes", icon=ft.Icons.ASSESSMENT, content=ft.Container(padding=20, content=vista_reportes)))
            tabs.append(ft.Tab(text="Inventario", icon=ft.Icons.LIST, content=ft.Container(padding=20, content=vista_inv)))
            tabs.append(ft.Tab(text="Agregar", icon=ft.Icons.ADD_BOX, content=ft.Container(padding=20, content=vista_agregar)))
            # Cargar datos iniciales
            cargar_reporte(); cargar_inv()

        if "admin" in usuario_actual_rol: # Si dice 'admin' o 'administrador'
            tabs.append(ft.Tab(text="Usuarios", icon=ft.Icons.PEOPLE, content=ft.Container(padding=20, content=vista_users)))
            cargar_usuarios()

        page.add(
            ft.Row([
                ft.Text(f"Hola, {usuario_actual_nombre}", weight="bold"), 
                # Botón de SALIR ahora llama a cerrar_sesion
                ft.IconButton(ft.Icons.LOGOUT, on_click=cerrar_sesion, tooltip="Cerrar Sesión")
            ], alignment="spaceBetween"),
            ft.Tabs(tabs=tabs, expand=1)
        )

    page.add(vista_login)

ft.app(target=main, view=ft.AppView.WEB_BROWSER, port=int(os.environ.get("PORT", 8080)), host="0.0.0.0")
