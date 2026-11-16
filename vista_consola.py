"""
Interfaz de consola (ASCII): tableros, diagrama de Gantt, reportes,
exportación a .txt y 3 modos de ejecución:
  1. Paso a paso por tick ([ENTER])
  2. Paso a paso por cada evento relevante ('e')
  3. Automático con retardo visual ('a')
"""

import os
import time
from datetime import datetime
from typing import List, Optional

from cargador import obtener_directorio_ejecutable
from memoria import GestorMemoria
from modelos import Proceso
from simulador import Simulador


def generar_tabla_memoria_ascii(
    gestor: GestorMemoria,
    procesos_esperando: Optional[List[Proceso]] = None,
) -> str:
    """
    Genera la tabla ASCII de particiones con:
    Partición | Comienzo | Tamaño | Proceso | Frag. Interna | Frag. Externa
    """
    existe_frag = gestor.hay_fragmentacion_externa(procesos_esperando)
    lineas = []
    sep = "+------------+-----------+--------+------------------+---------------+---------------+"
    cab = "| Partición  | Comienzo  | Tamaño | Proceso Asignado | Frag. Interna | Frag. Externa |"
    lineas.append(sep)
    lineas.append(cab)
    lineas.append(sep)

    for p in gestor.particiones:
        if p.es_so:
            id_col = f"{p.id_particion} (SO)"
            proc_col = "SO"
            frag_int_col = "0 KB"
            frag_ext_col = "0 KB"
        elif p.libre:
            id_col = f"{p.id_particion} (Hueco)"
            proc_col = "[LIBRE]"
            frag_int_col = "0 KB"
            frag_ext_col = f"{p.calcular_fragmentacion_externa(existe_frag)} KB"
        else:
            id_col = f"{p.id_particion}"
            proc_col = f"{p.proceso.pid}"
            frag_int_col = f"{p.fragmentacion_interna} KB"
            frag_ext_col = "0 KB"

        fila = (
            f"| {id_col:<10} | {f'{p.base}K':<9} | {f'{p.tamano}K':<6} | "
            f"{proc_col:<16} | {frag_int_col:<13} | {frag_ext_col:<13} |"
        )
        lineas.append(fila)

    lineas.append(sep)
    return "\n".join(lineas)


def generar_barra_memoria_ascii(gestor: GestorMemoria, ancho: int = 55) -> str:
    """Genera una barra proporcional visual de la RAM de 550 KB."""
    segmentos = []
    for p in gestor.particiones:
        chars = max(1, round((p.tamano / gestor.TAMANO_TOTAL) * ancho))
        etiqueta = "SO" if p.es_so else ("." if p.libre else p.proceso.pid)
        if len(etiqueta) >= chars:
            contenido = etiqueta[:chars]
        else:
            relleno = "." if p.libre else " "
            contenido = etiqueta.center(chars, relleno)
        segmentos.append(contenido)
    return "[" + "|".join(segmentos) + "]"


