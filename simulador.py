#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
SIMULADOR DE ASIGNACIÓN DE MEMORIA Y PLANIFICACIÓN DE PROCESOS
Cátedra: Sistemas Operativos - UTN FRRe (Facultad Regional Resistencia)
================================================================================
Características implementadas:
- Gestión de Memoria:
    * Total RAM: 550 KB.
    * Sistema Operativo: 100 KB fijos (direcciones 0 a 99 KB, inamovible).
    * Espacio Usuario: 450 KB (direcciones 100 a 549 KB).
    * Esquema: Particiones Variables Dinámicas (MVT).
    * Política de Asignación: Best-Fit (Mejor Ajuste).
    * RESTRICCIÓN ESTRICTA: SIN COMPACTACIÓN DE MEMORIA.
    * Liberación con Coalescencia Adyacente (fusión local con vecinos libres).
    * Cálculo y detección explícita de Fragmentación Externa.
- Planificación de CPU:
    * Algoritmo: SRTF (Shortest Remaining Time First) - Apropiativo con desalojo.
    * Condición de desalojo estricto: tiempo_restante < ejecucion.tiempo_restante.
    * Grado de Multiprogramación: máx. 5 procesos activos en el sistema:
      len(Ejecución) + len(Cola_Listos) + len(Cola_Listos_Suspendidos) <= 5.
- Estados de Procesos:
    * NUEVO -> LISTO / LISTO Y SUSPENDIDO -> EJECUCIÓN -> TERMINADO.
- Carga de Procesos:
    * Por defecto se ejecuta con 'procesos.csv' ubicado en la misma carpeta que el ejecutable.
- Modo de Ejecución:
    * Paso a paso interactivo por eventos o por ticks de reloj.
- Salida Visual:
    * Tablero limpio con formateo ASCII en cada evento relevante.
    * Reporte estadístico final detallado (Ta, Ti, Tf, Tr, Te, promedios y Throughput).
