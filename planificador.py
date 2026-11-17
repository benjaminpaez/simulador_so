"""
Planificador de CPU a corto plazo: SRTF (Shortest Remaining Time First).
"""

from typing import List, Optional

from modelos import Proceso


class PlanificadorSRTF:
    """Planificador apropiativo (con desalojo estricto) por menor tiempo restante."""

    def __init__(self):
        self.cola_listos: List[Proceso] = []
        self.cola_suspendidos: List[Proceso] = []
        self.proceso_ejecucion: Optional[Proceso] = None

    def mejor_candidato_listo(self) -> Optional[Proceso]:
        """Retorna el proceso de la cola de listos con menor tiempo restante sin extraerlo."""
        if not self.cola_listos:
            return None
        return min(self.cola_listos, key=lambda p: (p.tiempo_restante, p.tiempo_arribo, p.pid))

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
        Selecciona y extrae el proceso con menor tiempo restante de la Cola de Listos.
        Desempata por tiempo de arribo (FIFO) y luego por PID.
        """
        if not self.cola_listos:
            return None
        self.cola_listos.sort(key=lambda p: (p.tiempo_restante, p.tiempo_arribo, p.pid))
        return self.cola_listos.pop(0)