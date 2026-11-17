"""
Gestor de Memoria Principal (550 KB: 100 KB SO + 450 KB Usuario).
Política: Particiones Variables Dinámicas (MVT), Best-Fit y coalescencia adyacente sin compactación.
"""

from typing import List, Optional, Tuple

from modelos import Particion, Proceso


class GestorMemoria:
    """Administrador de Memoria Principal con Best-Fit y coalescencia natural."""

    TAMANO_TOTAL = 550
    TAMANO_SO = 100
    TAMANO_USUARIO = 450
    BASE_USUARIO = 100

    def __init__(self):
        self.particiones: List[Particion] = [
            Particion(id_particion=0, base=0, tamano=self.TAMANO_SO, proceso=None, es_so=True),
            Particion(id_particion=1, base=self.BASE_USUARIO, tamano=self.TAMANO_USUARIO, proceso=None, es_so=False),
        ]

    def _reindexar(self) -> None:
        """Mantiene los IDs de partición ordenados consecutivamente de 0 a N."""
        for idx, part in enumerate(self.particiones):
            part.id_particion = idx
            if part.proceso is not None:
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

    def hay_fragmentacion_externa(self, procesos_esperando: Optional[List[Proceso]] = None) -> bool:
        """
        Existe únicamente cuando hay al menos un proceso esperando ingresar a RAM
        cuyo tamaño es <= memoria_libre_total, pero > mayor_hueco_disponible.
        """
        if not procesos_esperando:
            return False
        libre_total = self.memoria_libre_total()
        mayor_hueco = self.mayor_hueco_disponible()
        return any(mayor_hueco < p.tamano <= libre_total for p in procesos_esperando)

    def asignar_best_fit(self, proceso: Proceso) -> Tuple[bool, str]:
        """
        Busca el hueco contiguo libre de tamaño >= proceso.tamano que deje el menor remanente.
        En caso de empate, elige el de menor dirección base.
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
                    f"(el mayor hueco disponible es de {mayor_hueco} KB)."
                )
            else:
                detalle = (
                    f"MEMORIA INSUFICIENTE: Requiere {proceso.tamano} KB y la memoria libre total "
                    f"es de solo {libre_total} KB."
                )
            return False, detalle

        candidatos.sort(key=lambda item: (item[1].tamano - proceso.tamano, item[1].base))
        idx_elegido, particion_elegida = candidatos[0]
        base_asignada = particion_elegida.base

        if particion_elegida.tamano == proceso.tamano:
            particion_elegida.proceso = proceso
            proceso.particion_id = particion_elegida.id_particion
            proceso.direccion_base = base_asignada
            detalle = (
                f"Asignado en Partición {particion_elegida.id_particion} "
                f"[{base_asignada}K - {base_asignada + proceso.tamano - 1}K] (Ajuste exacto, sin remanente)."
            )
        else:
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
                es_so=False,
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
        Libera la partición asignada al proceso y realiza únicamente coalescencia
        con vecinos inmediatos (anterior y/o posterior) si están libres.
        """
        idx_encontrado = None
        for idx, p in enumerate(self.particiones):
            if p.proceso is proceso or (p.proceso is not None and p.proceso.pid == proceso.pid):
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

        # 1. Coalescencia con vecino anterior (si no es SO y está libre)
        if idx_encontrado > 0:
            anterior = self.particiones[idx_encontrado - 1]
            if anterior.libre:
                fusiones.append(f"vecino anterior [base {anterior.base}K, tamaño {anterior.tamano}K]")
                anterior.tamano += part.tamano
                self.particiones.pop(idx_encontrado)
                part = anterior
                idx_encontrado -= 1

        # 2. Coalescencia con vecino posterior (si está libre)
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