================================================================================
"""

import sys
import os
import time
import csv
from enum import Enum
from dataclasses import dataclass
from typing import List, Optional, Tuple

# Configurar salida estándar UTF-8 si es posible
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


# ==============================================================================
# ENUMERACIONES Y MODELO DE DOMINIO
# ==============================================================================

class EstadoProceso(Enum):
    NUEVO = "NUEVO"
    LISTO = "LISTO"
    LISTO_SUSPENDIDO = "LISTO Y SUSPENDIDO"
    EJECUCION = "EJECUCION"
    TERMINADO = "TERMINADO"


@dataclass
class Proceso:
    """
    Representa un Proceso (PCB simplificado) en el sistema operativo.
    """
    pid: str
    tamano: int                   # Tamaño en KB
    tiempo_arribo: int            # Tiempo de arribo (Ta)
    tiempo_irrupcion: int         # Tiempo total de CPU requerido (Ti / Burst)
    tiempo_restante: int          # Tiempo de CPU pendiente por ejecutar
    estado: EstadoProceso = EstadoProceso.NUEVO
    tiempo_inicio: Optional[int] = None       # Instante en que tocó la CPU por 1ra vez
    tiempo_fin: Optional[int] = None          # Instante en que finalizó (Tf)
    particion_id: Optional[int] = None        # ID de la partición asignada en RAM
    direccion_base: Optional[int] = None      # Dirección de memoria física inicial (KB)

    @property
    def tiempo_retorno(self) -> Optional[int]:
        """Tiempo de Retorno (Tr = Tf - Ta)."""
        if self.tiempo_fin is not None:
            return self.tiempo_fin - self.tiempo_arribo
        return None

    @property
    def tiempo_espera(self) -> Optional[int]:
        """Tiempo de Espera (Te = Tr - Ti)."""
        tr = self.tiempo_retorno
        if tr is not None:
            return tr - self.tiempo_irrupcion
        return None

    def __repr__(self) -> str:
        return f"{self.pid}({self.tamano}K, Rest:{self.tiempo_restante})"


# ==============================================================================
# GESTIÓN DE MEMORIA - PARTICIONES VARIABLES Y BEST-FIT
# ==============================================================================

@dataclass
class Particion:
    """
    Representa una partición o hueco contiguo en memoria física.
    """
    id_particion: int
    base: int                     # Dirección de inicio en KB (0 .. 549)
    tamano: int                   # Tamaño de la partición en KB
    proceso: Optional[Proceso] = None  # Proceso asignado, o None si está libre
    es_so: bool = False           # True si está reservada para el Sistema Operativo

    @property
    def libre(self) -> bool:
        """Indica si la partición es un hueco disponible para asignar a usuarios."""
        return self.proceso is None and not self.es_so

    @property
    def fragmentacion_externa(self) -> int:
        """
        En particiones variables no hay fragmentación interna.
        El tamaño de cualquier hueco libre constituye fragmentación externa potencial.
        """
        return self.tamano if self.libre else 0

    @property
    def limite_superior(self) -> int:
        """Última dirección ocupada por la partición (inclusiva)."""
        return self.base + self.tamano - 1


class GestorMemoria:
    """
    Administrador de Memoria Principal (550 KB totales).
    - 100 KB para SO (0 a 99 KB).
    - 450 KB para usuarios (100 a 549 KB).
    - Política de asignación: Best-Fit (Mejor Ajuste).
    - Sin compactación bajo ninguna circunstancia.
    - Fusión adyacente (coalescencia de vecinos) al liberar.
    """
    TAMANO_TOTAL = 550
    TAMANO_SO = 100
    TAMANO_USUARIO = 450
    BASE_USUARIO = 100

    def __init__(self):
        # Memoria inicial: Partición 0 (SO) y Partición 1 (Hueco de usuario de 450 KB)
        self.particiones: List[Particion] = [
            Particion(id_particion=0, base=0, tamano=self.TAMANO_SO, proceso=None, es_so=True),
            Particion(id_particion=1, base=self.BASE_USUARIO, tamano=self.TAMANO_USUARIO, proceso=None, es_so=False)
        ]

    def _reindexar(self):
        """Mantiene los IDs de partición ordenados consecutivamente de 0 a N."""
        for idx, part in enumerate(self.particiones):
            part.id_particion = idx
            if part.proceso:
                part.proceso.particion_id = idx

    def memoria_libre_total(self) -> int:
        """Suma de todos los huecos libres de usuario en KB."""
        return sum(p.tamano for p in self.particiones if p.libre)

    def mayor_hueco_disponible(self) -> int:
        """Tamaño del mayor hueco contiguo libre en KB."""
        huecos = [p.tamano for p in self.particiones if p.libre]
        return max(huecos) if huecos else 0

    def huecos_libres(self) -> List[Particion]:
        """Lista de todas las particiones libres."""
        return [p for p in self.particiones if p.libre]

    def asignar_best_fit(self, proceso: Proceso) -> Tuple[bool, str]:
        """
        Busca el hueco contiguo libre de tamaño >= proceso.tamano que deje el menor remanente.
        Si no cabe, diagnostica si se debe a Fragmentación Externa o falta total de memoria.
        Si cabe, divide el hueco si es mayor, dejando el remanente contiguo.
        """
        candidatos = [
            (idx, p) for idx, p in enumerate(self.particiones)
            if p.libre and p.tamano >= proceso.tamano
        ]

        if not candidatos:
            libre_total = self.memoria_libre_total()
            mayor_hueco = self.mayor_hueco_disponible()
            if libre_total >= proceso.tamano:
                detalle = (
                    f"EVIDENCIA DE FRAGMENTACIÓN EXTERNA: El proceso requiere {proceso.tamano} KB. "
                    f"Hay {libre_total} KB libres en total, pero dispersos en huecos discontinuos "
                    f"(el mayor hueco disponible es de {mayor_hueco} KB). "
                    f"Al estar prohibida la compactación, el proceso NO puede ingresar a RAM."
                )
            else:
                detalle = (
                    f"MEMORIA INSUFICIENTE: Requiere {proceso.tamano} KB y la memoria libre total "
                    f"es de solo {libre_total} KB."
                )
            return False, detalle

        # Criterio Best-Fit: menor desperdicio (particion.tamano - proceso.tamano).
        # En caso de empate, elige la de menor dirección base.
        candidatos.sort(key=lambda item: (item[1].tamano - proceso.tamano, item[1].base))
        idx_elegido, particion_elegida = candidatos[0]

        base_asignada = particion_elegida.base

        if particion_elegida.tamano == proceso.tamano:
            # Ajuste exacto: la partición completa se asigna al proceso
            particion_elegida.proceso = proceso
            proceso.particion_id = particion_elegida.id_particion
            proceso.direccion_base = base_asignada
            detalle = (
                f"Asignado en Partición {particion_elegida.id_particion} "
                f"[{base_asignada}K - {base_asignada + proceso.tamano - 1}K] (Ajuste exacto, sin remanente)."
            )
        else:
            # División de partición: la parte requerida se asigna y el resto queda como hueco contiguo
            remanente = particion_elegida.tamano - proceso.tamano
            nueva_base_hueco = base_asignada + proceso.tamano

            particion_elegida.tamano = proceso.tamano
            particion_elegida.proceso = proceso
            proceso.direccion_base = base_asignada

            hueco_remanente = Particion(
                id_particion=0,
                base=nueva_base_hueco,
                tamano=remanente,
                proceso=None,
                es_so=False
            )
            self.particiones.insert(idx_elegido + 1, hueco_remanente)
            self._reindexar()
            detalle = (
                f"Asignado en Partición {proceso.particion_id} [{base_asignada}K - {nueva_base_hueco - 1}K] "
                f"({proceso.tamano} KB). Hueco libre remanente: {remanente} KB en "
                f"[{nueva_base_hueco}K - {nueva_base_hueco + remanente - 1}K]."
            )

        return True, detalle

    def liberar_memoria(self, proceso: Proceso) -> Tuple[bool, str]:
        """
        Libera la partición asignada al proceso y realiza ÚNICAMENTE coalescencia
        con vecinos inmediatos (anterior y/o posterior) si están libres.
        NO realiza compactación ni reubicación de otros procesos.
        """
        idx_encontrado = None
        for idx, p in enumerate(self.particiones):
            if p.proceso == proceso:
                idx_encontrado = idx
                break

        if idx_encontrado is None:
            return False, f"El proceso {proceso.pid} no se encontraba cargado en memoria."

        part = self.particiones[idx_encontrado]
        tam_liberado = part.tamano
        base_liberada = part.base
        part.proceso = None
        proceso.particion_id = None
        proceso.direccion_base = None

        fusiones = []

        # 1. Verificar coalescencia con vecino anterior (si no es el SO y está libre)
        if idx_encontrado > 0:
            anterior = self.particiones[idx_encontrado - 1]
            if anterior.libre:
                fusiones.append(f"vecino anterior [base {anterior.base}K, tamaño {anterior.tamano}K]")
                anterior.tamano += part.tamano
                self.particiones.pop(idx_encontrado)
                part = anterior
                idx_encontrado -= 1

        # 2. Verificar coalescencia con vecino posterior (si está libre)
        if idx_encontrado + 1 < len(self.particiones):
            posterior = self.particiones[idx_encontrado + 1]
            if posterior.libre:
                fusiones.append(f"vecino posterior [base {posterior.base}K, tamaño {posterior.tamano}K]")
                part.tamano += posterior.tamano
                self.particiones.pop(idx_encontrado + 1)

        self._reindexar()

        if fusiones:
            detalle = (
                f"Liberada partición de {proceso.pid} ({tam_liberado} KB en dir. {base_liberada}K). "
                f"Coalescencia natural con {' y '.join(fusiones)}. "
                f"Nuevo bloque contiguo libre: {part.tamano} KB en [{part.base}K - {part.limite_superior}K]."
            )
        else:
            detalle = (
                f"Liberada partición de {proceso.pid} ({tam_liberado} KB en dir. {base_liberada}K). "
                f"No posee vecinos libres adyacentes; el hueco se mantiene aislado."
            )

        return True, detalle

    def generar_tabla_ascii(self) -> str:
        """
        Genera la tabla formateada en ASCII con las columnas requeridas:
        Partición | Comienzo | Tamaño | Proceso Asignado | Frag. Externa (Hueco)
        """
        lineas = []
        sep = "+------------+-----------+--------+------------------+-----------------------+"
        cab = "| Partición  | Comienzo  | Tamaño | Proceso Asignado | Frag. Externa (Hueco) |"
        lineas.append(sep)
        lineas.append(cab)
        lineas.append(sep)

        for p in self.particiones:
            if p.es_so:
                id_col = f"{p.id_particion} (SO)"
                proc_col = "SO"
                frag_col = "0 KB"
            elif p.libre:
                id_col = f"{p.id_particion} (Hueco)"
                proc_col = "[LIBRE]"
                frag_col = f"{p.tamano} KB"
            else:
                id_col = f"{p.id_particion}"
                proc_col = f"{p.proceso.pid}"
                frag_col = "0 KB"

            comienzo_col = f"{p.base}K"
            tamano_col = f"{p.tamano}K"

            fila = (
                f"| {id_col:<10} | {comienzo_col:<9} | {tamano_col:<6} | "
                f"{proc_col:<16} | {frag_col:<21} |"
            )
            lineas.append(fila)

        lineas.append(sep)
        return "\n".join(lineas)


# ==============================================================================
# PLANIFICADOR DE CPU - SRTF (SHORTEST REMAINING TIME FIRST)
# ==============================================================================

class PlanificadorSRTF:
    """
    Planificador de corto plazo bajo política SRTF (apropiativo / con desalojo).
    Mantiene:
    - Cola de Listos (en Memoria Principal).
    - Cola de Listos y Suspendidos (en Swap / esperando memoria contigua).
    - Proceso actualmente en Ejecución (a lo sumo 1).
    """

    def __init__(self):
        self.cola_listos: List[Proceso] = []
        self.cola_suspendidos: List[Proceso] = []
        self.proceso_ejecucion: Optional[Proceso] = None

    def desaloja_a_ejecucion(self, candidato: Proceso) -> bool:
        """
        Condición de desalojo estricta:
        El candidato debe tener un tiempo restante estrictamente menor que el proceso en CPU.
        """
        if self.proceso_ejecucion is None:
            return False
        return candidato.tiempo_restante < self.proceso_ejecucion.tiempo_restante

    def seleccionar_siguiente(self) -> Optional[Proceso]:
        """
        Selecciona el proceso con menor tiempo restante de la Cola de Listos.
        En caso de empate en tiempo restante, desempata por tiempo de arribo (FIFO) y luego por PID.
        """
        if not self.cola_listos:
            return None
        self.cola_listos.sort(key=lambda p: (p.tiempo_restante, p.tiempo_arribo, p.pid))
        return self.cola_listos.pop(0)


# ==============================================================================
# SIMULADOR PRINCIPAL Y COORDINADOR
# ==============================================================================

class Simulador:
    """
    Coordinador central del ciclo de simulación paso a paso.
    Gobierna el reloj del sistema, las admisiones, la memoria y la CPU.
    """
    LIMITE_MULTIPROGRAMACION = 5

    def __init__(self, procesos: List[Proceso]):
        # Copia de seguridad y ordenamiento inicial por arribo
        self.procesos_iniciales: List[Proceso] = [
            Proceso(
                pid=p.pid,
                tamano=p.tamano,
                tiempo_arribo=p.tiempo_arribo,
                tiempo_irrupcion=p.tiempo_irrupcion,
                tiempo_restante=p.tiempo_irrupcion,
                estado=EstadoProceso.NUEVO
            )
            for p in procesos
        ]
        self.procesos_pendientes_arribo: List[Proceso] = sorted(
            self.procesos_iniciales, key=lambda p: (p.tiempo_arribo, p.pid)
        )
        self.cola_nuevos_espera: List[Proceso] = []
        self.procesos_terminados: List[Proceso] = []
        self.total_procesos = len(self.procesos_iniciales)

        self.gestor_memoria = GestorMemoria()
        self.planificador = PlanificadorSRTF()
        self.reloj = 0

        # Control de interactividad
        self.modo_automatico = False

    @property
    def total_activos(self) -> int:
        """Total de procesos en el grado de multiprogramación (máx 5)."""
        en_cpu = 1 if self.planificador.proceso_ejecucion is not None else 0
        return en_cpu + len(self.planificador.cola_listos) + len(self.planificador.cola_suspendidos)

    @property
    def finalizado(self) -> bool:
        """La simulación concluye cuando todos los procesos han terminado."""
        return len(self.procesos_terminados) == self.total_procesos

    def ejecutar_paso(self) -> List[str]:
        """
        Ejecuta las transiciones y eventos correspondientes al instante de reloj actual (t).
        Retorna la lista de descripciones de eventos ocurridos en este instante.
        """
        eventos = []
        t = self.reloj

        # ----------------------------------------------------------------------
        # 1. EVALUAR TERMINACIÓN DEL PROCESO EN CPU
        # ----------------------------------------------------------------------
        if self.planificador.proceso_ejecucion is not None:
            if self.planificador.proceso_ejecucion.tiempo_restante == 0:
                p_fin = self.planificador.proceso_ejecucion
                p_fin.estado = EstadoProceso.TERMINADO
                p_fin.tiempo_fin = t
                self.procesos_terminados.append(p_fin)

                ok, msg_lib = self.gestor_memoria.liberar_memoria(p_fin)
                eventos.append(
                    f"TERMINACIÓN: Proceso {p_fin.pid} finalizó su ejecución en t={t} "
                    f"(Retorno Tr={p_fin.tiempo_retorno} u.t., Espera Te={p_fin.tiempo_espera} u.t.)."
                )
                eventos.append(f"LIBERACIÓN MEMORIA: {msg_lib}")
                self.planificador.proceso_ejecucion = None

        # ----------------------------------------------------------------------
        # 2. EVALUAR REINGRESO DE PROCESOS SUSPENDIDOS (DES-SUSPENSIÓN)
        # ----------------------------------------------------------------------
        # Como se liberó memoria, revisamos si algún proceso en Suspendido ahora cabe
        i = 0
        while i < len(self.planificador.cola_suspendidos):
            p_susp = self.planificador.cola_suspendidos[i]
            ok, msg_asig = self.gestor_memoria.asignar_best_fit(p_susp)
            if ok:
                self.planificador.cola_suspendidos.pop(i)
                p_susp.estado = EstadoProceso.LISTO
                self.planificador.cola_listos.append(p_susp)
                eventos.append(
                    f"DES-SUSPENSIÓN: Proceso {p_susp.pid} ({p_susp.tamano} KB) obtiene partición "
                    f"contigua en RAM y pasa al estado LISTO. {msg_asig}"
                )
            else:
                i += 1

        # ----------------------------------------------------------------------
        # 3. LLEGADA DE NUEVOS PROCESOS (Arribos en tiempo t)
        # ----------------------------------------------------------------------
        # Los procesos solo ingresan a la cola de nuevos a medida que el reloj alcanza su tiempo de arribo
        while self.procesos_pendientes_arribo and self.procesos_pendientes_arribo[0].tiempo_arribo <= t:
            p_arr = self.procesos_pendientes_arribo.pop(0)
            self.cola_nuevos_espera.append(p_arr)
            eventos.append(
                f"ARRIBO: Proceso {p_arr.pid} llega al sistema en t={t} "
                f"(Tamaño: {p_arr.tamano} KB, Ráfaga: {p_arr.tiempo_irrupcion} u.t.) -> Ingresa al estado NUEVO."
            )

        # ----------------------------------------------------------------------
        # 4. ADMISIÓN AL CUPO DE MULTIPROGRAMACIÓN (Máx 5 activos)
        # ----------------------------------------------------------------------
        while self.cola_nuevos_espera and self.total_activos < self.LIMITE_MULTIPROGRAMACION:
            p_adm = self.cola_nuevos_espera.pop(0)
            ok, msg_asig = self.gestor_memoria.asignar_best_fit(p_adm)
            if ok:
                p_adm.estado = EstadoProceso.LISTO
                self.planificador.cola_listos.append(p_adm)
                eventos.append(
                    f"ADMISIÓN -> LISTO: Proceso {p_adm.pid} admitido en cupo ({self.total_activos}/"
                    f"{self.LIMITE_MULTIPROGRAMACION}). {msg_asig}"
                )
            else:
                p_adm.estado = EstadoProceso.LISTO_SUSPENDIDO
                self.planificador.cola_suspendidos.append(p_adm)
                eventos.append(
                    f"ADMISIÓN -> LISTO Y SUSPENDIDO: Proceso {p_adm.pid} admitido en cupo ({self.total_activos}/"
                    f"{self.LIMITE_MULTIPROGRAMACION}), pero enviado a SWAP. {msg_asig}"
                )

        if self.cola_nuevos_espera:
            esperando_pids = [p.pid for p in self.cola_nuevos_espera]
            eventos.append(
                f"LÍMITE MULTIPROGRAMACIÓN: Cupo máximo alcanzado ({self.total_activos}/"
                f"{self.LIMITE_MULTIPROGRAMACION}). Procesos en espera de admisión: {esperando_pids}."
            )

        # ----------------------------------------------------------------------
        # 5. PLANIFICACIÓN SRTF: EVALUACIÓN DE DESALOJO O DESPACHO
        # ----------------------------------------------------------------------
        if self.planificador.proceso_ejecucion is not None:
            # Si hay alguien en ejecución, chequear si algún proceso en memoria tiene
            # tiempo restante estrictamente menor
            if self.planificador.cola_listos:
                menor_en_listos = min(
                    self.planificador.cola_listos,
                    key=lambda p: (p.tiempo_restante, p.tiempo_arribo, p.pid)
                )
                if menor_en_listos.tiempo_restante < self.planificador.proceso_ejecucion.tiempo_restante:
                    desalojado = self.planificador.proceso_ejecucion
                    desalojado.estado = EstadoProceso.LISTO
                    self.planificador.cola_listos.append(desalojado)

                    self.planificador.cola_listos.remove(menor_en_listos)
                    self.planificador.proceso_ejecucion = menor_en_listos
                    menor_en_listos.estado = EstadoProceso.EJECUCION
                    if menor_en_listos.tiempo_inicio is None:
                        menor_en_listos.tiempo_inicio = t

                    eventos.append(
                        f"DESALOJO POR SRTF: Proceso {menor_en_listos.pid} (Restante: {menor_en_listos.tiempo_restante} u.t.) "
                        f"desaloja de la CPU a {desalojado.pid} (Restante: {desalojado.tiempo_restante} u.t.). "
                        f"{desalojado.pid} regresa a la Cola de Listos."
                    )
        else:
            # CPU Ociosa: Seleccionar el proceso más corto de la Cola de Listos
            nuevo_cpu = self.planificador.seleccionar_siguiente()
            if nuevo_cpu is not None:
                self.planificador.proceso_ejecucion = nuevo_cpu
                nuevo_cpu.estado = EstadoProceso.EJECUCION
                if nuevo_cpu.tiempo_inicio is None:
                    nuevo_cpu.tiempo_inicio = t
                eventos.append(
                    f"DESPACHO DE CPU: Proceso {nuevo_cpu.pid} asignado a CPU "
                    f"(Restante: {nuevo_cpu.tiempo_restante} / Total: {nuevo_cpu.tiempo_irrupcion} u.t.)."
                )
            else:
                if self.planificador.cola_suspendidos:
                    eventos.append(
                        "CPU OCIOSA: No hay procesos en Cola de Listos en memoria principal. "
                        "(Hay procesos en espera en Cola de Suspendidos por falta de hueco contiguo)."
                    )
                elif not self.finalizado:
                    eventos.append("CPU OCIOSA: No hay procesos listos para ejecutar en este instante.")

        return eventos

    def avanzar_reloj(self):
        """Avanza el reloj en 1 unidad de tiempo y consume 1 u.t. de CPU si está ocupada."""
        if self.planificador.proceso_ejecucion is not None:
            self.planificador.proceso_ejecucion.tiempo_restante -= 1
        self.reloj += 1

    def renderizar_tablero(self, eventos: List[str]):
        """
        Imprime en pantalla la visualización ASCII solicitada con el estado completo del sistema.
        """
        t = self.reloj
        sep_ancho = 80
        linea_doble = "=" * sep_ancho

        evento_resumen = eventos[0] if eventos else "Ciclo de ejecución normal"
        if len(eventos) > 1:
            evento_resumen = f"{eventos[0]} (+{len(eventos) - 1} evento(s))"

        # 1. Cabecera principal
        print("\n" + linea_doble)
        print(f" RELOJ: t = {t} unidades de tiempo | EVENTO: {evento_resumen}")
        print(linea_doble)

        # Si hubo múltiples eventos, listarlos explícitamente para máxima claridad educativa
        if len(eventos) > 1:
            print(" DETALLE DE ACCIONES EN ESTE INSTANTE:")
            for idx_ev, ev in enumerate(eventos, start=1):
                print(f"   [{idx_ev}] {ev}")
            print("-" * sep_ancho)

        # 2. Estado de CPU
        if self.planificador.proceso_ejecucion is not None:
            p_cpu = self.planificador.proceso_ejecucion
            print(f" CPU ACTUAL: [{p_cpu.pid} (Restante: {p_cpu.tiempo_restante} / Total: {p_cpu.tiempo_irrupcion})]")
        else:
            print(" CPU ACTUAL: [OCIOSA]")
        print()

        # 3. Tabla de Particiones de Memoria
        print(" TABLA DE PARTICIONES DE MEMORIA (550 KB Total | 100 KB SO + 450 KB Usuario):")
        print(self.gestor_memoria.generar_tabla_ascii())

        # Diagnóstico de Fragmentación Externa
        libre_total = self.gestor_memoria.memoria_libre_total()
        huecos = self.gestor_memoria.huecos_libres()
        cant_huecos = len(huecos)
        condicion_frag = "Discontinua" if cant_huecos > 1 else "Contigua"

        print(
            f" Memoria Libre Total: {libre_total} KB | "
            f"Fragmentación Externa Total: {libre_total} KB ({condicion_frag} en {cant_huecos} hueco(s))"
        )

        # Advertencia educativa sobre fragmentación externa
        mayor_hueco = self.gestor_memoria.mayor_hueco_disponible()
        if cant_huecos > 1 and mayor_hueco < libre_total:
            tam_ejemplo = mayor_hueco + 10
            if tam_ejemplo <= libre_total:
                print(
                    f" [AVISO DIDÁCTICO]: Si llega un proceso de {tam_ejemplo} KB, irá a SUSPENDIDO "
                    f"porque el mayor hueco es de {mayor_hueco} KB (alcanza el total pero no hay compactación)."
                )

        # Si hay procesos en suspendidos, explicar por qué no entran
        if self.planificador.cola_suspendidos:
            detalles_susp = []
            for ps in self.planificador.cola_suspendidos:
                if ps.tamano <= libre_total:
                    detalles_susp.append(
                        f"{ps.pid} ({ps.tamano} KB: hay {libre_total} KB libres pero dispersos en huecos < {ps.tamano} KB)"
                    )
                else:
                    detalles_susp.append(f"{ps.pid} (requiere {ps.tamano} KB > {libre_total} KB libres)")
            print(f" [ESTADO DE SUSPENDIDOS]: {'; '.join(detalles_susp)}.")

        print()

        # 4. Colas del Sistema
        p_exec_str = f"[{self.planificador.proceso_ejecucion.pid}]" if self.planificador.proceso_ejecucion else "[NINGUNO]"

        if self.planificador.cola_listos:
            p_listos_str = " ".join([f"[{p.pid} (Restante: {p.tiempo_restante})]" for p in self.planificador.cola_listos])
        else:
            p_listos_str = "[VACÍA]"

        if self.planificador.cola_suspendidos:
            p_susp_str = " ".join([f"[{p.pid} (Tamaño: {p.tamano}K - Esperando hueco contiguo)]" for p in self.planificador.cola_suspendidos])
        else:
            p_susp_str = "[VACÍA]"

        if self.cola_nuevos_espera:
            p_nuevos_str = " ".join([f"[{p.pid} (En espera de cupo)]" for p in self.cola_nuevos_espera])
        else:
            p_nuevos_str = "[VACÍA]"

        print(f" COLAS DEL SISTEMA (Total activos: {self.total_activos} / Máx: {self.LIMITE_MULTIPROGRAMACION}):")
        print(f" - Nuevos: {p_nuevos_str}")
        print(f" - En Ejecución:       {p_exec_str}")
        print(f" - Listos (Memoria):   {p_listos_str}")
        print(f" - Listos/Suspendidos: {p_susp_str}")
        print(linea_doble)

    def mostrar_reporte_final(self):
        """
        Genera e imprime el Reporte Estadístico Final con las métricas requeridas:
        Ta, Ti, Tf, Tr, Te, y promedios globales.
        """
        sep = "=" * 80
        print("\n" + sep)
        print(" " * 24 + "REPORTE ESTADÍSTICO FINAL DE SIMULACIÓN")
        print(sep)

        # Ordenar por PID para claridad
        procesos_ordenados = sorted(self.procesos_terminados, key=lambda p: (p.tiempo_arribo, p.pid))

        tabla_sep = "+---------+------------------+--------------------+---------------------+--------------------+-------------------+"
        tabla_cab = "| Proceso | T. Arribo (Ta)   | T. Irrupción (Ti)  | T. Finalización(Tf) | T. Retorno (Tr)    | T. Espera (Te)    |"
        print(tabla_sep)
        print(tabla_cab)
        print(tabla_sep)

        suma_tr = 0
        suma_te = 0
        n = len(procesos_ordenados)

        for p in procesos_ordenados:
            tr = p.tiempo_retorno if p.tiempo_retorno is not None else 0
            te = p.tiempo_espera if p.tiempo_espera is not None else 0
            suma_tr += tr
            suma_te += te

            fila = (
                f"| {p.pid:<7} | {p.tiempo_arribo:<16} | {p.tiempo_irrupcion:<18} | "
                f"{p.tiempo_fin:<19} | {tr:<18} | {te:<17} |"
            )
            print(fila)

        print(tabla_sep)

        prom_tr = (suma_tr / n) if n > 0 else 0.0
        prom_te = (suma_te / n) if n > 0 else 0.0
        tiempo_total_sim = self.reloj
        throughput = (n / tiempo_total_sim) if tiempo_total_sim > 0 else 0.0

        print("\nESTADÍSTICAS GLOBALES DEL SISTEMA:")
        print(f" * Total de Procesos Terminados:     {n}")
        print(f" * Tiempo Total de Simulación:       {tiempo_total_sim} unidades de tiempo")
        print(f" * Tiempo de Retorno Promedio (Tr prom): {prom_tr:.2f} u.t.")
        print(f" * Tiempo de Espera Promedio (Te prom):  {prom_te:.2f} u.t.")
        print(f" * Rendimiento (Throughput):         {throughput:.4f} procesos / u.t.")
        print(sep + "\n")

    def ejecutar_simulacion(self):
        """
        Bucle interactivo principal de la simulación.
        Pausa en cada paso/evento relevante y ofrece opciones de control al usuario.
        """
        print("\nINICIANDO SIMULACIÓN PASO A PASO...")
        print("Modos de control:")
        print("  - Presionar [ENTER]: Avanzar al siguiente instante / evento.")
        print("  - Ingresar 'a' o 'auto': Activar modo automático con retardo visual.")
        print("  - Ingresar 's' o 'salir': Interrumpir la simulación.")

        # Límite de seguridad para evitar bucles infinitos en configuraciones anómalas
        limite_ticks = 1000

        while not self.finalizado and self.reloj < limite_ticks:
            eventos = self.ejecutar_paso()
            self.renderizar_tablero(eventos)

            # Si ya finalizaron todos tras el paso en t, romper antes de pedir pausa
            if self.finalizado:
                break

            if not self.modo_automatico:
                try:
                    opcion = input(">> Presione [ENTER] para avanzar (o 'a' para automático, 's' para salir): ").strip().lower()
                    if opcion in ("a", "auto"):
                        self.modo_automatico = True
                        print(">> Modo automático activado. Presione Ctrl+C en cualquier momento para pausar.")
                    elif opcion in ("s", "salir", "exit"):
                        print(">> Simulación interrumpida por el usuario.")
                        return
                except (KeyboardInterrupt, EOFError):
                    print("\n>> Simulación pausada.")
                    self.modo_automatico = False
            else:
                try:
                    time.sleep(0.6)  # Retardo visual cómodo
                except KeyboardInterrupt:
                    print("\n>> Pausa manual activada. Volviendo al modo paso a paso.")
                    self.modo_automatico = False

            self.avanzar_reloj()

        # Última pantalla si concluyó
        if self.finalizado:
            # Evento final de cierre
            self.renderizar_tablero(["SIMULACIÓN COMPLETADA: Todos los procesos finalizaron exitosamente."])
            self.mostrar_reporte_final()


# ==============================================================================
# CARGA DE DATOS Y VALIDACIONES
# ==============================================================================

def validar_procesos(procesos: List[Proceso]) -> Tuple[bool, str]:
    """
    Aplica las reglas de negocio estrictas:
    - Máximo 10 procesos.
    - Ningún proceso > 450 KB (tamaño de espacio de usuario).
    - Valores numéricos estrictamente válidos (tamano > 0, arribo >= 0, irrupción > 0).
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
                f"de {GestorMemoria.TAMANO_USUARIO} KB (Memoria Total 550 KB - 100 KB SO). "
                f"Este proceso jamás podría ser alojado en memoria."
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
    Detecta y descarta automáticamente la fila de encabezado si existe.
    """
    procesos = []
    lector = csv.reader([l.strip() for l in lineas if l.strip() and not l.strip().startswith("#")])

    for nro_fila, fila in enumerate(lector, start=1):
        if not fila:
            continue
        # Descartar encabezado típico si está presente
        if nro_fila == 1 and any(h in fila[0].lower() for h in ("pid", "proceso", "id", "identificador")):
            continue

        if len(fila) < 4:
            raise ValueError(f"Fila {nro_fila} incompleta: se esperan 4 columnas (PID,Tamaño,Arribo,Irrupcion).")

        pid = fila[0].strip()
        try:
            tamano = int(fila[1].strip())
            arribo = int(fila[2].strip())
            irrupcion = int(fila[3].strip())
        except ValueError:
            raise ValueError(f"Fila {nro_fila} ('{pid}'): Los valores de Tamaño, Arribo e Irrupción deben ser enteros.")

        procesos.append(Proceso(
            pid=pid,
            tamano=tamano,
            tiempo_arribo=arribo,
            tiempo_irrupcion=irrupcion,
            tiempo_restante=irrupcion
        ))

    return procesos


def obtener_directorio_ejecutable() -> str:
    """
    Retorna la ruta del directorio donde se encuentra el archivo ejecutable o script.
    Soporta ejecutables compilados (.exe con PyInstaller/cx_Freeze) y ejecución directa (.py).
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    elif "__file__" in globals():
        return os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.getcwd())


