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

# VARIABLES PARA EDICIÓN DE STOCK
id_stock_editar = None

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
                    page.add(ft.Text(f"Error fatal: {ex}", color="red"))
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
        
        # --- A. FUNCIONES AUXILIARES ---
        def enviar_whatsapp(telefono, nombre_prod, precio):
            if not telefono: return
            tel = telefono.strip().replace(" ", "").replace("-", "")
            if len(tel) == 10: tel = "52" + tel
            msg = f"Hola! Compra en Beauty POS.\nProducto: {nombre_prod}\nTotal: ${precio:,.2f}"
            page.launch_url(f"https://wa.me/{tel}?text={urllib.parse.quote(msg)}")

        # --- B. DIALOGOS DE EDICIÓN DE STOCK ---
        txt_nuevo_stock = ft.TextField(label="Nueva Cantidad", keyboard_type="number", autofocus=True)
        
        def guardar_edicion_stock(e):
            global id_stock_editar
            try:
                nueva_cantidad = int(txt_nuevo_stock.value)
                conn = psycopg2.connect(URL_CONEXION); c=conn.cursor()
                c.execute("UPDATE inventario SET stock_actual = %s WHERE variante_id = %s", (nueva_cantidad, id_stock_editar))
                conn.commit(); conn.close()
                page.snack_bar = ft.SnackBar(ft.Text("Stock Actualizado"), bgcolor="green"); page.snack_bar.open=True
                dialogo_editar.open = False
                cargar_inv() # Refrescar lista
            except Exception as ex:
                page.snack_bar = ft.SnackBar(ft.Text(f"Error: {ex}"), bgcolor="red"); page.snack_bar.open=True
            page.update()

        def cerrar_dialogo(e):
            dialogo_editar.open = False
            page.update()

        dialogo_editar = ft.AlertDialog(
            title=ft.Text("Modificar Stock"),
            content=txt_nuevo_stock,
            actions=[
                ft.TextButton("Cancelar", on_click=cerrar_dialogo),
                ft.ElevatedButton("Guardar", on_click=guardar_edicion_stock, bgcolor="blue", color="white")
            ]
        )

        def abrir_editar(id_var, stock_actual):
            global id_stock_editar
            id_stock_editar = id_var
            txt_nuevo_stock.value = str(stock_actual)
            page.dialog = dialogo_editar
            dialogo_editar.open = True
            page.update()

        def eliminar_producto_inv(id_var):
            try:
                conn = psycopg2.connect(URL_CONEXION); c=conn.cursor()
                # Intentamos borrar. Si falla por FK, saltará al except
                c.execute("DELETE FROM inventario WHERE variante_id = %s", (id_var,))
                c.execute("DELETE FROM variantes WHERE id = %s", (id_var,))
                conn.commit(); conn.close()
                page.snack_bar = ft.SnackBar(ft.Text("Producto Eliminado"), bgcolor="blue"); page.snack_bar.open=True
                cargar_inv()
            except psycopg2.errors.ForeignKeyViolation:
                page.snack_bar = ft.SnackBar(ft.Text("❌ No se puede borrar: Tiene ventas históricas"), bgcolor="red"); page.snack_bar.open=True
            except Exception as ex:
                page.snack_bar = ft.SnackBar(ft.Text(f"Error: {ex}"), bgcolor="red"); page.snack_bar.open=True
            page.update()

        # --- C. VENTA ---
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
