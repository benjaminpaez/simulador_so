"""
Carga, parseo y validación de procesos desde archivos CSV/TXT, consola o dataset de ejemplo.
"""

import csv
import os
import sys
from typing import List, Optional, Tuple

from memoria import GestorMemoria
from modelos import Proceso


def validar_procesos(procesos: List[Proceso]) -> Tuple[bool, str]:
    """
    Reglas de negocio:
    - Entre 1 y 10 procesos.
    - Ningún proceso > 450 KB (espacio de usuario).
    - Valores numéricos válidos (tamano > 0, arribo >= 0, irrupción > 0).
    - PIDs únicos y no vacíos.
    """
    if not procesos:
        return False, "La lista de procesos está vacía."

    if len(procesos) > 10:
        return False, f"Se superó el límite permitido de procesos: {len(procesos)} cargados (Máximo: 10)."

    pids_vistos = set()
    for idx, p in enumerate(procesos, start=1):
        if not p.pid:
            return False, f"El proceso #{idx} no tiene un PID válido."

        if p.pid in pids_vistos:
            return False, f"PID duplicado detectado: '{p.pid}'. Los identificadores deben ser únicos."
        pids_vistos.add(p.pid)

        if p.tamano <= 0:
            return False, f"Proceso '{p.pid}': El tamaño debe ser un entero positivo (> 0 KB)."

        if p.tamano > GestorMemoria.TAMANO_USUARIO:
            return False, (
                f"Proceso '{p.pid}': Requiere {p.tamano} KB, lo cual supera el espacio total de usuario "
                f"de {GestorMemoria.TAMANO_USUARIO} KB (Memoria Total 550 KB - 100 KB SO)."
            )

        if p.tiempo_arribo < 0:
            return False, f"Proceso '{p.pid}': El tiempo de arribo debe ser mayor o igual a 0."

        if p.tiempo_irrupcion <= 0:
            return False, f"Proceso '{p.pid}': El tiempo de irrupción debe ser un entero positivo (> 0 u.t.)."

    return True, "Validación exitosa."


def parsear_lineas_procesos(lineas: List[str]) -> List[Proceso]:
    """
    Parsea líneas en formato CSV/TXT: PID,Tamaño,Arribo,Irrupcion.
    Ignora líneas en blanco o comentarios con '#'.
    Reporta el número de línea real del archivo ante errores de formato.
    """
    procesos: List[Proceso] = []
    primera_fila_datos = True

    for nro_linea_real, raw in enumerate(lineas, start=1):
        limpia = raw.strip()
        if not limpia or limpia.startswith("#"):
            continue

        fila = next(csv.reader([limpia]))
        if not fila:
            continue

        if primera_fila_datos:
            primera_fila_datos = False
            if any(h in fila[0].lower() for h in ("pid", "proceso", "id", "identificador")):
                continue

        if len(fila) < 4:
            raise ValueError(
                f"Línea {nro_linea_real} incompleta: se esperan 4 columnas (PID,Tamaño,Arribo,Irrupcion)."
            )

        pid = fila[0].strip()
        try:
            tamano = int(fila[1].strip())
            arribo = int(fila[2].strip())
            irrupcion = int(fila[3].strip())
        except ValueError:
            raise ValueError(
                f"Línea {nro_linea_real} ('{pid}'): Los valores de Tamaño, Arribo e Irrupción deben ser enteros."
            )

        procesos.append(Proceso(
            pid=pid,
            tamano=tamano,
            tiempo_arribo=arribo,
            tiempo_irrupcion=irrupcion,
            tiempo_restante=irrupcion,
        ))

    return procesos


def obtener_dataset_ejemplo() -> List[Proceso]:
    """Dataset predefinido didáctico para demostrar Best-Fit, SRTF y Fragmentación Externa."""
    return [
        Proceso(pid="P1", tamano=200, tiempo_arribo=0, tiempo_irrupcion=5, tiempo_restante=5),
        Proceso(pid="P2", tamano=150, tiempo_arribo=1, tiempo_irrupcion=3, tiempo_restante=3),
        Proceso(pid="P3", tamano=160, tiempo_arribo=2, tiempo_irrupcion=4, tiempo_restante=4),
        Proceso(pid="P4", tamano=80, tiempo_arribo=3, tiempo_irrupcion=2, tiempo_restante=2),
        Proceso(pid="P5", tamano=100, tiempo_arribo=7, tiempo_irrupcion=3, tiempo_restante=3),
    ]


def obtener_directorio_ejecutable() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    if "__file__" in globals():
        return os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.getcwd())


def listar_archivos_carpeta() -> List[str]:
    directorio_base = obtener_directorio_ejecutable()
    try:
        archivos = [
            f for f in os.listdir(directorio_base)
            if os.path.isfile(os.path.join(directorio_base, f))
            and f.lower().endswith((".csv", ".txt"))
        ]
        return sorted(archivos)
    except Exception:
        return []