def listar_archivos_carpeta() -> List[str]:
    """
    Retorna la lista de archivos CSV o TXT existentes en la carpeta del ejecutable/script.
    """
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
    """
    Toma únicamente el nombre del archivo (extrayendo el nombre base si se introdujo una ruta)
    y lo resuelve estrictamente dentro de la carpeta del ejecutable/script.
    Si el nombre no tiene extensión, intenta buscar agregando '.csv'.
    """
    directorio_base = obtener_directorio_ejecutable()
    nombre_base = os.path.basename(nombre_o_ruta.strip().strip("'\""))

    if not nombre_base:
        return None

    ruta_candidata = os.path.join(directorio_base, nombre_base)
    if os.path.exists(ruta_candidata):
        return ruta_candidata

    # Si no tiene extensión o no existe con ese nombre, probar agregando .csv
    if not nombre_base.lower().endswith((".csv", ".txt")):
        ruta_csv = os.path.join(directorio_base, f"{nombre_base}.csv")
        if os.path.exists(ruta_csv):
            return ruta_csv

    return ruta_candidata


def cargar_desde_archivo(nombre_archivo: Optional[str] = None) -> Optional[List[Proceso]]:
    """
    Carga procesos desde un archivo CSV o TXT ubicado SIEMPRE en la carpeta del simulador.
    El usuario solo debe proporcionar el nombre del archivo (ej. 'procesos.csv').
    """
    directorio_base = obtener_directorio_ejecutable()
    archivos_disponibles = listar_archivos_carpeta()

    if nombre_archivo is not None and nombre_archivo.strip():
        entrada = nombre_archivo.strip()
    else:
        print("\n" + "-" * 75)
        print(" [CARGA DE ARCHIVO DE PROCESOS]")
        print(" REGLA: Los archivos deben estar ubicados SIEMPRE en la carpeta del simulador:")
        print(f" -> Carpeta: {directorio_base}")
        print(" -> Ingrese ÚNICAMENTE el nombre del archivo (ej. 'procesos.csv'), NO la ruta.")
        if archivos_disponibles:
            print(" -> Archivos compatibles detectados en esta carpeta:")
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
        print(f"\n>> ERROR: No se encontró el archivo '{nombre_mostrado}' en la carpeta del simulador.")
        print(f">> Carpeta requerida: {directorio_base}")
        print(f">> Recuerde colocar el archivo en dicha carpeta e ingresar únicamente su nombre (sin rutas).")
        if archivos_disponibles:
            print(f">> Archivos disponibles en la carpeta: {archivos_disponibles}")
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
    """
    Interfaz interactiva para cargar procesos uno a uno por teclado.
    """
    print("\n--- CARGA MANUAL DE PROCESOS (Máximo 10 procesos) ---")
    try:
        cant_str = input("¿Cuántos procesos desea cargar? (1 a 10): ").strip()
        cantidad = int(cant_str)
        if cantidad < 1 or cantidad > 10:
            print(">> ERROR: La cantidad de procesos debe ser entre 1 y 10.")
            return None
    except ValueError:
        print(">> ERROR: Ingrese un número entero válido.")
        return None

    procesos = []
    print("\nIngrese los datos solicitados para cada proceso:")
    for i in range(1, cantidad + 1):
        print(f"\n[Proceso {i} de {cantidad}]")
        pid = input("  Identificador (PID, ej. P1): ").strip().upper()
        if not pid:
            pid = f"P{i}"

        try:
            tamano = int(input("  Tamaño en KB (1 a 450 KB): ").strip())
            arribo = int(input("  Tiempo de Arribo (Ta >= 0): ").strip())
            irrupcion = int(input("  Tiempo de Irrupción / Burst (Ti > 0): ").strip())
        except ValueError:
            print(">> ERROR: Los valores numéricos deben ser números enteros. Carga abortada.")
            return None

        procesos.append(Proceso(
            pid=pid,
            tamano=tamano,
            tiempo_arribo=arribo,
            tiempo_irrupcion=irrupcion,
            tiempo_restante=irrupcion
        ))

    valido, mensaje = validar_procesos(procesos)
    if not valido:
        print(f">> ERROR DE VALIDACIÓN: {mensaje}")
        return None

    print(f">> Se cargaron exitosamente {len(procesos)} procesos manualmente.")
    return procesos


