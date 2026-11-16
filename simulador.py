"""
Coordinador central de la simulación (reloj, admisión, memoria y CPU).
"""

from typing import Dict, List, Tuple

from memoria import GestorMemoria
from modelos import EstadoProceso, Proceso
from planificador import PlanificadorSRTF


class Simulador:
    """
    Gobierna el reloj del sistema, el grado de multiprogramación (máx. 5),
    la asignación de memoria y la planificación SRTF.
    """
    LIMITE_MULTIPROGRAMACION = 5

    def __init__(self, procesos: List[Proceso]):
        self.procesos_iniciales: List[Proceso] = [
            Proceso(
                pid=p.pid,
                tamano=p.tamano,
                tiempo_arribo=p.tiempo_arribo,
                tiempo_irrupcion=p.tiempo_irrupcion,
                tiempo_restante=p.tiempo_irrupcion,
                estado=EstadoProceso.NUEVO,
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

        # Historial de Gantt: lista de tuplas (tick, pid_en_cpu | "IDLE")
        self.historial_gantt: List[Tuple[int, str]] = []

        # Límite dinámico seguro para evitar bucles infinitos
        max_arribo = max((p.tiempo_arribo for p in self.procesos_iniciales), default=0)
        suma_burst = sum(p.tiempo_irrupcion for p in self.procesos_iniciales)
        self.limite_ticks = max(1000, max_arribo + suma_burst + 50)

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
        Ejecuta las transiciones correspondientes al instante de reloj actual (t).
        Retorna la lista de eventos relevantes ocurridos en este instante.
        """
        eventos: List[str] = []
        t = self.reloj

        # 1. Evaluar terminación del proceso en CPU
        if self.planificador.proceso_ejecucion is not None:
            if self.planificador.proceso_ejecucion.tiempo_restante == 0:
                p_fin = self.planificador.proceso_ejecucion
                p_fin.estado = EstadoProceso.TERMINADO
                p_fin.tiempo_fin = t
                self.procesos_terminados.append(p_fin)

                _, msg_lib = self.gestor_memoria.liberar_memoria(p_fin)
                eventos.append(
                    f"TERMINACIÓN: Proceso {p_fin.pid} finalizó su ejecución en t={t} "
                    f"(Retorno Tr={p_fin.tiempo_retorno} u.t., Espera Te={p_fin.tiempo_espera} u.t.)."
                )
                eventos.append(f"LIBERACIÓN MEMORIA: {msg_lib}")
                self.planificador.proceso_ejecucion = None

        # 2. Evaluar reingreso de procesos suspendidos (des-suspensión)
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

        # 3. Llegada de nuevos procesos (arribos en tiempo t)
        while self.procesos_pendientes_arribo and self.procesos_pendientes_arribo[0].tiempo_arribo <= t:
            p_arr = self.procesos_pendientes_arribo.pop(0)
            self.cola_nuevos_espera.append(p_arr)
            eventos.append(
                f"ARRIBO: Proceso {p_arr.pid} llega al sistema en t={t} "
                f"(Tamaño: {p_arr.tamano} KB, Ráfaga: {p_arr.tiempo_irrupcion} u.t.) -> Ingresa al estado NUEVO."
            )

        # 4. Admisión al cupo de multiprogramación (máx 5 activos)
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
                    f"{self.LIMITE_MULTIPROGRAMACION}). {msg_asig}"
                )

        if self.cola_nuevos_espera:
            esperando_pids = [p.pid for p in self.cola_nuevos_espera]
            eventos.append(
                f"LÍMITE MULTIPROGRAMACIÓN: Cupo máximo alcanzado ({self.total_activos}/"
                f"{self.LIMITE_MULTIPROGRAMACION}). Procesos en espera de admisión: {esperando_pids}."
            )

        # 5. Planificación SRTF: evaluación de desalojo o despacho
        if self.planificador.proceso_ejecucion is not None:
            menor_en_listos = self.planificador.mejor_candidato_listo()
            if menor_en_listos is not None and self.planificador.desaloja_a_ejecucion(menor_en_listos):
                desalojado = self.planificador.proceso_ejecucion
                desalojado.estado = EstadoProceso.LISTO
                self.planificador.cola_listos.append(desalojado)

                self.planificador.cola_listos = [
                    p for p in self.planificador.cola_listos if p is not menor_en_listos
                ]
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

    def avanzar_reloj(self) -> None:
        """Registra el uso de CPU en [t, t+1), avanza el reloj en 1 u.t. y consume 1 u.t. de CPU."""
        if self.planificador.proceso_ejecucion is not None:
            self.historial_gantt.append((self.reloj, self.planificador.proceso_ejecucion.pid))
            self.planificador.proceso_ejecucion.tiempo_restante -= 1
        else:
            self.historial_gantt.append((self.reloj, "IDLE"))
        self.reloj += 1

    def ejecutar_hasta_final(self) -> bool:
        """Ejecuta la simulación completa de manera no interactiva (para tests)."""
        while not self.finalizado and self.reloj < self.limite_ticks:
            self.ejecutar_paso()
            if self.finalizado:
                break
            self.avanzar_reloj()
        return self.finalizado

    def calcular_metricas_globales(self) -> Dict[str, float]:
        """Calcula promedios de Tr, Te, T_resp, Throughput y Uso de CPU."""
        n = len(self.procesos_terminados)
        if n == 0:
            return {
                "total_terminados": 0,
                "tiempo_total": self.reloj,
                "tr_promedio": 0.0,
                "te_promedio": 0.0,
                "tresp_promedio": 0.0,
                "throughput": 0.0,
                "uso_cpu_pct": 0.0,
            }

        suma_tr = sum(p.tiempo_retorno or 0 for p in self.procesos_terminados)
        suma_te = sum(p.tiempo_espera or 0 for p in self.procesos_terminados)
        suma_tresp = sum(p.tiempo_respuesta or 0 for p in self.procesos_terminados)
        ticks_ocupados = sum(1 for _, pid in self.historial_gantt if pid != "IDLE")
        tiempo_total = self.reloj

        return {
            "total_terminados": n,
            "tiempo_total": tiempo_total,
            "tr_promedio": suma_tr / n,
            "te_promedio": suma_te / n,
            "tresp_promedio": suma_tresp / n,
            "throughput": (n / tiempo_total) if tiempo_total > 0 else 0.0,
            "uso_cpu_pct": (ticks_ocupados / tiempo_total * 100.0) if tiempo_total > 0 else 0.0,
        }