def formatear_tablero(simulador: Simulador, eventos: List[str]) -> str:
    """Construye el texto completo del tablero ASCII en el tick actual."""
    t = simulador.reloj
    sep_ancho = 88
    linea_doble = "=" * sep_ancho
    lista_eventos = eventos if eventos else ["Ciclo de ejecución normal (sin eventos)"]
    out: List[str] = []

    out.append("\n" + linea_doble)
    out.append(f" RELOJ: t = {t} unidades de tiempo")
    out.append(linea_doble)

    out.append(" DETALLE DE ACCIONES EN ESTE INSTANTE:")
    for idx_ev, ev in enumerate(lista_eventos, start=1):
        out.append(f"   [{idx_ev}] {ev}")
    out.append("-" * sep_ancho)

    if simulador.planificador.proceso_ejecucion is not None:
        p_cpu = simulador.planificador.proceso_ejecucion
        out.append(f" CPU ACTUAL: [{p_cpu.pid} (Restante: {p_cpu.tiempo_restante} / Total: {p_cpu.tiempo_irrupcion})]")
    else:
        out.append(" CPU ACTUAL: [OCIOSA]")
    out.append("")

    procesos_esperando_mem = simulador.planificador.cola_suspendidos
    out.append(" TABLA DE PARTICIONES DE MEMORIA (550 KB Total | 100 KB SO + 450 KB Usuario):")
    out.append(f" Mapa visual: {generar_barra_memoria_ascii(simulador.gestor_memoria)}")
    out.append(generar_tabla_memoria_ascii(simulador.gestor_memoria, procesos_esperando_mem))

    libre_total = simulador.gestor_memoria.memoria_libre_total()
    huecos = simulador.gestor_memoria.huecos_libres()
    cant_huecos = len(huecos)
    existe_frag = simulador.gestor_memoria.hay_fragmentacion_externa(procesos_esperando_mem)
    frag_total = libre_total if existe_frag else 0

    if existe_frag:
        mayor_hueco = simulador.gestor_memoria.mayor_hueco_disponible()
        afectados = [
            f"{p.pid} ({p.tamano} KB)"
            for p in procesos_esperando_mem
            if mayor_hueco < p.tamano <= libre_total
        ]
        detalle_frag = f"{frag_total} KB (Discontinua en {cant_huecos} huecos; afecta a: {', '.join(afectados)})"
    else:
        detalle_frag = "0 KB (Ningún proceso en espera bloqueado por memoria fragmentada)"

    out.append(
        f" Memoria Libre Total: {libre_total} KB ({cant_huecos} hueco(s)) | "
        f"Fragmentación Externa Total: {detalle_frag}"
    )
    out.append("")

    p_exec_str = (
        f"[{simulador.planificador.proceso_ejecucion.pid}]"
        if simulador.planificador.proceso_ejecucion
        else "[NINGUNO]"
    )
    p_listos_str = (
        " ".join(f"[{p.pid} (Restante: {p.tiempo_restante})]" for p in simulador.planificador.cola_listos)
        if simulador.planificador.cola_listos
        else "[VACÍA]"
    )
    p_susp_str = (
        " ".join(
            f"[{p.pid} (Tamaño: {p.tamano}K - Esperando hueco contiguo)]"
            for p in simulador.planificador.cola_suspendidos
        )
        if simulador.planificador.cola_suspendidos
        else "[VACÍA]"
    )
    p_nuevos_str = (
        " ".join(f"[{p.pid} (En espera de cupo)]" for p in simulador.cola_nuevos_espera)
        if simulador.cola_nuevos_espera
        else "[VACÍA]"
    )

    out.append(
        f" COLAS DEL SISTEMA (Total activos: {simulador.total_activos} / Máx: {simulador.LIMITE_MULTIPROGRAMACION}):"
    )
    out.append(f" - Nuevos:             {p_nuevos_str}")
    out.append(f" - En Ejecución:       {p_exec_str}")
    out.append(f" - Listos (Memoria):   {p_listos_str}")
    out.append(f" - Listos/Suspendidos: {p_susp_str}")
    out.append(linea_doble)
    return "\n".join(out)


def renderizar_tablero(simulador: Simulador, eventos: List[str]) -> str:
    """Imprime el tablero en consola y retorna el texto generado."""
    texto = formatear_tablero(simulador, eventos)
    print(texto)
    return texto


def formatear_diagrama_gantt(historial_gantt: List[tuple]) -> str:
    """Construye el diagrama de Gantt en ASCII agrupando ticks consecutivos del mismo PID."""
    if not historial_gantt:
        return ""

    bloques = []
    inicio_actual, pid_actual = historial_gantt[0]
    for tick, pid in historial_gantt[1:]:
        if pid != pid_actual:
            bloques.append((inicio_actual, tick, pid_actual))
            inicio_actual = tick
            pid_actual = pid
    bloques.append((inicio_actual, historial_gantt[-1][0] + 1, pid_actual))

    linea_celdas = "|"
    linea_tiempos = ""
    for ini, fin, pid in bloques:
        etiqueta = f" {pid} "
        ancho = max(len(etiqueta), len(str(fin)) + 2)
        linea_celdas += etiqueta.center(ancho) + "|"
        linea_tiempos += f"{ini:<{ancho + 1}}"
    linea_tiempos += str(bloques[-1][1])

    borde = "+" + "+".join("-" * len(c) for c in linea_celdas.strip("|").split("|")) + "+"
    return "\n".join([
        "\nDIAGRAMA DE GANTT (USO DE CPU):",
        borde,
        linea_celdas,
        borde,
        linea_tiempos,
    ])