def obtener_dataset_ejemplo() -> List[Proceso]:
    """
    Dataset predefinido altamente didáctico diseñado específicamente para cátedra de SO:
    - P1 (200 KB, Arribo 0, Burst 5): Asignado en 100K..299K, hueco de 250 KB. Entra a CPU.
    - P2 (150 KB, Arribo 1, Burst 3): Asignado en 300K..449K (Best-Fit). Ti=3 < P1 restante(4) -> DESALOJO SRTF!
    - P3 (160 KB, Arribo 2, Burst 4): Solo quedan 100 KB libres en RAM. Va a LISTO Y SUSPENDIDO (Swap).
    - P4 (80 KB, Arribo 3, Burst 2): Entra en el hueco de 100 KB (450K..529K). Remanente de 20 KB.
    - P2 finaliza en t=4: Libera 150 KB. Quedan 150 KB + 20 KB = 170 KB libres.
      Pero P3 requiere 160 KB y el mayor hueco es 150 KB -> FRAGMENTACIÓN EXTERNA DEMOSTRADA (sin compactar).
    - P4 finaliza en t=6: Fusión adyacente doble con el hueco anterior (150 KB) y posterior (20 KB) -> Bloque de 250 KB.
      P3 se des-suspende y entra a RAM.
    - P5 (100 KB, Arribo 7, Burst 3): Arriba cuando RAM tiene solo 90 KB libres -> Va a LISTO Y SUSPENDIDO.
    """
    return [
        Proceso(pid="P1", tamano=200, tiempo_arribo=0, tiempo_irrupcion=5, tiempo_restante=5),
        Proceso(pid="P2", tamano=150, tiempo_arribo=1, tiempo_irrupcion=3, tiempo_restante=3),
        Proceso(pid="P3", tamano=160, tiempo_arribo=2, tiempo_irrupcion=4, tiempo_restante=4),
        Proceso(pid="P4", tamano=80, tiempo_arribo=3, tiempo_irrupcion=2, tiempo_restante=2),
        Proceso(pid="P5", tamano=100, tiempo_arribo=7, tiempo_irrupcion=3, tiempo_restante=3),
    ]


