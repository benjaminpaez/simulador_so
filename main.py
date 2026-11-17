"""
Punto de entrada principal del Simulador de Asignación de Memoria y Planificación de Procesos.
Cátedra: Sistemas Operativos - UTN FRRe (Facultad Regional Resistencia).
"""

import os
import sys

from cargador import (
    cargar_desde_archivo,
    cargar_manual_consola,
    obtener_dataset_ejemplo,
)
from simulador import Simulador
from vista_consola import (
    ejecutar_simulacion_interactiva,
    mostrar_tabla_procesos_cargados,
)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def ajustar_ancho_consola() -> None:
    """En Windows, ajusta el ancho mínimo a 105 columnas para que las tablas ASCII no se corten."""
    if os.name == "nt" and sys.stdout.isatty():
        try:
            if os.get_terminal_size().columns < 105:
                os.system("mode con: cols=105 lines=38")
        except Exception:
            pass


def limpiar_consola() -> None:
    """Limpia la pantalla de la terminal en Windows (cls) o Linux/macOS (clear)."""
    os.system("cls" if os.name == "nt" else "clear")


def _confirmar_inicio() -> bool:
    """Solicita confirmación S/n validando que no se acepten teclas inválidas en silencio."""
    while True:
        confirmar = input("\n¿Desea iniciar la simulación con estos procesos? (S/n) [S]: ").strip().lower()
        if confirmar in ("", "s", "si", "y", "yes"):
            return True
        if confirmar in ("n", "no"):
            return False
        print(">> [ERROR] Opción inválida. Ingrese 'S' para iniciar o 'N' para cancelar.")


def menu_principal() -> None:
    ajustar_ancho_consola()
    while True:
        limpiar_consola()
        print("=" * 75)
        print(" SIMULADOR DE ASIGNACIÓN DE MEMORIA (BEST-FIT) Y PLANIFICACIÓN (SRTF)")
        print(" Cátedra Sistemas Operativos - UTN FRRe")
        print("=" * 75)
        print(" 1. Cargar archivo de la carpeta")
        print(" 2. Cargar procesos manual por consola")
        print(" 3. Usar dataset de ejemplo")
        print(" 4. Salir")
        print("-" * 75)

        opcion = input("Seleccione una opción (1-4): ").strip()
        procesos_a_ejecutar = None

        if opcion == "1":
            procesos_a_ejecutar = cargar_desde_archivo()
        elif opcion == "2":
            procesos_a_ejecutar = cargar_manual_consola()
        elif opcion == "3":
            print("\n>> Cargando dataset didáctico de ejemplo...")
            procesos_a_ejecutar = obtener_dataset_ejemplo()
        elif opcion in ("4", "q", "salir", "exit"):
            print("\n>> ¡Hasta luego!\n")
            sys.exit(0)
        else:
            print("\n>> [ERROR] Opción no reconocida. Ingrese un número del 1 al 4.")
            input("Presione [ENTER] para volver al menú principal... ")
            continue

        if procesos_a_ejecutar:
            mostrar_tabla_procesos_cargados(procesos_a_ejecutar)
            if _confirmar_inicio():
                limpiar_consola()
                ejecutar_simulacion_interactiva(Simulador(procesos_a_ejecutar))
                input("\nPresione [ENTER] para volver al menú principal... ")
            else:
                print("\n>> Simulación cancelada.")
                input("Presione [ENTER] para volver al menú principal... ")


if __name__ == "__main__":
    try:
        if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
            ajustar_ancho_consola()
            nombre_cli = os.path.basename(sys.argv[1].strip().strip("'\""))
            procesos_cli = cargar_desde_archivo(nombre_cli)
            if procesos_cli:
                mostrar_tabla_procesos_cargados(procesos_cli)
                ejecutar_simulacion_interactiva(Simulador(procesos_cli))
                sys.exit(0)
            sys.exit(1)
        menu_principal()
    except (KeyboardInterrupt, EOFError):
        print("\n\n>> Ejecución finalizada por el usuario.")
        sys.exit(0)