def formatear_reporte_final(simulador: Simulador) -> str:
    """Construye el Reporte Estadístico Final con Gantt, métricas individuales y globales."""
    sep = "=" * 95
    out: List[str] = [
        "\n" + sep,
        " " * 28 + "REPORTE ESTADÍSTICO FINAL DE SIMULACIÓN",
        sep,
    ]

    gantt = formatear_diagrama_gantt(simulador.historial_gantt)
    if gantt:
        out.append(gantt)

    procesos_ordenados = sorted(simulador.procesos_terminados, key=lambda p: (p.tiempo_arribo, p.pid))
    tabla_sep = "+---------+--------+--------+--------+--------+--------+--------+----------+"
    tabla_cab = "| Proceso | Ta     | Ti     | T.Ini  | Tf     | Tr     | Te     | T.Resp   |"
    out.append("\n" + tabla_sep)
    out.append(tabla_cab)
    out.append(tabla_sep)

    for p in procesos_ordenados:
        t_ini = p.tiempo_inicio if p.tiempo_inicio is not None else "-"
        t_fin = p.tiempo_fin if p.tiempo_fin is not None else "-"
        tr = p.tiempo_retorno if p.tiempo_retorno is not None else 0
        te = p.tiempo_espera if p.tiempo_espera is not None else 0
        t_resp = p.tiempo_respuesta if p.tiempo_respuesta is not None else 0

        out.append(
            f"| {p.pid:<7} | {p.tiempo_arribo:<6} | {p.tiempo_irrupcion:<6} | "
            f"{t_ini:<6} | {t_fin:<6} | {tr:<6} | {te:<6} | {t_resp:<8} |"
        )

    out.append(tabla_sep)

    m = simulador.calcular_metricas_globales()
    out.append("\nESTADÍSTICAS GLOBALES DEL SISTEMA:")
    out.append(f" * Total de Procesos Terminados:         {int(m['total_terminados'])}")
    out.append(f" * Tiempo Total de Simulación:           {int(m['tiempo_total'])} unidades de tiempo")
    out.append(f" * Tiempo de Retorno Promedio (Tr prom): {m['tr_promedio']:.2f} u.t.")
    out.append(f" * Tiempo de Espera Promedio (Te prom):  {m['te_promedio']:.2f} u.t.")
    out.append(f" * Tiempo de Respuesta Prom. (T.Resp):   {m['tresp_promedio']:.2f} u.t.")
    out.append(f" * Uso de CPU:                           {m['uso_cpu_pct']:.2f}%")
    out.append(f" * Rendimiento (Throughput):             {m['throughput']:.4f} procesos / u.t.")
    out.append(sep + "\n")
    return "\n".join(out)


def mostrar_reporte_final(simulador: Simulador) -> str:
    """Imprime el Reporte Estadístico Final en consola y retorna el texto generado."""
    texto = formatear_reporte_final(simulador)
    print(texto)
    return texto


def exportar_traza_txt(traza_texto: List[str]) -> Optional[str]:
    """Guarda la traza completa y el reporte final en un archivo .txt en la carpeta del simulador."""
    directorio = obtener_directorio_ejecutable()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre = f"reporte_simulacion_{timestamp}.txt"
    ruta = os.path.join(directorio, nombre)
    try:
        with open(ruta, "w", encoding="utf-8") as f:
            f.write("\n".join(traza_texto))
        print(f">> Reporte exportado exitosamente en: {ruta}")
        return ruta
    except Exception as e:
        print(f">> ERROR al exportar el reporte: {e}")
        return None