# ==============================================================================
# MENÚ PRINCIPAL E INTERACTIVIDAD
# ==============================================================================

def mostrar_tabla_procesos_cargados(procesos: List[Proceso]):
    """Muestra un resumen de los procesos listos para simular."""
    print("\nPROCESOS PREPARADOS PARA LA SIMULACIÓN:")
    print("+---------+--------+---------------+--------------------+")
    print("| Proceso | Tamaño | Tiempo Arribo | Tiempo Irrupción   |")
    print("+---------+--------+---------------+--------------------+")
    for p in sorted(procesos, key=lambda item: (item.tiempo_arribo, item.pid)):
        print(f"| {p.pid:<7} | {p.tamano:<4}KB | {p.tiempo_arribo:<13} | {p.tiempo_irrupcion:<18} |")
    print("+---------+--------+---------------+--------------------+")


def info_rutas_entrada():
    """Muestra información sobre las rutas de entrada y ubicación de archivos."""
    directorio_base = obtener_directorio_ejecutable()
    archivos = listar_archivos_carpeta()
    print("\n" + "=" * 80)
    print("                INFORMACIÓN: RUTAS DE ENTRADA Y ARCHIVOS")
    print("=" * 80)
    print(" * Ubicación obligatoria de los archivos:")
    print("   Todos los archivos de procesos deben estar ubicados SIEMPRE en la misma")
    print("   carpeta donde reside el script o ejecutable del simulador:")
    print(f"   -> Carpeta actual: {directorio_base}")
    print()
    print(" * Cómo ingresar el archivo en el simulador:")
    print("   - No es necesario escribir rutas absolutas ni relativas (ej. NO 'C:\\ruta\\archivo.csv').")
    print("   - Ingrese ÚNICAMENTE el nombre con su extensión (ej. 'procesos.csv' o 'datos.txt').")
    print("   - O bien ingrese el NÚMERO DE ÍNDICE que aparece en la lista de archivos detectados.")
    print("   - Si omite la extensión '.csv', el sistema intentará agregarla automáticamente.")
    print()
    print(" * Archivos compatibles detectados actualmente en esta carpeta:")
    if archivos:
        for idx, arch in enumerate(archivos, start=1):
            print(f"   [{idx}] {arch}")
    else:
        print("   [!] No se encontraron archivos .csv o .txt en la carpeta actualmente.")
    print()
    print(" * Ejecución directa por línea de comandos (CLI):")
    print("   Puede pasar el nombre del archivo como argumento al iniciar el programa:")
    print("   -> python simulador.py procesos.csv")
    print("=" * 80)
    try:
        input("\nPresione [ENTER] para regresar al submenú de información... ")
    except (KeyboardInterrupt, EOFError):
        pass


