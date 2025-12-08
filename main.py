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
    page.title = "Beauty POS Móvil"
    # ESTO ES CLAVE PARA CELULAR:
    page.scroll = "auto" # Permite bajar con el dedo
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = "#f5f5f5"
    page.padding = 10 # Menos margen para aprovechar pantalla chica

    # ==========================================
    # 1. LOGIN (Adaptado a móvil)
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
                usuario_actual_rol = str(res[2]).strip().lower()
                page.clean()
                construir_interfaz() 
            else:
                lbl_error_login.value = "❌ Datos incorrectos"
                btn_login.text = "ENTRAR"
        except Exception as err:
            lbl_error_login.value = f"Error: {err}"
            btn_login.text = "ENTRAR"
        page.update()

    # Usamos expand=True en contenedores para que se centren bien
    txt_user_login = ft.TextField(label="Usuario", width=None, expand=True)
    txt_pass_login = ft.TextField(label="Contraseña", password=True, width=None, expand=True)
    btn_login = ft.ElevatedButton("ENTRAR", on_click=verificar_login, bgcolor="purple", color="white", height=50, expand=True)
    lbl_error_login = ft.Text("", color="red")

    vista_login = ft.Container(
        alignment=ft.alignment.center,
        padding=20,
        content=ft.Column([
            ft.Icon(ft.Icons.SPA, size=80, color="purple"),
            ft.Text("Beauty POS", size=30, weight="bold"), 
            ft.Container(height=20), # Espacio
            ft.Row([txt_user_login]), # Fila para que expand funcione
            ft.Row([txt_pass_login]),
            ft.Container(height=10),
            ft.Row([btn_login]),
            lbl_error_login
        ], horizontal_alignment="center")
    )

    # ==========================================
    # 2. SISTEMA PRINCIPAL
    # ==========================================
    def construir_interfaz():
        
        # --- FUNCIONES ---
        def enviar_whatsapp(telefono, nombre_prod, precio):
            if not telefono: return
            tel = telefono.strip().replace(" ", "").replace("-", "")
            if len(tel) == 10: tel = "52" + tel
            msg = f"Hola! Compra en Beauty POS.\nProducto: {nombre_prod}\nTotal: ${precio:,.2f}"
            page.launch_url(f"https://wa.me/{tel}?text={urllib.parse.quote(msg)}")

        def finalizar_venta(e):
            global id_variante_seleccionada, precio_venta_seleccionado
            tel = txt_tel.value.strip()
            btn_cobrar.disabled = True
            page.update()

            try:
                conn = psycopg2.connect(URL_CONEXION); cur = conn.cursor()
                cur.execute("UPDATE inventario SET stock_actual = stock_actual - 1 WHERE variante_id = %s AND stock_actual > 0 RETURNING stock_actual", (id_variante_seleccionada,))
                res = cur.fetchone()
                
                if res:
                    cur.execute("INSERT INTO ventas (usuario_id, variante_id, precio_venta, cliente_telefono) VALUES (%s, %s, %s, %s)", 
                                (usuario_actual_id, id_variante_seleccionada, precio_venta_seleccionado, tel))
                    conn.commit()
                    
                    if tel: enviar_whatsapp(tel, nombre_producto_seleccionado, precio_venta_seleccionado)
                    
                    page.snack_bar = ft.SnackBar(ft.Text(f"✅ Venta OK"), bgcolor="green")
                    page.snack_bar.open = True
                    
                    # Limpiar
                    txt_busqueda.value=""; info_prod.value=""; btn_cobrar.visible=False; txt_tel.visible=False; txt_tel.value=""
                    if usuario_actual_rol in ["gerente", "admin"]: cargar_reporte()
                else:
                    page.snack_bar = ft.SnackBar(ft.Text("⚠️ Sin Stock"), bgcolor="red"); page.snack_bar.open = True
                conn.close()
            except Exception as err: print(err)
            
            btn_cobrar.disabled = False
            btn_cobrar.text = "COBRAR"
            page.update()

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
                    if r[4] > 0: 
                        btn_cobrar.visible=True; txt_tel.visible=True; btn_cobrar.disabled=False
                    else: 
                        info_prod.value += " (AGOTADO)"; btn_cobrar.visible=False
                else: info_prod.value = "No encontrado"; btn_cobrar.visible=False
            except: pass
            page.update()

        # --- VISTA VENDER (Diseño Móvil) ---
        txt_busqueda = ft.TextField(label="Buscar Tono", on_submit=buscar_prod, text_size=20, expand=True)
        info_prod = ft.Text("", size=18, weight="bold", text_align="center")
        txt_tel = ft.TextField(label="WhatsApp Cliente", keyboard_type=ft.KeyboardType.PHONE, visible=False)
        btn_cobrar = ft.ElevatedButton("COBRAR", bgcolor="green", color="white", visible=False, on_click=finalizar_venta, height=60, width=None)
        
        vista_ventas = ft.Container(
            padding=10,
            content=ft.Column([
                ft.Text("Punto de Venta", size=25, weight="bold"),
                ft.Row([txt_busqueda, ft.IconButton(ft.Icons.SEARCH, on_click=buscar_prod, icon_color="purple")]),
                ft.Divider(),
                info_prod,
                ft.Container(height=10),
                txt_tel,
                ft.Container(height=10),
                ft.Row([btn_cobrar], alignment="center") # Botón centrado
            ])
        )

        # --- VISTA REPORTES (Con Scroll Horizontal para que no se corte) ---
        col_reporte = ft.Column(scroll="always") # Scroll vertical
        
        def cargar_reporte():
            col_reporte.controls.clear()
            try:
                conn = psycopg2.connect(URL_CONEXION); c=conn.cursor()
                c.execute("SELECT TO_CHAR(fecha, 'HH24:MI'), precio_venta, cliente_telefono, p.nombre FROM ventas JOIN variantes v ON ventas.variante_id = v.id JOIN productos p ON v.producto_id = p.id WHERE DATE(fecha)=CURRENT_DATE ORDER BY fecha DESC")
                total = 0
                for r in c.fetchall():
                    total += float(r[1])
                    # Tarjeta simple para móvil en lugar de tabla ancha
                    col_reporte.controls.append(
                        ft.Container(
                            padding=10,
                            border=ft.border.only(bottom=ft.border.BorderSide(1, "grey")),
                            content=ft.Column([
                                ft.Row([
                                    ft.Text(f"{r[0]} - {r[3]}", weight="bold"),
                                    ft.Text(f"${r[1]}", color="green", weight="bold")
                                ], alignment="spaceBetween"),
                                ft.Text(f"Cliente: {r[2] if r[2] else 'General'}", size=12, color="grey")
                            ])
                        )
                    )
                col_reporte.controls.insert(0, ft.Container(
                    bgcolor="green", padding=15, border_radius=10,
                    content=ft.Row([
                        ft.Text("Total Hoy:", color="white", size=18),
                        ft.Text(f"${total:,.2f}", color="white", size=22, weight="bold")
                    ], alignment="spaceBetween")
                ))
                conn.close()
            except: pass
            page.update()
        
        vista_reportes = ft.Container(padding=10, content=ft.Column([
            ft.Text("Corte de Caja", size=25),
            ft.ElevatedButton("Actualizar Lista", icon=ft.Icons.REFRESH, on_click=lambda e: cargar_reporte()),
            ft.Divider(),
            col_reporte
        ]))

        # --- VISTA AGREGAR ---
        txt_new_sku = ft.TextField(label="SKU", expand=True)
        txt_new_tono = ft.TextField(label="Tono", expand=True)
        txt_new_precio = ft.TextField(label="Precio", keyboard_type="number", expand=True)
        txt_new_stock = ft.TextField(label="Stock", keyboard_type="number", expand=True)
        
        def guardar_nuevo(e):
            page.snack_bar = ft.SnackBar(ft.Text("Función disponible en PC"), bgcolor="orange"); page.snack_bar.open=True; page.update()

        vista_agregar = ft.Container(padding=10, content=ft.Column([
            ft.Text("Nuevo Producto", size=25),
            ft.Row([txt_new_sku, txt_new_tono]),
            ft.Row([txt_new_precio, txt_new_stock]),
            ft.ElevatedButton("GUARDAR (Solo PC)", on_click=guardar_nuevo)
        ]))

        # --- VISTA INVENTARIO (Simple) ---
        col_inv = ft.Column(scroll="always", expand=True)
        def cargar_inv():
            col_inv.controls.clear()
            try:
                conn = psycopg2.connect(URL_CONEXION); c=conn.cursor()
                c.execute("SELECT p.nombre, v.numero_tono, i.stock_actual FROM variantes v JOIN productos p ON v.producto_id=p.id JOIN inventario i ON v.id=i.variante_id ORDER BY p.nombre")
                for r in c.fetchall():
                    col_inv.controls.append(
                        ft.Container(
                            padding=10, border=ft.border.only(bottom=ft.border.BorderSide(1, "#eeeeee")),
                            content=ft.Row([
                                ft.Text(f"{r[0]} {r[1]}"),
                                ft.Text(f"{r[2]} pzas", color="blue" if r[2]>5 else "red")
                            ], alignment="spaceBetween")
                        )
                    )
                conn.close()
            except: pass
            page.update()
        
        vista_inv = ft.Container(padding=10, content=ft.Column([
            ft.Text("Inventario", size=25), 
            ft.ElevatedButton("Refrescar", on_click=lambda e: cargar_inv()), 
            col_inv
        ]))

        # --- VISTA USUARIOS (Simple) ---
        col_usuarios = ft.Column(scroll="always")
        def cargar_usuarios():
            col_usuarios.controls.clear()
            try:
                conn = psycopg2.connect(URL_CONEXION); c=conn.cursor()
                c.execute("SELECT username, rol FROM usuarios")
                for r in c.fetchall():
                    col_usuarios.controls.append(ft.Text(f"👤 {r[0]} ({r[1]})", size=16))
                conn.close()
            except: pass
            page.update()
        
        vista_users = ft.Container(padding=10, content=ft.Column([
            ft.Text("Usuarios", size=25), 
            ft.ElevatedButton("Refrescar", on_click=lambda e: cargar_usuarios()), 
            col_usuarios
        ]))

        # --- ARMADO DE PESTAÑAS (SEGÚN ROL) ---
        tabs = [ft.Tab(text="Vender", icon=ft.Icons.MONEY, content=vista_ventas)]
        
        rol_seguro = usuario_actual_rol.lower().strip()
        
        if rol_seguro in ["admin", "gerente", "gerente de tienda", "administrador"]:
            tabs.append(ft.Tab(text="Corte", icon=ft.Icons.ASSESSMENT, content=vista_reportes))
            tabs.append(ft.Tab(text="Stock", icon=ft.Icons.LIST, content=vista_inv))
            # Ocultamos "Agregar" en celular para no saturar, o la dejamos simple
            # tabs.append(ft.Tab(text="Agregar", icon=ft.Icons.ADD, content=vista_agregar))
            cargar_reporte(); cargar_inv()

        if "admin" in rol_seguro:
            tabs.append(ft.Tab(text="Users", icon=ft.Icons.PEOPLE, content=vista_users))
            cargar_usuarios()

        def cerrar_sesion(e):
            global usuario_actual_id; usuario_actual_id = None; page.clean(); page.add(vista_login)

        page.add(
            ft.Row([
                ft.Text(f"Hola, {usuario_actual_nombre}", size=16, weight="bold"), 
                ft.IconButton(ft.Icons.LOGOUT, on_click=cerrar_sesion)
            ], alignment="spaceBetween"),
            ft.Tabs(tabs=tabs, expand=1, scrollable=True) # Scrollable=True permite muchas pestañas en cel
        )

    page.add(vista_login)

ft.app(target=main, view=ft.AppView.WEB_BROWSER, port=int(os.environ.get("PORT", 8080)), host="0.0.0.0")
