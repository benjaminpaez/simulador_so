"""
Modelos de dominio del Simulador de Asignación de Memoria y Planificación de Procesos.
Cátedra: Sistemas Operativos - UTN FRRe.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class EstadoProceso(Enum):
    NUEVO = "NUEVO"
    LISTO = "LISTO"
    LISTO_SUSPENDIDO = "LISTO Y SUSPENDIDO"
    EJECUCION = "EJECUCION"
    TERMINADO = "TERMINADO"


@dataclass
class Proceso:
    """Representa un Proceso (PCB simplificado) en el sistema operativo."""
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

    @property
    def tiempo_respuesta(self) -> Optional[int]:
        """Tiempo de Respuesta (T_resp = tiempo_inicio - Ta)."""
        if self.tiempo_inicio is not None:
            return self.tiempo_inicio - self.tiempo_arribo
        return None

    def __repr__(self) -> str:
        return f"{self.pid}({self.tamano}K, Rest:{self.tiempo_restante})"


@dataclass
class Particion:
    """Representa una partición o hueco contiguo en memoria física."""
    id_particion: int
    base: int                     # Dirección de inicio en KB (0 .. 549)
    tamano: int                   # Tamaño de la partición en KB
    proceso: Optional[Proceso] = None
    es_so: bool = False           # True si está reservada para el Sistema Operativo

    @property
    def libre(self) -> bool:
        """Indica si la partición es un hueco disponible para asignar a usuarios."""
        return self.proceso is None and not self.es_so

    @property
    def fragmentacion_interna(self) -> int:
        """En particiones variables dinámicas (MVT) no existe fragmentación interna."""
        return 0

    def calcular_fragmentacion_externa(self, existe_frag_externa: bool = False) -> int:
        """
        Un hueco libre constituye fragmentación externa solo cuando existe al menos
        un proceso esperando memoria que cabría en el total libre pero no en ningún hueco individual.
        """
        return self.tamano if (self.libre and existe_frag_externa) else 0

    @property
    def limite_superior(self) -> int:
        """Última dirección ocupada por la partición (inclusiva)."""
        return self.base + self.tamano - 1