def info_estructura_archivo():
    """Muestra especificaciones del formato y estructura del archivo de procesos."""
    print("\n" + "=" * 80)
    print("         INFORMACIÓN: ESTRUCTURA DEL ARCHIVO DE ENTRADA (.CSV / .TXT)")
    print("=" * 80)
    print(" * Formato general:")
    print("   Archivo de texto plano (.csv o .txt) con valores separados por coma (,).")
    print("   Cada línea representa un proceso con exactamente 4 columnas:")
    print("       PID, Tamaño, Tiempo de Arribo, Tiempo de Irrupción")
    print()
    print(" * Ejemplo de archivo válido:")
    print("   --------------------------------------------------")
    print("   # Este es un comentario opcional (inicia con '#')")
    print("   PID,Tamaño,Arribo,Irrupcion")
    print("   P1,200,0,5")
    print("   P2,150,1,3")
    print("   P3,160,2,4")
    print("   P4,80,3,2")
    print("   --------------------------------------------------")
    print()
    print(" * Especificaciones y reglas de negocio:")
    print("   1. Encabezado:")
    print("      - Opcional. Si la primera fila contiene 'PID', 'proceso' o 'id',")
    print("        el simulador la detecta y descarta automáticamente.")
    print("   2. Cantidad de procesos:")
    print("      - Mínimo: 1 proceso.")
    print("      - Máximo: 10 procesos simultáneos en el lote de entrada.")
    print("   3. PID (Identificador de Proceso):")
    print("      - Texto alfanumérico único para cada proceso (ej. P1, P2, PROC_A).")
    print("      - No se admiten identificadores duplicados ni vacíos.")
    print("   4. Tamaño en memoria (KB):")
    print("      - Número entero positivo entre 1 y 450 KB.")
    print("      - Límite del sistema: Memoria Total = 550 KB.")
    print("        Sistema Operativo reserva 100 KB fijos (direcciones 0K..99K).")
    print("        Espacio de usuario disponible = 450 KB (direcciones 100K..549K).")
    print("        Ningún proceso individual puede exceder los 450 KB.")
    print("   5. Tiempo de Arribo (Ta):")
    print("      - Número entero mayor o igual a 0 (instante de tiempo en u.t. de llegada).")
    print("   6. Tiempo de Irrupción (Ti / Burst):")
    print("      - Número entero mayor a 0 (duración requerida en CPU en u.t.).")
    print("   7. Líneas vacías y comentarios:")
    print("      - Se omiten automáticamente líneas en blanco o que inicien con '#'.")
    print("=" * 80)
    try:
        input("\nPresione [ENTER] para regresar al submenú de información... ")
    except (KeyboardInterrupt, EOFError):
        pass


