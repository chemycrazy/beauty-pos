import flet as ft
import psycopg2
import bcrypt
import os
import urllib.parse
from datetime import datetime
import platform
import traceback

# --- CONFIGURACIÓN ---
# ⚠️ PON TU CONTRASEÑA AQUÍ
URL_CONEXION = "postgresql://postgres.swavrpqagshyddhjaipf:R57667115#g@aws-0-us-west-2.pooler.supabase.com:6543/postgres"

# VARIABLES GLOBALES
usuario_actual_id = None; usuario_actual_nombre = ""; usuario_actual_rol = ""
id_variante_seleccionada = None; precio_venta_seleccionado = 0.0; nombre_producto_seleccionado = "" 

def main(page: ft.Page):
    page.title = "Beauty POS App"
    page.scroll = None 
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = "#ffffff"
    page.padding = 0
    page.spacing = 0

    # ==========================================
    # 1. LOGIN
    # ==========================================
    def verificar_login(e):
        global usuario_actual_id, usuario_actual_nombre, usuario_actual_rol
        user = txt_user_login.value
        pwd = txt_pass_login.value
        btn_login.text = "Cargando..."
        btn_login.disabled = True
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
                try:
                    construir_interfaz()
                except Exception as ex:
                    page.add(ft.Column([
                        ft.Icon(name="error", color="red", size=50),
                        ft.Text(f"Error cargando App: {ex}", color="red")
                    ]))
                    page.update()
            else:
                lbl_error_login.value = "❌ Datos incorrectos"; btn_login.text = "ENTRAR"; btn_login.disabled = False
        except Exception as err:
            lbl_error_login.value = f"Error: {err}"; btn_login.text = "ENTRAR"; btn_login.disabled = False
        page.update()

    txt_user_login = ft.TextField(label="Usuario", width=300)
    txt_pass_login = ft.TextField(label="Contraseña", password=True, width=300)
    btn_login = ft.ElevatedButton("ENTRAR", on_click=verificar_login, bgcolor="purple", color="white", width=300, height=50)
    lbl_error_login = ft.Text("", color="red")

    vista_login = ft.Container(
        alignment=ft.alignment.center, padding=20,
        content=ft.Column([
            ft.Container(height=50),
            ft.Icon(name="spa", size=80, color="purple"),
            ft.Text("Beauty POS", size=30, weight="bold"), 
            ft.Container(height=30),
            txt_user_login, txt_pass_login, 
            ft.Container(height=20),
            btn_login, lbl_error_login
        ], horizontal_alignment="center", scroll="auto")
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
            btn_cobrar.disabled = True; page.update()
            try:
                conn = psycopg2.connect(URL_CONEXION); cur = conn.cursor()
                cur.execute("UPDATE inventario SET stock_actual = stock_actual - 1 WHERE variante_id = %s AND stock_actual > 0 RETURNING stock_actual", (id_variante_seleccionada,))
                res = cur.fetchone()
                if res:
                    cur.execute("INSERT INTO ventas (usuario_id, variante_id, precio_venta, cliente_telefono) VALUES (%s, %s, %s, %s)", (usuario_actual_id, id_variante_seleccionada, precio_venta_seleccionado, tel))
                    conn.commit()
                    if tel: enviar_whatsapp(tel, nombre_producto_seleccionado, precio_venta_seleccionado)
                    page.snack_bar = ft.SnackBar(ft.Text("✅ Venta OK"), bgcolor="green"); page.snack_bar.open=True
                    txt_busqueda.value=""; info_prod.value=""; btn_cobrar.visible=False; txt_tel.visible=False; txt_tel.value=""
                    if usuario_actual_rol in ["gerente", "admin", "gerente de tienda"]: cargar_reporte()
                else: page.snack_bar = ft.SnackBar(ft.Text("⚠️ Sin Stock"), bgcolor="red"); page.snack_bar.open=True
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

        # --- VISTAS ---
        txt_busqueda = ft.TextField(label="Buscar Tono", on_submit=buscar_prod)
        info_prod = ft.Text("", size=18, weight="bold")
        txt_tel = ft.TextField(label="WhatsApp Cliente", keyboard_type=ft.KeyboardType.PHONE, visible=False)
        btn_cobrar = ft.ElevatedButton("COBRAR", bgcolor="green", color="white", visible=False, on_click=finalizar_venta, height=50)
        
        vista_ventas = ft.ListView(expand=True, padding=20, spacing=15, controls=[
            ft.Text("Punto de Venta", size=25, weight="bold"),
            ft.Row([txt_busqueda, ft.IconButton(icon="search", on_click=buscar_prod, icon_color="purple")]),
            ft.Divider(), info_prod, txt_tel, btn_cobrar
        ])

        col_reporte = ft.Column()
        def cargar_reporte():
            col_reporte.controls.clear()
            try:
                conn = psycopg2.connect(URL_CONEXION); c=conn.cursor()
                # CONSULTA CORREGIDA (ventas.precio_venta)
                c.execute("SELECT TO_CHAR(ventas.fecha, 'HH24:MI'), ventas.precio_venta, ventas.cliente_telefono, p.nombre FROM ventas JOIN variantes v ON ventas.variante_id = v.id JOIN productos p ON v.producto_id = p.id WHERE DATE(ventas.fecha)=CURRENT_DATE ORDER BY ventas.fecha DESC")
                total = 0
                for r in c.fetchall():
                    total += float(r[1])
                    col_reporte.controls.append(ft.Container(padding=10, border=ft.border.only(bottom=ft.border.BorderSide(1,"#dddddd")), content=ft.Column([
                        ft.Row([ft.Text(f"{r[3]}", weight="bold"), ft.Text(f"${r[1]}", weight="bold", color="green")], alignment="spaceBetween"),
                        ft.Row([ft.Text(f"Hora: {r[0]}", size=12), ft.Text(f"Tel: {r[2] if r[2] else '-'}", size=12)], alignment="spaceBetween")
                    ])))
                col_reporte.controls.insert(0, ft.Container(bgcolor="#e8f5e9", padding=15, border_radius=10, content=ft.Row([ft.Text("Total Hoy:", size=18), ft.Text(f"${total:,.2f}", size=22, weight="bold", color="green")], alignment="spaceBetween")))
                conn.close()
            except Exception as e: col_reporte.controls.append(ft.Text(f"Error carga: {e}", color="red"))
            page.update()
        
        vista_reportes = ft.ListView(expand=True, padding=20, spacing=10, controls=[
            ft.Text("Corte de Caja", size=25, weight="bold"),
            ft.ElevatedButton("Actualizar", icon="refresh", on_click=lambda e: cargar_reporte()),
            col_reporte
        ])

        # VISTA AGREGAR
        txt_new_sku = ft.TextField(label="SKU")
        txt_new_tono = ft.TextField(label="Tono")
        txt_new_precio = ft.TextField(label="Precio", keyboard_type="number")
        txt_new_stock = ft.TextField(label="Stock", keyboard_type="number")
        def guardar_nuevo(e):
            page.snack_bar = ft.SnackBar(ft.Text("Función disponible en PC"), bgcolor="orange"); page.snack_bar.open=True; page.update()

        vista_agregar = ft.ListView(expand=True, padding=20, spacing=15, controls=[
            ft.Text("Nuevo Producto", size=25, weight="bold"),
            txt_new_sku, txt_new_tono, txt_new_precio, txt_new_stock,
            ft.ElevatedButton("GUARDAR (Solo PC)", on_click=guardar_nuevo, height=50)
        ])

        # VISTA INVENTARIO
        col_inv = ft.Column()
        def cargar_inv():
            col_inv.controls.clear()
            try:
                conn = psycopg2.connect(URL_CONEXION); c=conn.cursor()
                c.execute("SELECT p.nombre, v.numero_tono, i.stock_actual FROM variantes v JOIN productos p ON v.producto_id=p.id JOIN inventario i ON v.id=i.variante_id ORDER BY p.nombre")
                for r in c.fetchall():
                    col_inv.controls.append(ft.Container(padding=10, border=ft.border.only(bottom=ft.border.BorderSide(1, "#eeeeee")), content=ft.Row([ft.Text(f"{r[0]} {r[1]}"), ft.Text(f"{r[2]} pzas", color="blue" if r[2]>5 else "red")], alignment="spaceBetween")))
                conn.close()
            except: pass
            page.update()
        
        vista_inv = ft.ListView(expand=True, padding=20, spacing=10, controls=[
            ft.Text("Inventario", size=25, weight="bold"),
            ft.ElevatedButton("Refrescar", on_click=lambda e: cargar_inv()), 
            col_inv
        ])

        # --- VISTA USUARIOS (RESTAURADA COMPLETA) ---
        col_users = ft.Column()
        # Campos para crear nuevo usuario
        txt_u_new = ft.TextField(label="Nuevo Usuario")
        txt_p_new = ft.TextField(label="Contraseña", password=True)
        dd_rol = ft.Dropdown(label="Rol", options=[
            ft.dropdown.Option("vendedor"), 
            ft.dropdown.Option("gerente"), 
            ft.dropdown.Option("admin")
        ], value="vendedor")

        def cargar_users():
            col_users.controls.clear()
            try:
                conn = psycopg2.connect(URL_CONEXION); c=conn.cursor()
                c.execute("SELECT id, username, rol FROM usuarios ORDER BY username")
                for r in c.fetchall():
                    uid, uname, urol = r
                    # Fila con nombre y botón de eliminar
                    col_users.controls.append(
                        ft.Container(
                            padding=10, 
                            border=ft.border.only(bottom=ft.border.BorderSide(1, "#eeeeee")), 
                            content=ft.Row([
                                ft.Text(f"👤 {uname} ({urol})", size=16),
                                ft.IconButton(icon="delete", icon_color="red", on_click=lambda e, x=uid: eliminar_user(x))
                            ], alignment="spaceBetween")
                        )
                    )
                conn.close()
            except: pass
            page.update()

        def eliminar_user(id_borrar):
            if id_borrar == usuario_actual_id:
                page.snack_bar = ft.SnackBar(ft.Text("No te puedes borrar a ti mismo"), bgcolor="orange"); page.snack_bar.open=True; page.update(); return
            try:
                conn = psycopg2.connect(URL_CONEXION); c=conn.cursor()
                c.execute("DELETE FROM usuarios WHERE id=%s", (id_borrar,))
                conn.commit(); conn.close()
                page.snack_bar = ft.SnackBar(ft.Text("Usuario eliminado"), bgcolor="blue"); page.snack_bar.open=True
                cargar_users()
            except Exception as e: page.snack_bar = ft.SnackBar(ft.Text(f"Error: {e}"), bgcolor="red"); page.snack_bar.open=True; page.update()

        def crear_user(e):
            u, p, r = txt_u_new.value, txt_p_new.value, dd_rol.value
            if not u or not p: return
            try:
                h = bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()
                conn = psycopg2.connect(URL_CONEXION); c=conn.cursor()
                c.execute("INSERT INTO usuarios (username, password_hash, rol) VALUES (%s, %s, %s)", (u, h, r))
                conn.commit(); conn.close()
                page.snack_bar = ft.SnackBar(ft.Text("Usuario Creado"), bgcolor="green"); page.snack_bar.open=True
                txt_u_new.value=""; txt_p_new.value=""; cargar_users()
            except Exception as ex: page.snack_bar = ft.SnackBar(ft.Text(f"Error: {ex}"), bgcolor="red"); page.snack_bar.open=True; page.update()

        # Armado de la vista Users verticalmente
        vista_users = ft.ListView(expand=True, padding=20, spacing=15, controls=[
            ft.Text("Gestión Usuarios", size=25, weight="bold"),
            ft.Text("Crear Nuevo:", weight="bold"),
            txt_u_new,
            txt_p_new,
            dd_rol,
            ft.ElevatedButton("CREAR USUARIO", on_click=crear_user, height=50),
            ft.Divider(),
            ft.Row([
                ft.Text("Lista Actual", weight="bold", size=18),
                ft.IconButton(icon="refresh", on_click=lambda e: cargar_users())
            ], alignment="spaceBetween"),
            col_users
        ])

        # --- NAVEGACIÓN ---
        cuerpo_principal = ft.Container(content=vista_ventas, expand=True)

        def cambiar_tab(e):
            idx = e.control.selected_index
            if idx == 0: cuerpo_principal.content = vista_ventas
            label_sel = destinos[idx].label
            if label_sel == "Corte": cuerpo_principal.content = vista_reportes; cargar_reporte()
            elif label_sel == "Stock": cuerpo_principal.content = vista_inv; cargar_inv()
            elif label_sel == "Alta": cuerpo_principal.content = vista_agregar
            elif label_sel == "Users": cuerpo_principal.content = vista_users; cargar_users()
            page.update()

        destinos = [ft.NavigationDestination(icon="money", label="Vender")]
        
        rol_seguro = usuario_actual_rol.lower().strip()
        
        if rol_seguro in ["admin", "gerente", "gerente de tienda", "administrador"]:
            destinos.append(ft.NavigationDestination(icon="assessment", label="Corte"))
            destinos.append(ft.NavigationDestination(icon="list", label="Stock"))
            destinos.append(ft.NavigationDestination(icon="add_box", label="Alta"))

        if "admin" in rol_seguro:
            destinos.append(ft.NavigationDestination(icon="people", label="Users"))

        nav_bar = ft.NavigationBar(destinations=destinos, on_change=cambiar_tab, bgcolor="white", selected_index=0)

        def cerrar_sesion(e):
            global usuario_actual_id; usuario_actual_id = None; page.clean(); page.add(vista_login)

        page.add(
            ft.Column(
                expand=True, spacing=0,
                controls=[
                    ft.Container(padding=10, bgcolor="purple", content=ft.Row([
                        ft.Text(f"Hola, {usuario_actual_nombre}", weight="bold", color="white"),
                        ft.IconButton(icon="logout", icon_color="white", on_click=cerrar_sesion)
                    ], alignment="spaceBetween")),
                    cuerpo_principal,
                    nav_bar
                ]
            )
        )

    page.add(vista_login)

ft.app(target=main, view=ft.AppView.WEB_BROWSER, port=int(os.environ.get("PORT", 8080)), host="0.0.0.0")
