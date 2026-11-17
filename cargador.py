"""
Carga, parseo y validación de procesos desde archivos CSV/TXT, consola o dataset de ejemplo.
Incluye manejo robusto de errores con pausa y validación inmediata por campo en carga manual.
"""

import csv
import os
import sys
from typing import List, Optional, Tuple

from memoria import GestorMemoria
from modelos import Proceso


def _pausar_tras_error(mensaje: str) -> None:
    """Muestra un mensaje de error y espera [ENTER] antes de regresar al menú."""
    print(f"\n>> {mensaje}")
    try:
        input("Presione [ENTER] para volver al menú principal... ")
    except (KeyboardInterrupt, EOFError):
        pass


def validar_procesos(procesos: List[Proceso]) -> Tuple[bool, str]:
    """
    Reglas de negocio:
    - Entre 1 y 10 procesos.
    - Ningún proceso > 450 KB (espacio de usuario).
    - Valores numéricos válidos (tamano > 0, arribo >= 0, irrupción > 0).
    - PIDs únicos y no vacíos.
    """
    if not procesos:
        return False, "[ERROR] La lista de procesos está vacía. Debe cargar al menos 1 proceso."

    if len(procesos) > 10:
        return False, (
            f"[ERROR] Se superó el límite permitido de procesos: {len(procesos)} cargados "
            f"(Máximo permitido: 10)."
        )

    pids_vistos = set()
    for idx, p in enumerate(procesos, start=1):
        if not p.pid or not p.pid.strip():
            return False, f"[ERROR] El proceso #{idx} no tiene un PID válido."

        if p.pid in pids_vistos:
            return False, f"[ERROR] PID duplicado detectado: '{p.pid}'. Los identificadores deben ser únicos."
        pids_vistos.add(p.pid)

        if p.tamano <= 0:
            return False, f"[ERROR] Proceso '{p.pid}': El tamaño debe ser un entero positivo (> 0 KB)."

        if p.tamano > GestorMemoria.TAMANO_USUARIO:
            return False, (
                f"[ERROR] Proceso '{p.pid}': Requiere {p.tamano} KB, lo cual supera el espacio total de usuario "
                f"de {GestorMemoria.TAMANO_USUARIO} KB (Memoria Total 550 KB - 100 KB SO)."
            )

        if p.tiempo_arribo < 0:
            return False, f"[ERROR] Proceso '{p.pid}': El tiempo de arribo (Ta) debe ser mayor o igual a 0."

        if p.tiempo_irrupcion <= 0:
            return False, f"[ERROR] Proceso '{p.pid}': El tiempo de irrupción (Ti) debe ser un entero positivo (> 0 u.t.)."

    return True, "Validación exitosa."


def parsear_lineas_procesos(lineas: List[str]) -> List[Proceso]:
    """
    Parsea líneas en formato CSV/TXT: PID,Tamaño,Arribo,Irrupcion.
    Soporta coma (,) y punto y coma (;). Ignora líneas en blanco o comentarios con '#'.
    Reporta el número de línea real del archivo ante errores de formato.
    """
    procesos: List[Proceso] = []
    primera_fila_datos = True

    for nro_linea_real, raw in enumerate(lineas, start=1):
        limpia = raw.strip()
        if not limpia or limpia.startswith("#"):
            continue

        delimitador = ";" if ("," not in limpia and ";" in limpia) else ","
        fila = next(csv.reader([limpia], delimiter=delimitador))
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
        if not pid:
            raise ValueError(f"Línea {nro_linea_real}: El identificador (PID) no puede estar vacío.")

        try:
            tamano = int(fila[1].strip())
            arribo = int(fila[2].strip())
            irrupcion = int(fila[3].strip())
        except ValueError:
            raise ValueError(
                f"Línea {nro_linea_real} ('{pid}'): Tamaño, Arribo e Irrupción deben ser números enteros."
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
            and not f.lower().startswith("reporte_simulacion_")
            and f.lower() != "howto.txt"
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


def _leer_lineas_archivo(ruta: str) -> List[str]:
    """Lee el archivo probando UTF-8 y cayendo a Latin-1 si fue guardado desde Excel."""
    try:
        with open(ruta, "r", encoding="utf-8-sig") as f:
            return f.readlines()
    except UnicodeDecodeError:
        with open(ruta, "r", encoding="latin-1") as f:
            return f.readlines()


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
            f"Ingrese nombre o número del archivo y de ENTER[Por defecto: {sugerencia}]: "
            if sugerencia
            else "Ingrese nombre o número del archivo: "
        )
        entrada = input(prompt).strip()
        if not entrada and sugerencia:
            entrada = sugerencia
        elif entrada.isdigit():
            idx_num = int(entrada) - 1
            if 0 <= idx_num < len(archivos_disponibles):
                entrada = archivos_disponibles[idx_num]
            else:
                _pausar_tras_error(
                    f"[ERROR] Índice {entrada} fuera de rango (1 a {len(archivos_disponibles)})."
                )
                return None

    if not entrada:
        _pausar_tras_error("[ERROR] No se especificó ningún nombre de archivo.")
        return None

    ruta = resolver_archivo_en_carpeta(entrada)
    nombre_mostrado = os.path.basename(ruta) if ruta else entrada

    if not ruta or not os.path.exists(ruta):
        _pausar_tras_error(
            f"[ERROR] No se encontró el archivo '{nombre_mostrado}' en {directorio_base}."
        )
        return None

    if os.path.isdir(ruta):
        _pausar_tras_error(f"[ERROR] '{nombre_mostrado}' es una carpeta, no un archivo válido.")
        return None

    try:
        lineas = _leer_lineas_archivo(ruta)
        procesos = parsear_lineas_procesos(lineas)
    except Exception as e:
        _pausar_tras_error(f"[ERROR] Al leer o parsear '{nombre_mostrado}': {e}")
        return None

    valido, mensaje = validar_procesos(procesos)
    if not valido:
        _pausar_tras_error(mensaje)
        return None

    print(f">> Archivo '{nombre_mostrado}' cargado exitosamente ({len(procesos)} procesos validados).")
    return procesos


