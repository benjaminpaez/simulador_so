"""
Pruebas unitarias y de integración para el Simulador de Sistemas Operativos.
Valida: Best-Fit, Coalescencia adyacente, Fragmentación Externa, SRTF, Multiprogramación
y métricas finales sobre el dataset de ejemplo.
"""

import unittest

from cargador import (
    obtener_dataset_ejemplo,
    parsear_lineas_procesos,
    validar_procesos,
)
from memoria import GestorMemoria
from modelos import Proceso
from planificador import PlanificadorSRTF
from simulador import Simulador


def crear_proceso(pid: str, tamano: int, arribo: int = 0, irrupcion: int = 5) -> Proceso:
    return Proceso(
        pid=pid,
        tamano=tamano,
        tiempo_arribo=arribo,
        tiempo_irrupcion=irrupcion,
        tiempo_restante=irrupcion,
    )


class TestGestorMemoriaBestFitYCoalescencia(unittest.TestCase):
    def setUp(self):
        self.mem = GestorMemoria()

    def test_best_fit_elige_menor_remanente(self):
        p1 = crear_proceso("P1", 100)
        p2 = crear_proceso("P2", 150)
        p3 = crear_proceso("P3", 100)
        p4 = crear_proceso("P4", 100)

        for p in (p1, p2, p3, p4):
            self.assertTrue(self.mem.asignar_best_fit(p)[0])

        self.mem.liberar_memoria(p2)  # 150K en base 200
        self.mem.liberar_memoria(p4)  # 100K en base 450

        p5 = crear_proceso("P5", 90)
        ok, _ = self.mem.asignar_best_fit(p5)
        self.assertTrue(ok)
        self.assertEqual(p5.direccion_base, 450)

    def test_best_fit_desempata_por_menor_direccion_base(self):
        p1 = crear_proceso("P1", 100)
        p2 = crear_proceso("P2", 100)
        p3 = crear_proceso("P3", 100)
        p4 = crear_proceso("P4", 150)
        for p in (p1, p2, p3, p4):
            self.mem.asignar_best_fit(p)

        self.mem.liberar_memoria(p1)  # 100K en base 100
        self.mem.liberar_memoria(p3)  # 100K en base 300

        p5 = crear_proceso("P5", 80)
        ok, _ = self.mem.asignar_best_fit(p5)
        self.assertTrue(ok)
        self.assertEqual(p5.direccion_base, 100)

    def test_ajuste_exacto_no_genera_hueco_remanente(self):
        p1 = crear_proceso("P1", 450)
        ok, _ = self.mem.asignar_best_fit(p1)
        self.assertTrue(ok)
        self.assertEqual(self.mem.memoria_libre_total(), 0)
        self.assertEqual(len(self.mem.particiones), 2)

    def test_coalescencia_doble_y_no_fusiona_con_so(self):
        p1 = crear_proceso("P1", 100)
        p2 = crear_proceso("P2", 150)
        p3 = crear_proceso("P3", 200)
        for p in (p1, p2, p3):
            self.mem.asignar_best_fit(p)

        self.mem.liberar_memoria(p1)
        self.mem.liberar_memoria(p3)
        self.assertEqual(len(self.mem.particiones), 4)

        ok, _ = self.mem.liberar_memoria(p2)
        self.assertTrue(ok)
        self.assertEqual(len(self.mem.particiones), 2)
        self.assertEqual(self.mem.mayor_hueco_disponible(), 450)
        self.assertTrue(self.mem.particiones[0].es_so)

    def test_fragmentacion_externa_detectada_correctamente(self):
        p1 = crear_proceso("P1", 100)
        p2 = crear_proceso("P2", 150)
        p3 = crear_proceso("P3", 200)
        for p in (p1, p2, p3):
            self.mem.asignar_best_fit(p)

        self.mem.liberar_memoria(p1)
        self.mem.liberar_memoria(p3)

        p_grande = crear_proceso("P4", 250)
        self.assertTrue(self.mem.hay_fragmentacion_externa([p_grande]))
        ok, msg = self.mem.asignar_best_fit(p_grande)
        self.assertFalse(ok)
        self.assertIn("FRAGMENTACIÓN EXTERNA", msg)


class TestPlanificadorSRTF(unittest.TestCase):
    def test_desalojo_estricto_y_no_desalojo_en_empate(self):
        plan = PlanificadorSRTF()
        plan.proceso_ejecucion = crear_proceso("P1", 100, arribo=0, irrupcion=4)

        p_empate = crear_proceso("P2", 100, arribo=1, irrupcion=4)
        self.assertFalse(plan.desaloja_a_ejecucion(p_empate))

        p_menor = crear_proceso("P3", 100, arribo=2, irrupcion=3)
        self.assertTrue(plan.desaloja_a_ejecucion(p_menor))

    def test_seleccion_siguiente_desempata_por_arribo_y_pid(self):
        plan = PlanificadorSRTF()
        p_b = crear_proceso("P2", 50, arribo=1, irrupcion=3)
        p_a = crear_proceso("P1", 50, arribo=1, irrupcion=3)
        p_mas_temprano = crear_proceso("P3", 50, arribo=0, irrupcion=3)

        plan.cola_listos = [p_b, p_a, p_mas_temprano]
        self.assertIs(plan.seleccionar_siguiente(), p_mas_temprano)
        self.assertIs(plan.seleccionar_siguiente(), p_a)
        self.assertIs(plan.seleccionar_siguiente(), p_b)


class TestIntegracionSimulador(unittest.TestCase):
    def test_dataset_ejemplo_completo(self):
        sim = Simulador(obtener_dataset_ejemplo())
        termino = sim.ejecutar_hasta_final()

        self.assertTrue(termino)
        self.assertTrue(sim.finalizado)
        self.assertEqual(len(sim.procesos_terminados), 5)

        por_pid = {p.pid: p for p in sim.procesos_terminados}
        self.assertEqual(por_pid["P2"].tiempo_fin, 4)
        self.assertEqual(por_pid["P4"].tiempo_fin, 6)
        self.assertEqual(por_pid["P1"].tiempo_fin, 10)
        self.assertEqual(por_pid["P5"].tiempo_fin, 13)
        self.assertEqual(por_pid["P3"].tiempo_fin, 17)
        self.assertEqual(sim.reloj, 17)

    def test_limite_multiprogramacion_5(self):
        procesos = [crear_proceso(f"P{i}", 50, arribo=0, irrupcion=2) for i in range(1, 8)]
        sim = Simulador(procesos)
        sim.ejecutar_paso()
        self.assertLessEqual(sim.total_activos, 5)
        self.assertEqual(len(sim.cola_nuevos_espera), 2)
        self.assertTrue(sim.ejecutar_hasta_final())
        self.assertEqual(len(sim.procesos_terminados), 7)

    def test_validaciones_y_parseo_csv(self):
        lineas = [
            "# Comentario inicial",
            "PID,Tamano,Arribo,Irrupcion",
            "P1,100,0,5",
            "P2,450,2,3",
        ]
        procs = parsear_lineas_procesos(lineas)
        self.assertEqual(len(procs), 2)
        ok, _ = validar_procesos(procs)
        self.assertTrue(ok)

        invalido = [crear_proceso("P1", 451, 0, 5)]
        ok_inv, msg = validar_procesos(invalido)
        self.assertFalse(ok_inv)
        self.assertIn("450 KB", msg)


if __name__ == "__main__":
    unittest.main()