def info_estadisticas_finales():
    """Muestra el significado y fórmulas de los datos estadísticos finales."""
    print("\n" + "=" * 80)
    print("             INFORMACIÓN: SIGNIFICADO DE LAS ESTADÍSTICAS FINALES")
    print("=" * 80)
    print(" Al finalizar la simulación, el sistema emite una tabla individual de métricas")
    print(" por proceso y un resumen de estadísticas globales:")
    print()
    print(" 1. MÉTRICAS INDIVIDUALES POR PROCESO")
    print(" -------------------------------------------------------------------------------")
    print(" * Tiempo de Arribo (Ta):")
    print("   Instante de reloj en el que el proceso entra formalmente al sistema.")
    print()
    print(" * Tiempo de Irrupción (Ti):")
    print("   Duración total de ráfaga de CPU requerida por el proceso.")
    print()
    print(" * Tiempo de Fin (Tf):")
    print("   Instante de reloj en el que el proceso ejecutó su última instrucción y concluyó.")
    print()
    print(" * Tiempo de Retorno (Tr / Turnaround Time):")
    print("   - Fórmula: Tr = Tf - Ta")
    print("   - Significado: Intervalo total transcurrido desde que el proceso arriba hasta que")
    print("     finaliza. Incluye el tiempo de ejecución en CPU más todo el tiempo de espera en")
    print("     la cola de listos (RAM) y en estado suspendido (Swap).")
    print()
    print(" * Tiempo de Espera (Te / Waiting Time):")
    print("   - Fórmula: Te = Tr - Ti")
    print("   - Significado: Tiempo neto acumulado que el proceso pasó aguardando turno")
    print("     sin hacer uso de la CPU. Refleja las demoras por competencia de CPU y memoria.")
    print()
    print(" 2. ESTADÍSTICAS GLOBALES DEL SISTEMA")
    print(" -------------------------------------------------------------------------------")
    print(" * Total de Procesos Terminados (n):")
    print("   Cantidad de procesos que completaron exitosamente su ciclo de vida.")
    print()
    print(" * Tiempo Total de Simulación:")
    print("   Instante de reloj en el cual terminó el último proceso del lote.")
    print()
    print(" * Tiempo de Retorno Promedio (Tr prom):")
    print("   - Fórmula: Tr_prom = (Suma de Tr de todos los procesos) / n")
    print("   - Significado: Tiempo medio que tarda un proceso en completarse desde su arribo.")
    print("     Evalúa la rapidez con la que el sistema entrega resultados al usuario.")
    print()
    print(" * Tiempo de Espera Promedio (Te prom):")
    print("   - Fórmula: Te_prom = (Suma de Te de todos los procesos) / n")
    print("   - Significado: Tiempo promedio que un proceso debió esperar para ser atendido.")
    print("     Es el indicador por excelencia de la eficacia del algoritmo de planificación:")
    print("     SRTF (Shortest Remaining Time First) está diseñado para minimizar este valor.")
    print()
    print(" * Rendimiento (Throughput):")
    print("   - Fórmula: Throughput = n / Tiempo Total de Simulación")
    print("   - Significado: Cantidad de procesos completados por cada unidad de tiempo (u.t.).")
    print("     Mide la productividad y capacidad de procesamiento del sistema.")
    print("=" * 80)
    try:
        input("\nPresione [ENTER] para regresar al submenú de información... ")
    except (KeyboardInterrupt, EOFError):
        pass


