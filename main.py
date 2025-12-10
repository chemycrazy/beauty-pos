import flet as ft
import psycopg2
import bcrypt
import os
import urllib.parse
from datetime import datetime
import platform
import traceback
import logging

# --- CONFIGURACIÓN DE LOGS ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BeautyPOS")

# --- CONFIGURACIÓN BASE DE DATOS ---
# ⚠️ PON TU CONTRASEÑA AQUÍ
URL_CONEXION = "postgresql://postgres.swavrpqagshyddhjaipf:R57667115#g@aws-0-us-west-2.pooler.supabase.com:6543/postgres"

# --- PARCHE DE COMPATIBILIDAD ---
try:
    NavDest = ft.NavigationDestination
except AttributeError:
    NavDest = ft.NavigationBarDestination

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

    # 0. INICIALIZAR DB Y ACTUALIZAR TABLA USUARIOS
    def inicializar_db():
        try:
            conn = psycopg2.connect(URL_CONEXION); c = conn.cursor()
            # 1. Tabla Marcas
            c.execute("CREATE TABLE IF NOT EXISTS marcas (id SERIAL PRIMARY KEY, nombre VARCHAR(100) UNIQUE NOT NULL);")
            # 2. Actualización Tabla Usuarios (Agregamos columna activo si no existe)
            c.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS activo BOOLEAN DEFAULT TRUE;")
            conn.commit(); conn.close()
        except: pass
    inicializar_db()

    # ==========================================
    # 1. LOGIN (AHORA VERIFICA SI ESTÁ ACTIVO)
    # ==========================================
    def verificar_login(e):
        global usuario_actual_id, usuario_actual_nombre, usuario_actual_rol
        user = txt_user_login.value
        pwd = txt_pass_login.value
        btn_login.text = "Cargando..."
        btn_login.disabled = True
        page.update()

        try:
            conn = psycopg2.connect(URL_CONEXION); cursor = conn.cursor()
            # MODIFICACIÓN CLAVE: AND activo = TRUE
            cursor.execute("SELECT id, password_hash, rol FROM usuarios WHERE username = %s AND activo = TRUE", (user,))
            res = cursor.fetchone(); conn.close()

            if res and bcrypt.checkpw(pwd.encode(), res[1].encode()):
                usuario_actual_id = res[0]; usuario_actual_nombre = user; 
                usuario_actual_rol = str(res[2]).strip().lower()
                page.clean(); construir_interfaz()
            else:
                lbl_error_login.value = "❌ Datos incorrectos o Usuario Inactivo"; btn_login.text = "ENTRAR"; btn_login.disabled = False
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
        
        # --- FUNCIONES AUXILIARES ---
        def enviar_whatsapp(telefono, nombre_prod, precio):
            if not telefono: return
            tel = telefono.strip().replace(" ", "").replace("-", "")
            if len(tel) == 10: tel = "52" + tel
            msg = f"Hola! Compra en Beauty POS.\nProducto: {nombre_prod}\nTotal: ${precio:,.2f}"
            page.launch_url(f"https://wa.me/{tel}?text={urllib.parse.quote(msg)}")

        # --- A. VENTA ---
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
            texto_busqueda = txt_busqueda.value.strip() # Limpiamos espacios
            
            id_variante_seleccionada = None
            
            if not texto_busqueda: return

            try:
                conn = psycopg2.connect(URL_CONEXION); c = conn.cursor()
                
                # --- CAMBIO IMPORTANTE AQUÍ ---
                # Ahora buscamos por SKU (código) O por Numero de Tono
                # Usamos ILIKE para que no importen las mayúsculas/minúsculas
                query = """
                    SELECT v.id, p.nombre, v.nombre_variante, v.precio_venta, i.stock_actual 
                    FROM variantes v 
                    JOIN productos p ON v.producto_id = p.id 
                    JOIN inventario i ON v.id = i.variante_id 
                    WHERE v.sku ILIKE %s OR v.numero_tono ILIKE %s
                """
                
                # Pasamos el mismo texto dos veces: una para intentar calzar con SKU y otra con Tono
                c.execute(query, (texto_busqueda, texto_busqueda))
                
                r = c.fetchone()
                conn.close()
                
                if r:
                    id_variante_seleccionada = r[0]
                    nombre_producto_seleccionado = f"{r[1]} {r[2]}"
                    precio_venta_seleccionado = float(r[3])
                    
                    info_prod.value = f"{r[1]} {r[2]}\nPrecio: ${r[3]}\nStock: {r[4]}"
                    info_prod.color = "black"
                    
                    # Lógica de stock (Visual)
                    if r[4] > 0: 
                        btn_cobrar.visible = True
                        txt_tel.visible = True
                        btn_cobrar.disabled = False
                    else: 
                        info_prod.value += " (AGOTADO)"
                        info_prod.color = "red"
                        btn_cobrar.visible = False
                else: 
                    info_prod.value = "❌ No encontrado"
                    info_prod.color = "red"
                    btn_cobrar.visible = False
            except Exception as err:
                info_prod.value = f"Error: {err}"
            
            page.update()

        txt_busqueda = ft.TextField(label="Buscar Tono", on_submit=buscar_prod)
        info_prod = ft.Text("", size=18, weight="bold")
        txt_tel = ft.TextField(label="WhatsApp Cliente", keyboard_type=ft.KeyboardType.PHONE, visible=False)
        btn_cobrar = ft.ElevatedButton("COBRAR", bgcolor="green", color="white", visible=False, on_click=finalizar_venta, height=50)
        
        vista_ventas = ft.ListView(expand=True, padding=20, spacing=15, controls=[
            ft.Text("Punto de Venta", size=25, weight="bold"),
            ft.Row([txt_busqueda, ft.IconButton(icon="search", on_click=buscar_prod, icon_color="purple")]),
            ft.Divider(), info_prod, txt_tel, btn_cobrar
        ])

        # --- B. REPORTE ---
        col_reporte = ft.Column()
        def cargar_reporte(modo="diario"):
            col_reporte.controls.clear()
            titulo = "Total Hoy:"
            try:
                conn = psycopg2.connect(URL_CONEXION); c=conn.cursor()
                if modo == "diario":
                    query = "SELECT TO_CHAR(ventas.fecha, 'HH24:MI'), ventas.precio_venta, ventas.cliente_telefono, p.nombre FROM ventas JOIN variantes v ON ventas.variante_id = v.id JOIN productos p ON v.producto_id = p.id WHERE DATE(ventas.fecha)=CURRENT_DATE ORDER BY ventas.fecha DESC"
                else:
                    query = "SELECT TO_CHAR(ventas.fecha, 'DD/MM HH24:MI'), ventas.precio_venta, ventas.cliente_telefono, p.nombre FROM ventas JOIN variantes v ON ventas.variante_id = v.id JOIN productos p ON v.producto_id = p.id WHERE ventas.fecha >= CURRENT_DATE - INTERVAL '7 days' ORDER BY ventas.fecha DESC"
                    titulo = "Total 7 Días:"
                c.execute(query)
                total = 0
                for r in c.fetchall():
                    total += float(r[1])
                    col_reporte.controls.append(ft.Container(padding=10, border=ft.border.only(bottom=ft.border.BorderSide(1,"#dddddd")), content=ft.Column([
                        ft.Row([ft.Text(f"{r[3]}", weight="bold"), ft.Text(f"${r[1]}", weight="bold", color="green")], alignment="spaceBetween"),
                        ft.Row([ft.Text(f"Fecha: {r[0]}", size=12), ft.Text(f"Tel: {r[2] if r[2] else '-'}", size=12)], alignment="spaceBetween")
                    ])))
                col_reporte.controls.insert(0, ft.Container(bgcolor="#e3f2fd", padding=15, border_radius=10, content=ft.Row([ft.Text(titulo, size=18), ft.Text(f"${total:,.2f}", size=22, weight="bold", color="purple")], alignment="spaceBetween")))
                conn.close()
            except Exception as e: col_reporte.controls.append(ft.Text(f"Error carga: {e}", color="red"))
            page.update()
        
        vista_reportes = ft.ListView(expand=True, padding=20, spacing=10, controls=[
            ft.Text("Corte de Caja", size=25, weight="bold"),
            ft.Row([ft.ElevatedButton("HOY", on_click=lambda e: cargar_reporte("diario"), expand=True), ft.ElevatedButton("SEMANA", on_click=lambda e: cargar_reporte("semanal"), expand=True)]),
            ft.Divider(), col_reporte
        ])

        # --- C. INVENTARIO ---
        col_inv = ft.Column()
        
        def click_lapiz_stock(e):
            datos = e.control.data 
            txt_nuevo = ft.TextField(value=str(datos['stock']), label="Nuevo Stock", keyboard_type="number", autofocus=True)
            
            def guardar_cambio(e):
                try:
                    conn = psycopg2.connect(URL_CONEXION); c=conn.cursor()
                    c.execute("UPDATE inventario SET stock_actual = %s WHERE variante_id = %s", (int(txt_nuevo.value), datos['id']))
                    conn.commit(); conn.close()
                    page.close(dlg_edit)
                    page.snack_bar = ft.SnackBar(ft.Text("✅ Stock actualizado"), bgcolor="green"); page.snack_bar.open=True
                    page.update()
                    cargar_inv()
                except Exception as ex: page.snack_bar = ft.SnackBar(ft.Text(f"Error: {ex}"), bgcolor="red"); page.snack_bar.open=True; page.update()

            dlg_edit = ft.AlertDialog(title=ft.Text("Editar Stock"), content=txt_nuevo, actions=[ft.TextButton("Cancelar", on_click=lambda e: page.close(dlg_edit)), ft.ElevatedButton("GUARDAR", on_click=guardar_cambio)])
            page.open(dlg_edit)

        def borrar_item(e):
            id_var = e.control.data
            try:
                conn = psycopg2.connect(URL_CONEXION); c=conn.cursor()
                c.execute("DELETE FROM inventario WHERE variante_id=%s", (id_var,))
                c.execute("DELETE FROM variantes WHERE id=%s", (id_var,))
                conn.commit(); conn.close()
                page.snack_bar = ft.SnackBar(ft.Text("Eliminado"), bgcolor="purple"); page.snack_bar.open=True
                cargar_inv()
            except: page.snack_bar = ft.SnackBar(ft.Text("No se puede borrar (tiene ventas)"), bgcolor="red"); page.snack_bar.open=True; page.update()

        def cargar_inv():
            col_inv.controls.clear()
            try:
                conn = psycopg2.connect(URL_CONEXION); c=conn.cursor()
                c.execute("SELECT v.id, p.nombre, v.numero_tono, i.stock_actual FROM variantes v JOIN productos p ON v.producto_id=p.id JOIN inventario i ON v.id=i.variante_id ORDER BY p.nombre, v.numero_tono")
                for r in c.fetchall():
                    vid, nom, ton, stk = r
                    btn_edit = ft.IconButton(icon="edit", icon_color="purple", data={'id': vid, 'stock': stk}, on_click=click_lapiz_stock)
                    btn_del = ft.IconButton(icon="delete", icon_color="red", data=vid, on_click=borrar_item)
                    col_inv.controls.append(ft.Container(padding=10, border=ft.border.only(bottom=ft.border.BorderSide(1, "#eeeeee")), content=ft.Row([
                        ft.Column([ft.Text(f"{nom} - {ton}", weight="bold"), ft.Text(f"Stock: {stk}", color="purple" if stk>5 else "red")]),
                        ft.Row([btn_edit, btn_del])
                    ], alignment="spaceBetween")))
                conn.close()
            except: pass
            page.update()
        
        vista_inv = ft.ListView(expand=True, padding=20, spacing=10, controls=[
            ft.Text("Inventario", size=25, weight="bold"),
            ft.ElevatedButton("Refrescar", on_click=lambda e: cargar_inv()), 
            col_inv
        ])

        # --- D. AGREGAR ---
        dd_marcas = ft.Dropdown(label="Selecciona Línea", expand=True)
        txt_new_sku = ft.TextField(label="SKU")
        txt_new_tono = ft.TextField(label="Tono (ej. 7.1)")
        txt_new_precio = ft.TextField(label="Precio Venta", keyboard_type="number")
        txt_new_stock = ft.TextField(label="Stock Inicial", keyboard_type="number")
        
        def click_nueva_marca(e):
            txt_m = ft.TextField(label="Nombre Nueva Línea", autofocus=True)
            def guardar_m(e):
                if not txt_m.value: return
                try:
                    conn = psycopg2.connect(URL_CONEXION); c=conn.cursor()
                    c.execute("INSERT INTO productos (nombre) VALUES (%s)", (txt_m.value,))
                    conn.commit(); conn.close()
                    page.close(dlg_m)
                    page.snack_bar = ft.SnackBar(ft.Text("Línea Creada"), bgcolor="green"); page.snack_bar.open=True
                    page.update(); cargar_marcas_dropdown()
                except Exception as ex: page.snack_bar = ft.SnackBar(ft.Text(f"Error: {ex}"), bgcolor="red"); page.snack_bar.open=True; page.update()
            dlg_m = ft.AlertDialog(title=ft.Text("Nueva Línea"), content=txt_m, actions=[ft.ElevatedButton("CREAR", on_click=guardar_m)])
            page.open(dlg_m)

        def cargar_marcas_dropdown():
            try:
                conn = psycopg2.connect(URL_CONEXION); c=conn.cursor()
                c.execute("SELECT id, nombre FROM productos ORDER BY nombre")
                dd_marcas.options = [ft.dropdown.Option(key=str(x[0]), text=x[1]) for x in c.fetchall()]
                conn.close(); page.update()
            except: pass

        def guardar_prod(e):
            if not dd_marcas.value or not txt_new_sku.value: 
                page.snack_bar = ft.SnackBar(ft.Text("Falta Línea o SKU"), bgcolor="orange"); page.snack_bar.open=True; page.update(); return
            try:
                conn = psycopg2.connect(URL_CONEXION); c=conn.cursor()
                c.execute("INSERT INTO variantes (producto_id, sku, nombre_variante, numero_tono, precio_compra, precio_venta) VALUES (%s, %s, %s, %s, 0, %s) RETURNING id", 
                            (dd_marcas.value, txt_new_sku.value, f"Tono {txt_new_tono.value}", txt_new_tono.value, float(txt_new_precio.value)))
                nid = c.fetchone()[0]
                c.execute("INSERT INTO inventario (variante_id, stock_actual) VALUES (%s, %s)", (nid, int(txt_new_stock.value)))
                conn.commit(); conn.close()
                page.snack_bar = ft.SnackBar(ft.Text("✅ Guardado"), bgcolor="green"); page.snack_bar.open=True
                txt_new_sku.value=""; txt_new_tono.value=""; txt_new_precio.value=""; txt_new_stock.value=""
                if usuario_actual_rol in ["gerente", "admin"]: cargar_inv() 
                page.update()
            except Exception as ex: page.snack_bar = ft.SnackBar(ft.Text(f"Error: {ex}"), bgcolor="red"); page.snack_bar.open=True; page.update()

        vista_agregar = ft.ListView(expand=True, padding=20, spacing=15, controls=[
            ft.Text("Nuevo Producto", size=25, weight="bold"),
            ft.Row([dd_marcas, ft.IconButton(icon="add_circle", icon_color="purple", icon_size=40, on_click=click_nueva_marca)]),
            ft.ElevatedButton("Refrescar Líneas", icon="refresh", on_click=lambda e: cargar_marcas_dropdown()),
            txt_new_sku, txt_new_tono, txt_new_precio, txt_new_stock,
            ft.ElevatedButton("GUARDAR PRODUCTO", on_click=guardar_prod, height=50, bgcolor="purple", color="white")
        ])

        # --- E. USUARIOS (INACTIVAR/ACTIVAR) ---
        col_users = ft.Column()
        txt_u_new = ft.TextField(label="Nuevo Usuario")
        txt_p_new = ft.TextField(label="Contraseña", password=True)
        dd_rol = ft.Dropdown(label="Rol", options=[ft.dropdown.Option("vendedor"), ft.dropdown.Option("gerente"), ft.dropdown.Option("admin")], value="vendedor")

        def crear_user(e):
            u, p, r = txt_u_new.value, txt_p_new.value, dd_rol.value
            if not u or not p: return
            try:
                h = bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()
                conn = psycopg2.connect(URL_CONEXION); c=conn.cursor()
                c.execute("INSERT INTO usuarios (username, password_hash, rol, activo) VALUES (%s, %s, %s, TRUE)", (u, h, r))
                conn.commit(); conn.close()
                page.snack_bar = ft.SnackBar(ft.Text("Usuario Creado"), bgcolor="green"); page.snack_bar.open=True
                txt_u_new.value=""; txt_p_new.value=""; cargar_users()
            except Exception as ex: page.snack_bar = ft.SnackBar(ft.Text(f"Error: {ex}"), bgcolor="red"); page.snack_bar.open=True
            page.update()

        # FUNCIÓN DE TOGGLE (BLOQUEAR/DESBLOQUEAR)
        def toggle_status(e):
            datos = e.control.data # {id: 1, activo: True}
            uid = datos['id']
            estado_actual = datos['activo']
            if uid == usuario_actual_id: 
                page.snack_bar = ft.SnackBar(ft.Text("No puedes bloquearte a ti mismo"), bgcolor="orange"); page.snack_bar.open=True; page.update(); return
            
            try:
                nuevo_estado = not estado_actual
                conn = psycopg2.connect(URL_CONEXION); c=conn.cursor()
                c.execute("UPDATE usuarios SET activo = %s WHERE id = %s", (nuevo_estado, uid))
                conn.commit(); conn.close()
                msg = "Usuario Activado" if nuevo_estado else "Usuario Bloqueado"
                page.snack_bar = ft.SnackBar(ft.Text(msg), bgcolor="purple" if nuevo_estado else "grey"); page.snack_bar.open=True
                cargar_users()
            except Exception as ex: page.snack_bar = ft.SnackBar(ft.Text(f"Error: {ex}"), bgcolor="red"); page.snack_bar.open=True; page.update()

        def eliminar_user_permanente(e):
            id_b = e.control.data
            if id_b == usuario_actual_id: return
            try:
                conn = psycopg2.connect(URL_CONEXION); c=conn.cursor()
                c.execute("DELETE FROM usuarios WHERE id=%s", (id_b,))
                conn.commit(); conn.close()
                page.snack_bar = ft.SnackBar(ft.Text("Eliminado Permanentemente"), bgcolor="red"); page.snack_bar.open=True; cargar_users()
            except: page.snack_bar = ft.SnackBar(ft.Text("Tiene ventas, usa el botón de BLOQUEAR"), bgcolor="orange"); page.snack_bar.open=True; page.update()

        def cargar_users():
            col_users.controls.clear()
            try:
                conn = psycopg2.connect(URL_CONEXION); c=conn.cursor()
                # OBTENEMOS EL ESTADO 'ACTIVO'
                c.execute("SELECT id, username, rol, activo FROM usuarios ORDER BY id")
                for r in c.fetchall():
                    uid, uname, urol, activo = r
                    
                    # ICONO DE ESTADO
                    icono_status = "check_circle" if activo else "block"
                    color_status = "green" if activo else "grey"
                    tooltip_status = "Bloquear" if activo else "Activar"
                    
                    # Estilo visual: si está inactivo, texto gris
                    color_texto = "black" if activo else "grey"

                    col_users.controls.append(ft.Container(padding=10, border=ft.border.only(bottom=ft.border.BorderSide(1, "#eeeeee")), content=ft.Row([
                        ft.Text(f"👤 {uname} ({urol})", size=16, color=color_texto),
                        ft.Row([
                            # BOTÓN TOGGLE (BLOQUEAR/DESBLOQUEAR)
                            ft.IconButton(icon=icono_status, icon_color=color_status, tooltip=tooltip_status, data={'id': uid, 'activo': activo}, on_click=toggle_status),
                            # BOTÓN ELIMINAR (SOLO SI ES NECESARIO)
                            ft.IconButton(icon="delete", icon_color="red", tooltip="Eliminar Permanente", data=uid, on_click=eliminar_user_permanente)
                        ])
                    ], alignment="spaceBetween")))
                conn.close()
            except: pass
            page.update()

        vista_users = ft.ListView(expand=True, padding=20, spacing=15, controls=[
            ft.Text("Gestión Usuarios", size=25, weight="bold"),
            ft.Text("Crear Nuevo:", weight="bold"), txt_u_new, txt_p_new, dd_rol,
            ft.ElevatedButton("CREAR USUARIO", on_click=crear_user, height=50),
            ft.Divider(),
            ft.Row([ft.Text("Lista Actual", weight="bold", size=18), ft.IconButton(icon="refresh", on_click=lambda e: cargar_users())], alignment="spaceBetween"),
            col_users
        ])

        # --- NAVEGACIÓN ---
        cuerpo_principal = ft.Container(content=vista_ventas, expand=True)

        def cambiar_tab(e):
            idx = e.control.selected_index
            if idx == 0: cuerpo_principal.content = vista_ventas
            label_sel = destinos[idx].label
            if label_sel == "Corte": cuerpo_principal.content = vista_reportes; cargar_reporte("diario")
            elif label_sel == "Stock": cuerpo_principal.content = vista_inv; cargar_inv()
            elif label_sel == "Alta": cuerpo_principal.content = vista_agregar; cargar_marcas_dropdown()
            elif label_sel == "Users": cuerpo_principal.content = vista_users; cargar_users()
            page.update()

        destinos = [NavDest(icon="money", label="Vender")]
        rol_seguro = usuario_actual_rol.lower().strip()
        if rol_seguro in ["admin", "gerente", "gerente de tienda", "administrador"]:
            destinos.append(NavDest(icon="assessment", label="Corte"))
            destinos.append(NavDest(icon="list", label="Stock"))
            destinos.append(NavDest(icon="add_box", label="Alta"))
        if "admin" in rol_seguro:
            destinos.append(NavDest(icon="people", label="Users"))

        nav_bar = ft.NavigationBar(destinations=destinos, on_change=cambiar_tab, bgcolor="white", selected_index=0)

        def cerrar_sesion(e):
            global usuario_actual_id; usuario_actual_id = None; page.clean(); page.add(vista_login)

        page.add(
            ft.Column(expand=True, spacing=0, controls=[
                ft.Container(padding=10, bgcolor="purple", content=ft.Row([
                    ft.Text(f"Hola, {usuario_actual_nombre}", weight="bold", color="white"),
                    ft.IconButton(icon="logout", icon_color="white", on_click=cerrar_sesion)
                ], alignment="spaceBetween")),
                cuerpo_principal,
                nav_bar
            ])
        )

    page.add(vista_login)

if __name__ == "__main__":
    try:
        ft.app(target=main, view=ft.AppView.WEB_BROWSER, port=int(os.environ.get("PORT", 8080)), host="0.0.0.0")
    except Exception as e:
        logger.error(f"Error fatal iniciando Flet: {e}")
        raise e