def _pedir_entero_validado(
    prompt: str,
    minimo: Optional[int] = None,
    maximo: Optional[int] = None,
) -> Optional[int]:
    """Valida un entero en el momento, permitiendo reintentar o cancelar con 'c'."""
    while True:
        raw = input(prompt).strip()
        if raw.lower() in ("c", "cancelar"):
            return None
        try:
            valor = int(raw)
        except ValueError:
            print("  >> [ERROR] Debe ingresar un número entero válido (o 'c' para cancelar).")
            continue

        if minimo is not None and valor < minimo:
            print(f"  >> [ERROR] El valor debe ser >= {minimo} (ingresaste {valor}).")
            continue
        if maximo is not None and valor > maximo:
            print(f"  >> [ERROR] El valor no puede superar {maximo} (ingresaste {valor}).")
            continue
        return valor


def cargar_manual_consola() -> Optional[List[Proceso]]:
    print("\n--- CARGA MANUAL DE PROCESOS (Máximo 10 procesos | 'c' para cancelar) ---")
    try:
        cantidad = int(input("¿Cuántos procesos desea cargar? (1 a 10): ").strip())
        if cantidad < 1 or cantidad > 10:
            _pausar_tras_error(
                f"[ERROR] La cantidad de procesos debe estar entre 1 y 10 (ingresaste {cantidad})."
            )
            return None
    except ValueError:
        _pausar_tras_error("[ERROR] Debe ingresar un número entero válido.")
        return None

    procesos: List[Proceso] = []
    pids_usados = set()

    for i in range(1, cantidad + 1):
        print(f"\n[Proceso {i} de {cantidad}]")
        while True:
            pid = input(f"  Identificador (PID) [Por defecto P{i}]: ").strip().upper() or f"P{i}"
            if pid in pids_usados:
                print(f"  >> [ERROR] El PID '{pid}' ya fue ingresado. Elija otro.")
                continue
            pids_usados.add(pid)
            break

        tamano = _pedir_entero_validado(
            "  Tamaño en KB (1 a 450 KB): ",
            minimo=1,
            maximo=GestorMemoria.TAMANO_USUARIO,
        )
        if tamano is None:
            _pausar_tras_error("Carga manual cancelada por el usuario.")
            return None

        arribo = _pedir_entero_validado("  Tiempo de Arribo (Ta >= 0): ", minimo=0)
        if arribo is None:
            _pausar_tras_error("Carga manual cancelada por el usuario.")
            return None

        irrupcion = _pedir_entero_validado("  Tiempo de Irrupción / Burst (Ti > 0): ", minimo=1)
        if irrupcion is None:
            _pausar_tras_error("Carga manual cancelada por el usuario.")
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
        _pausar_tras_error(mensaje)
        return None

    print(f">> Se cargaron exitosamente {len(procesos)} procesos manualmente.")
    return procesos