def mostrar_tabla_procesos_cargados(procesos: List[Proceso]) -> None:
    print("\nPROCESOS PREPARADOS PARA LA SIMULACIÓN:")
    print("+---------+--------+---------------+--------------------+")
    print("| Proceso | Tamaño | Tiempo Arribo | Tiempo Irrupción   |")
    print("+---------+--------+---------------+--------------------+")
    for p in sorted(procesos, key=lambda item: (item.tiempo_arribo, item.pid)):
        print(f"| {p.pid:<7} | {p.tamano:<4}KB | {p.tiempo_arribo:<13} | {p.tiempo_irrupcion:<18} |")
    print("+---------+--------+---------------+--------------------+")


def seleccionar_modo_inicial() -> str:
    """Permite elegir el modo de ejecución antes de iniciar la simulación."""
    print("\nSeleccione el modo de ejecución:")
    print("  1. Paso a paso por tick ([ENTER] en cada unidad de tiempo)")
    print("  2. Paso a paso por evento (pausa en arribos, desalojos y terminaciones)")
    print("  3. Automático (avance continuo con retardo visual; Ctrl+C para pausar)")
    opcion = input("Modo [1/2/3, por defecto 1]: ").strip()
    if opcion == "2":
        return "eventos"
    if opcion == "3":
        return "auto"
    return "ticks"


def ejecutar_simulacion_interactiva(simulador: Simulador) -> None:
    """Bucle interactivo en consola con los 3 modos de ejecución y exportación opcional a .txt."""
    modo = seleccionar_modo_inicial()
    print(f"\n>> Simulación iniciada en modo: {modo.upper()}.")
    traza_texto: List[str] = []

    while not simulador.finalizado and simulador.reloj < simulador.limite_ticks:
        eventos = simulador.ejecutar_paso()

        es_tick_con_evento = bool(eventos)
        debe_mostrar = (modo != "eventos") or es_tick_con_evento or simulador.finalizado

        if debe_mostrar:
            traza_texto.append(renderizar_tablero(simulador, eventos))

        if simulador.finalizado:
            break

        if modo == "auto":
            try:
                time.sleep(0.5)
            except KeyboardInterrupt:
                print("\n>> Pausa manual activada. Cambiando a modo paso a paso por tick.")
                modo = "ticks"
        elif debe_mostrar:
            try:
                opcion = input(
                    ">> [ENTER] tick | 'e' por eventos | 'a' automático | 's' salir: "
                ).strip().lower()
                if opcion in ("a", "auto"):
                    modo = "auto"
                    print(">> Modo automático activado (Ctrl+C para pausar).")
                elif opcion in ("e", "evento", "eventos"):
                    modo = "eventos"
                elif opcion in ("s", "salir", "exit"):
                    print(">> Simulación interrumpida por el usuario.")
                    return
                else:
                    modo = "ticks"
            except (KeyboardInterrupt, EOFError):
                print("\n>> Simulación pausada.")
                modo = "ticks"

        simulador.avanzar_reloj()

    if simulador.finalizado:
        traza_texto.append(
            renderizar_tablero(simulador, ["SIMULACIÓN COMPLETADA: Todos los procesos finalizaron exitosamente."])
        )
        traza_texto.append(mostrar_reporte_final(simulador))
        try:
            exportar = input("¿Desea exportar la traza y el reporte final a un archivo .txt? (s/N) [N]: ").strip().lower()
            if exportar in ("s", "si", "y", "yes"):
                exportar_traza_txt(traza_texto)
        except (KeyboardInterrupt, EOFError):
            pass
    else:
        print(
            f"\n>> ADVERTENCIA: La simulación alcanzó el límite de seguridad de "
            f"{simulador.limite_ticks} ticks sin finalizar todos los procesos."
        )