def submenu_informacion():
    """Submenú interactivo para navegar las distintas secciones de ayuda e información."""
    while True:
        print("\n" + "=" * 70)
        print("                    SUBMENÚ DE INFORMACIÓN")
        print("=" * 70)
        print(" 1. Información sobre rutas de entrada y ubicación de archivos")
        print(" 2. Información sobre estructura del archivo de entrada (.csv / .txt)")
        print(" 3. Información sobre estadísticas y métricas finales")
        print(" 4. Volver al menú principal")
        print("-" * 70)

        opc = input("Seleccione una opción (1-4): ").strip()

        if opc == "1":
            info_rutas_entrada()
        elif opc == "2":
            info_estructura_archivo()
        elif opc == "3":
            info_estadisticas_finales()
        elif opc in ("4", "v", "volver", "salir", "exit", "q"):
            break
        else:
            print(">> Opción no válida. Ingrese un número del 1 al 4.")


def menu_principal():
    """Bucle del menú interactivo para el usuario."""
    directorio_base = obtener_directorio_ejecutable()

    while True:
        print("\n" + "=" * 75)
        print(" SIMULADOR DE ASIGNACIÓN DE MEMORIA (BEST-FIT) Y PLANIFICACIÓN (SRTF)")
        print(" Cátedra Sistemas Operativos - UTN FRRe")
        print("=" * 75)
        print(" 1. Cargar archivo de la carpeta")
        print(" 2. Cargar procesos manual por consola")
        print(" 3. Usar dataset de ejemplo")
        print(" 4. Información")
        print(" 5. Salir")
        print("-" * 75)

        opcion = input("Seleccione una opción (1-5): ").strip()

        procesos_a_ejecutar = None

        if opcion == "1":
            procesos_a_ejecutar = cargar_desde_archivo()
        elif opcion == "2":
            procesos_a_ejecutar = cargar_manual_consola()
        elif opcion == "3":
            print("\n>> Cargando dataset didáctico de ejemplo...")
            procesos_a_ejecutar = obtener_dataset_ejemplo()
            print(">> Dataset cargado con 5 procesos configurados.")
        elif opcion == "4":
            submenu_informacion()
            continue
        elif opcion in ("5", "q", "salir", "exit"):
            print("\n>> Gracias por utilizar el Simulador de Sistemas Operativos. ¡Hasta luego!\n")
            sys.exit(0)
        else:
            print(">> Opción no reconocida. Por favor ingrese un número del 1 al 5.")
            continue

        if procesos_a_ejecutar:
            mostrar_tabla_procesos_cargados(procesos_a_ejecutar)
            confirmar = input("\n¿Desea iniciar la simulación con estos procesos? (S/n) [S]: ").strip().lower()
            if confirmar in ("", "s", "si", "y", "yes"):
                simulador = Simulador(procesos_a_ejecutar)
                simulador.ejecutar_simulacion()
            else:
                print(">> Simulación cancelada. Regresando al menú principal.")


# ==============================================================================
# PUNTO DE ENTRADA
# ==============================================================================

if __name__ == "__main__":
    try:
        # Si se pasa un archivo como argumento CLI, cargarlo desde la carpeta del simulador
        if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
            nombre_cli = os.path.basename(sys.argv[1].strip().strip("'\""))
            print(f">> Cargando archivo desde la carpeta del simulador: '{nombre_cli}'...")
            procesos_cli = cargar_desde_archivo(nombre_cli)
            if procesos_cli:
                mostrar_tabla_procesos_cargados(procesos_cli)
                simulador_cli = Simulador(procesos_cli)
                simulador_cli.ejecutar_simulacion()
                sys.exit(0)
        menu_principal()
    except (KeyboardInterrupt, EOFError):
        print("\n\n>> Ejecución finalizada por el usuario.")
        sys.exit(0)