def resolver_archivo_en_carpeta(nombre_o_ruta: str) -> Optional[str]:
    directorio_base = obtener_directorio_ejecutable()
    nombre_base = os.path.basename(nombre_o_ruta.strip().strip("'\""))
    if not nombre_base:
        return None

    ruta_candidata = os.path.join(directorio_base, nombre_base)
    if os.path.exists(ruta_candidata):
        return ruta_candidata

    if not nombre_base.lower().endswith((".csv", ".txt")):
        ruta_csv = os.path.join(directorio_base, f"{nombre_base}.csv")
        if os.path.exists(ruta_csv):
            return ruta_csv

    return ruta_candidata


def cargar_desde_archivo(nombre_archivo: Optional[str] = None) -> Optional[List[Proceso]]:
    directorio_base = obtener_directorio_ejecutable()
    archivos_disponibles = listar_archivos_carpeta()

    if nombre_archivo is not None and nombre_archivo.strip():
        entrada = nombre_archivo.strip()
    else:
        print("\n" + "-" * 75)
        print(" [CARGA DE ARCHIVO DE PROCESOS]")
        print(f" -> Carpeta: {directorio_base}")
        if archivos_disponibles:
            print(" -> Archivos compatibles detectados:")
            for idx_a, arch in enumerate(archivos_disponibles, start=1):
                print(f"    [{idx_a}] {arch}")
        else:
            print(" -> [AVISO] No se detectaron archivos .csv o .txt en la carpeta.")
        print("-" * 75)

        sugerencia = (
            "procesos.csv"
            if "procesos.csv" in archivos_disponibles
            else (archivos_disponibles[0] if archivos_disponibles else "")
        )
        prompt = (
            f"Ingrese solo el nombre del archivo [Por defecto: {sugerencia}]: "
            if sugerencia
            else "Ingrese solo el nombre del archivo: "
        )
        entrada = input(prompt).strip()
        if not entrada and sugerencia:
            entrada = sugerencia
        elif entrada.isdigit() and archivos_disponibles:
            idx_num = int(entrada) - 1
            if 0 <= idx_num < len(archivos_disponibles):
                entrada = archivos_disponibles[idx_num]

    if not entrada:
        print(">> Operación cancelada: no se especificó ningún nombre de archivo.")
        return None

    ruta = resolver_archivo_en_carpeta(entrada)
    nombre_mostrado = os.path.basename(ruta) if ruta else entrada

    if not ruta or not os.path.exists(ruta):
        print(f"\n>> ERROR: No se encontró el archivo '{nombre_mostrado}' en {directorio_base}.")
        return None

    try:
        with open(ruta, "r", encoding="utf-8") as f:
            lineas = f.readlines()
        procesos = parsear_lineas_procesos(lineas)
    except Exception as e:
        print(f">> ERROR al leer o parsear el archivo '{nombre_mostrado}': {e}")
        return None

    valido, mensaje = validar_procesos(procesos)
    if not valido:
        print(f">> ERROR DE VALIDACIÓN: {mensaje}")
        return None

    print(f">> Archivo '{nombre_mostrado}' cargado exitosamente ({len(procesos)} procesos validados).")
    return procesos


def cargar_manual_consola() -> Optional[List[Proceso]]:
    print("\n--- CARGA MANUAL DE PROCESOS (Máximo 10 procesos) ---")
    try:
        cantidad = int(input("¿Cuántos procesos desea cargar? (1 a 10): ").strip())
        if cantidad < 1 or cantidad > 10:
            print(">> ERROR: La cantidad de procesos debe ser entre 1 y 10.")
            return None
    except ValueError:
        print(">> ERROR: Ingrese un número entero válido.")
        return None

    procesos = []
    for i in range(1, cantidad + 1):
        print(f"\n[Proceso {i} de {cantidad}]")
        pid = input("  Identificador (PID, ej. P1): ").strip().upper() or f"P{i}"
        try:
            tamano = int(input("  Tamaño en KB (1 a 450 KB): ").strip())
            arribo = int(input("  Tiempo de Arribo (Ta >= 0): ").strip())
            irrupcion = int(input("  Tiempo de Irrupción / Burst (Ti > 0): ").strip())
        except ValueError:
            print(">> ERROR: Los valores numéricos deben ser enteros. Carga abortada.")
            return None

        procesos.append(Proceso(
            pid=pid,
            tamano=tamano,
            tiempo_arribo=arribo,
            tiempo_irrupcion=irrupcion,
            tiempo_restante=irrupcion,
        ))

    valido, mensaje = validar_procesos(procesos)
    if not valido:
        print(f">> ERROR DE VALIDACIÓN: {mensaje}")
        return None

    print(f">> Se cargaron exitosamente {len(procesos)} procesos manualmente.")
    return procesos