#!/usr/bin/env python3
"""
Script de datos de demo para Hestia - Escuela de Salud DuocUC.

Uso:
    docker compose exec api python seed_demo.py

Genera:
    - 18 salas clinicas, 10 categorias
    - 5 usuarios (admin, 2 operadores, 2 visores)
    - 2 docentes demo
    - 20 asignaturas de 5 carreras
    - 88 insumos/implementos en Bodega
    - Unidades fisicas de implementos
    - ~560 movimientos en los ultimos 60 dias
    - 6 activos fijos: 3 muebles + 3 phantomas
    - 2 proveedores: Laerdal Chile y MedSupply SpA
    - 1 orden de mantenimiento demo (SimMan 3G en_curso con Laerdal)
    - 10 talleres + 10 paquetes de insumos
    - 10 programaciones de taller (semestre 2026-1)
    - 10 revisiones de sala (8 completadas, 2 en_revision), 32 items
    - 3 incidencias en activos fijos
    - 3 ordenes de entrada (1 cerrada, 1 confirmada, 1 borrador), 9 items

Credenciales:
    admin@hestia.duoc.cl          / Admin2024!
    mgonzalez@hestia.duoc.cl      / Oper2024!
    cfuentes@hestia.duoc.cl       / Oper2024!
    amartinez@hestia.duoc.cl      / Visor2024!
    lperez@hestia.duoc.cl         / Visor2024!
"""

import re
import sys
import os
import random
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal
from app.models.sala import Sala
from app.models.insumo import Insumo, TipoInsumo
from app.models.movimiento import Movimiento, TipoMovimiento, SubtipoMovimiento
from app.models.usuario import Usuario, RolUsuario
from app.models.audit_log import AuditLog
from app.models.solicitud import SolicitudRetiro, SolicitudItem, EstadoSolicitud
from app.models.asignatura import Asignatura, CarreraAsignatura
# Docente y ComentarioDocente deben importarse ANTES de ClaseDocente para que
# el mapper de SQLAlchemy pueda resolver relationship("Docente", ...) al
# inicializar ClaseDocente.
from app.models.docente import Docente, ComentarioDocente  # noqa: F401
from app.models.clase_docente import ClaseDocente
from app.models.retorno_implemento import RetornoImplemento
from app.models.activo_fijo import (
    ActivoFijo, TipoActivo, EstadoActivo, FidelidadPhantoma,
)
from app.models.unidad_implemento import UnidadImplemento, EstadoUnidad
# IMPORTANTE: taller y paquete_insumo deben importarse antes de cualquier
# query ORM para que el mapper de SQLAlchemy registre las relaciones de
# Asignatura antes de la primera consulta.
from app.models.taller import Taller
from app.models.paquete_insumo import PaqueteInsumo, PaqueteItem
from app.models.proveedor import Proveedor
from app.models.orden_mantenimiento import (
    OrdenMantenimiento, OrdenMantenimientoItem,
    EstadoOrden, ResultadoItem,
)
# Modelos incorporados tras la version inicial del seed. Se importan aqui para
# que el mapper de SQLAlchemy registre sus relaciones y para que el bloque de
# limpieza pueda borrarlos en el orden FK correcto.
from app.models.programacion_taller import ProgramacionTaller
from app.models.revision_sala import RevisionSala, RevisionSalaItem
from app.models.incidencia import (
    Incidencia, TipoIncidencia, SeveridadIncidencia, EstadoIncidencia,
)
from app.models.orden_entrada import (
    OrdenEntrada, OrdenEntradaItem,
    TipoOrden, EstadoOrden as EstadoOrdenEntrada,
    EstadoItem as EstadoItemOrden, TipoItemOrden,
)
from app.utils.security import hashear_password

try:
    from app.models.categoria import Categoria
except ImportError:
    from app.models.categoria import Categorium as Categoria

random.seed(42)

IN = "insumo"
IM = "implemento"
TENS  = CarreraAsignatura.TENS
TQF   = CarreraAsignatura.TQF
TLCBS = CarreraAsignatura.TLCBS
TONS  = CarreraAsignatura.TONS
PF    = CarreraAsignatura.preparador_fisico

SALAS = [
    ("Sala 010", "simulacion", "Sala de simulacion clinica - piso -1"),
    ("Sala 011", "simulacion", "Sala de simulacion clinica - piso -1"),
    ("Sala 012", "simulacion", "Sala de simulacion clinica - piso -1"),
    ("Sala 013", "simulacion", "Sala de simulacion clinica - piso -1"),
    ("Sala 014", "simulacion", "Sala de simulacion clinica - piso -1"),
    ("Sala 015", "simulacion", "Sala de simulacion clinica - piso -1"),
    ("Sala 016", "simulacion", "Sala de simulacion clinica - piso -1"),
    ("Sala 017", "simulacion", "Sala de simulacion clinica - piso -1"),
    ("Sala 018", "simulacion", "Sala de simulacion clinica - piso -1"),
    ("Sala 019", "simulacion", "Sala de simulacion clinica - piso -1"),
    ("Sala 020", "simulacion", "Sala de simulacion clinica - piso -1"),
    ("Sala 021", "simulacion", "Sala de simulacion clinica - piso -1"),
    ("Sala 022", "simulacion", "Sala de simulacion clinica - piso -1"),
    ("Bodega", "bodega", "Bodega central de insumos - piso -1"),
    ("Oficina", "oficina", "Oficina de coordinacion - piso -1"),
    ("Sala 07 - Odontologia", "odontologia", "Sala de odontologia - edificio anexo"),
    ("Sala 08 - Odontologia", "odontologia", "Sala de odontologia - edificio anexo"),
    ("Sala 09 - Odontologia", "odontologia", "Sala de odontologia - edificio anexo"),
]

CATEGORIAS = [
    "Proteccion Personal (EPP)", "Vendajes y Apositos", "Material de Sutura",
    "Instrumental de Diagnostico", "Cateterismo y Venoclisis", "Inyectologia",
    "Oxigenoterapia", "Gestion de Residuos", "Medicamentos de Emergencia",
    "Higiene y Antisepticos",
]

USUARIOS = [
    ("Administrador Hestia", "admin@hestia.duoc.cl", "Admin2024!", RolUsuario.admin),
    ("Maria Gonzalez", "mgonzalez@hestia.duoc.cl", "Oper2024!", RolUsuario.operador),
    ("Carlos Fuentes", "cfuentes@hestia.duoc.cl", "Oper2024!", RolUsuario.operador),
    ("Ana Martinez", "amartinez@hestia.duoc.cl", "Visor2024!", RolUsuario.visor),
    ("Luis Perez", "lperez@hestia.duoc.cl", "Visor2024!", RolUsuario.visor),
]

# Formato: (nombre, email, rut)
# Los docentes NO tienen cuenta en Hestia; son entidades externas gestionadas
# por el operador coordinador.
DOCENTES_DATA = [
    ("Paz Rodriguez", "paz.rodriguez@duoc.cl", "12.345.678-9"),
    ("Michael Torres", "michael.torres@duoc.cl", "98.765.432-1"),
]

ASIGNATURAS = [
    ("Primeros Auxilios", "CIS1101", TENS),
    ("Rol del Tecnico en Enfermeria y Cuidados Basicos", "CIS1102", TENS),
    ("Anatomofisiologia", "CIS1103", TENS),
    ("Atencion de Personas con Alteraciones de Salud", "CIS1104", TENS),
    ("Atencion de la Mujer y Recien Nacido", "CIS1103B", TENS),
    ("Quimica Analitica e Instrumental", "PFS1115", TQF),
    ("Bioseguridad Farmaceutica", "BIS1102", TQF),
    ("Legislacion Farmaceutica", "LFS1112", TQF),
    ("Farmacologia", "AVS2132", TQF),
    ("Preparacion de Laboratorio Clinico", "LCS1111", TLCBS),
    ("Administracion de Toma de Muestra", "ATS1111", TLCBS),
    ("Bioseguridad Clinica", "BIS1111", TLCBS),
    ("Microbiologia para Laboratorio Clinico", "LCS3111", TLCBS),
    ("Anatomo Fisiopatologia Estomatognatica", "ACS1101", TONS),
    ("Tecnicas de Primeros Auxilios y Procedimientos Basicos", "ACS1102", TONS),
    ("Servicios de Salud Generales y Odontologicos", "GAS1101", TONS),
    ("Asistencia en Cirugia Maxilofacial e Implantologia", "ACS1105", TONS),
    ("Anatomia Funcional del Aparato Locomotor", "FES1101", PF),
    ("Teoria del Entrenamiento", "EAS1101", PF),
    ("Evaluacion para la Condicion Fisica", "EAS1102", PF),
]

# Formato: (docente_nombre, asig_codigo, seccion, semestre, num_estudiantes)
# docente_nombre referencia DOCENTES_DATA; asig_codigo referencia ASIGNATURAS.
CLASES_DOCENTE = [
    ("Paz Rodriguez",  "CIS1101", "001D", "2026-1", 28),
    ("Paz Rodriguez",  "CIS1102", "001D", "2026-1", 32),
    ("Michael Torres", "CIS1103", "001D", "2026-1", 30),
    ("Michael Torres", "CIS1104", "002D", "2026-1", 35),
    ("Paz Rodriguez",  "PFS1115", "001D", "2026-1", 22),
    ("Michael Torres", "LCS1111", "001D", "2026-1", 25),
    ("Paz Rodriguez",  "ACS1101", "001D", "2026-1", 20),
    ("Michael Torres", "FES1101", "001D", "2026-1", 18),
]

# Formato: (nombre, unidad_medida, stock, minimo, cat_idx, tipo, costo)
# cat_idx referencia CATEGORIAS por posicion (restriccion: constante no modificable).
INSUMOS = [
    # EPP (cat 0)
    ("Guantes de latex talla S", "Caja x100 unidades", 150, 50, 0, IN, 3200),
    ("Guantes de latex talla M", "Caja x100 unidades", 220, 80, 0, IN, 3500),
    ("Guantes de latex talla L", "Caja x100 unidades", 95, 50, 0, IN, 3200),
    ("Guantes nitrilo sin polvo talla M", "Caja x100 unidades", 180, 100, 0, IN, 4200),
    ("Mascarillas quirurgicas", "Caja x50 unidades", 15, 60, 0, IN, 4000),
    ("Mascarillas N95 FFP2", "Unidad", 3, 20, 0, IN, 2800),
    ("Gafas de proteccion", "Unidad reutilizable", 45, 15, 0, IM, 3500),
    ("Pecheras desechables", "Unidad", 55, 25, 0, IN, 280),
    ("Gorro quirurgico", "Bolsa x100 unidades", 8, 30, 0, IN, 1800),
    ("Polainas quirurgicas", "Par", 70, 20, 0, IN, 450),
    ("Careta de proteccion facial", "Unidad reutilizable", 12, 5, 0, IM, 5500),
    # Vendajes (cat 1)
    ("Gasa esteril 10x10 cm", "Sobre x5 unidades", 380, 100, 1, IN, 650),
    ("Gasa no esteril 10x10 cm", "Rollo", 195, 80, 1, IN, 420),
    ("Aposito adhesivo 10x8 cm", "Unidad", 140, 50, 1, IN, 380),
    ("Venda de gasa 10cm x 5m", "Rollo", 75, 25, 1, IN, 520),
    ("Venda elastica 10cm", "Rollo", 55, 20, 1, IN, 850),
    ("Venda de yeso 15cm", "Unidad", 18, 8, 1, IN, 1200),
    ("Esparadrapo 5cm x 5m", "Rollo", 32, 12, 1, IN, 1850),
    ("Algodon hidrofilo 500g", "Rollo", 14, 5, 1, IN, 2400),
    ("Aposito hidrocoloide 10x10 cm", "Unidad", 25, 10, 1, IN, 2800),
    ("Tela adhesiva 10cm x 5m", "Rollo", 20, 8, 1, IN, 1650),
    ("Parche ocular esteril", "Unidad", 30, 10, 1, IN, 580),
    # Sutura (cat 2)
    ("Seda 2-0 con aguja triangular", "Sobre", 28, 10, 2, IN, 1200),
    ("Nylon 3-0 con aguja", "Sobre", 22, 10, 2, IN, 1350),
    ("Poliglactina 2-0 Vicryl", "Sobre", 15, 8, 2, IN, 2800),
    ("Seda 0 con aguja", "Sobre", 12, 5, 2, IN, 1100),
    ("Nylon 4-0 piel", "Sobre", 10, 5, 2, IN, 1450),
    ("Pinza Adson con dientes", "Unidad reutilizable", 8, 3, 2, IM, 18000),
    ("Tijera de Mayo recta", "Unidad reutilizable", 5, 2, 2, IM, 24000),
    ("Porta aguja Hegar", "Unidad reutilizable", 6, 2, 2, IM, 21000),
    # Diagnostico (cat 3)
    ("Esfigmomanometro aneroide", "Unidad reutilizable", 12, 4, 3, IM, 28000),
    ("Estetoscopio adulto", "Unidad reutilizable", 18, 6, 3, IM, 38000),
    ("Termometro digital axilar", "Unidad reutilizable", 22, 8, 3, IM, 9500),
    ("Oximetro de pulso digital", "Unidad reutilizable", 8, 3, 3, IM, 22000),
    ("Otoscopio diagnostico", "Unidad reutilizable", 4, 2, 3, IM, 95000),
    ("Martillo de reflejos neurologico", "Unidad reutilizable", 6, 2, 3, IM, 14000),
    ("Glucometro portatil", "Unidad reutilizable", 5, 2, 3, IM, 38000),
    ("Tiras reactivas glucometro x50", "Caja", 8, 4, 3, IN, 12000),
    ("Linterna diagnostica", "Unidad reutilizable", 10, 3, 3, IM, 9500),
    ("Cinta metrica flexible", "Unidad reutilizable", 15, 5, 3, IM, 2200),
    # Cateterismo (cat 4)
    ("Cateter venoso periferico 18G", "Unidad", 35, 15, 4, IN, 1450),
    ("Cateter venoso periferico 20G", "Unidad", 48, 20, 4, IN, 1350),
    ("Cateter venoso periferico 22G", "Unidad", 28, 12, 4, IN, 1450),
    ("Equipo de venoclisis con camara", "Unidad", 22, 10, 4, IN, 1850),
    ("Llave de tres pasos", "Unidad", 15, 8, 4, IN, 2200),
    ("Bolsa colectora de orina 2000ml", "Unidad", 12, 5, 4, IN, 2800),
    ("Sonda Foley N14 con globo", "Unidad", 6, 4, 4, IN, 3500),
    ("Sonda Foley N16 con globo", "Unidad", 5, 3, 4, IN, 3500),
    ("Sonda nasogastrica N14", "Unidad", 5, 3, 4, IN, 2800),
    ("Jeringa 10ml con aguja 21G", "Unidad", 85, 30, 4, IN, 380),
    ("Jeringa 20ml", "Unidad", 42, 15, 4, IN, 320),
    ("Torniquete venoso", "Unidad reutilizable", 8, 3, 4, IM, 4500),
    # Inyectologia (cat 5)
    ("Jeringa insulina 1ml", "Unidad", 160, 50, 5, IN, 120),
    ("Aguja hipodermica 21G x 1.5", "Unidad", 210, 80, 5, IN, 95),
    ("Aguja hipodermica 23G x 1", "Unidad", 185, 70, 5, IN, 95),
    ("Aguja hipodermica 25G x 5/8", "Unidad", 125, 50, 5, IN, 95),
    ("Lancetas descartables x100", "Caja", 8, 4, 5, IN, 4500),
    ("Contenedor cortopunzante 3L", "Unidad", 2, 8, 5, IN, 4200),
    ("Contenedor cortopunzante 3L APS", "Unidad", 1, 6, 5, IN, 4200),
    # Oxigenoterapia (cat 6)
    ("Mascarilla de oxigeno adulto", "Unidad reutilizable", 8, 4, 6, IM, 4800),
    ("Mascarilla Venturi adulto", "Unidad reutilizable", 4, 2, 6, IM, 8500),
    ("Canula nasal adulto", "Unidad", 14, 5, 6, IN, 850),
    ("Canula nasal pediatrica", "Unidad", 6, 3, 6, IN, 850),
    ("Bolsa autoinflable AMBU adulto", "Unidad reutilizable", 3, 2, 6, IM, 95000),
    ("Bolsa autoinflable AMBU pediatrico", "Unidad reutilizable", 2, 2, 6, IM, 85000),
    ("Resucitador AMBU con mascarilla", "Unidad reutilizable", 4, 2, 6, IM, 110000),
    # Residuos (cat 7)
    ("Bolsa roja residuos peligrosos 60L", "Unidad", 4, 12, 7, IN, 380),
    ("Bolsa amarilla residuos especiales", "Unidad", 14, 8, 7, IN, 320),
    ("Caja carton cortopunzantes grande", "Unidad", 6, 4, 7, IN, 2800),
    ("Contenedor biohazard 30L", "Unidad", 3, 2, 7, IN, 18000),
    # Medicamentos emergencia (cat 8)
    ("Adrenalina 1mg/ml ampolla 1ml", "Ampolla 1 mL", 5, 3, 8, IN, 2500),
    ("Glucosa 50% ampolla 20ml", "Ampolla 20 mL", 10, 4, 8, IN, 1800),
    ("Suero fisiologico NaCl 0.9% 1L", "Bolsa 1 L", 2, 10, 8, IN, 3500),
    ("Suero glucosado 5% 500ml", "Bolsa 500 mL", 6, 5, 8, IN, 2800),
    ("Solucion Ringer Lactato 1L", "Bolsa 1 L", 5, 4, 8, IN, 3200),
    ("Suero fisiologico 0.9% 250ml", "Bolsa 250 mL", 12, 6, 8, IN, 1800),
    ("Cloruro de sodio 20% ampolla", "Ampolla 20 mL", 8, 3, 8, IN, 1200),
    # Higiene (cat 9)
    ("Alcohol isopropilico 70% 1000ml", "Frasco 1000 mL", 12, 5, 9, IN, 5500),
    ("Clorhexidina gluconato 4% 500ml", "Frasco 500 mL", 8, 4, 9, IN, 6800),
    ("Povidona yodada 10% 100ml", "Frasco 100 mL", 10, 4, 9, IN, 3500),
    ("Jabon clinico antiseptico 500ml", "Frasco 500 mL", 16, 6, 9, IN, 4200),
    ("Gel antibacterial 500ml Sim1", "Frasco 500 mL", 3, 12, 9, IN, 3800),
    ("Gel antibacterial 500ml APS", "Frasco 500 mL", 4, 10, 9, IN, 3800),
    ("Solucion glutaraldehido 2%", "Frasco 1 L", 4, 2, 9, IN, 8500),
    ("Hipoclorito de sodio 5% 1L", "Frasco 1 L", 8, 3, 9, IN, 2800),
    ("Gasas con clorhexidina CHG", "Sobre", 40, 15, 9, IN, 1200),
]

# Formato: (nombre, descripcion, tipo, sala_nombre, fidelidad, notas, proveedor_key)
# sala_nombre referencia SALAS por nombre unico.
ACTIVOS_FIJOS_DEMO = [
    ("Camilla articulada con barandas",
     "Camilla electrica 3 secciones, barandas abatibles",
     TipoActivo.mueble, "Sala 010", None,
     "Revision anual programada marzo 2027", "medsupply"),
    ("Carro de paro de emergencia",
     "Carro equipado con desfibrilador y medicamentos de emergencia",
     TipoActivo.mueble, "Sala 013", None,
     "Revision mensual de contenido obligatoria", "medsupply"),
    ("Mesa de procedimientos Mayo",
     "Mesa auxiliar acero inoxidable con ruedas",
     TipoActivo.mueble, "Sala 012", None, None, None),
    ("SimMan 3G",
     "Maniqui de alta fidelidad adulto Laerdal",
     TipoActivo.phantoma, "Sala 010", FidelidadPhantoma.alta,
     "Mantenimiento preventivo semestral por Laerdal Chile", "laerdal"),
    ("Nursing Anne",
     "Maniqui para entrenamiento de enfermeria Laerdal",
     TipoActivo.phantoma, "Sala 011", FidelidadPhantoma.media,
     None, "laerdal"),
    ("ALS Simulator neonatal",
     "Maniqui neonatal de soporte vital avanzado",
     TipoActivo.phantoma, "Sala 016", FidelidadPhantoma.alta,
     "Solo para clase de Obstetricia y Ginecologia", "laerdal"),
]

MOTIVOS_SALIDA = [
    "Practica clinica - Enfermeria",
    "Practica simulacion alta fidelidad",
    "Uso en procedimiento de simulacion",
    "Practica de sutura y cierre de heridas",
    "Simulacro de urgencias vitales",
    "Practica de venopuncion",
    "Clase practica de diagnostico clinico",
    "Ejercicio de RCP avanzado",
    "Practica de vendaje funcional",
    "Simulacion obstetrica",
    "Taller de atencion primaria",
]

MOTIVOS_ENTRADA = [
    "Reposicion mensual de stock",
    "Compra programada DuocUC",
    "Reposicion urgente",
    "Recepcion pedido proveedor",
]

# Formato: (nombre, descripcion, asig_codigo)
# asig_codigo referencia ASIGNATURAS por codigo unico.
TALLERES_DATA = [
    ("Taller de venopuncion",
     "Practica de cateterizacion venosa periferica", "CIS1101"),
    ("Taller de sutura basica",
     "Tecnicas de sutura y cierre de heridas en simulador", "CIS1101"),
    ("Taller de RCP avanzado",
     "Reanimacion cardiopulmonar con maniqui de alta fidelidad", "CIS1103"),
    ("Taller de cuidados al recien nacido",
     "Atencion y cuidados del recien nacido en simulador neonatal", "CIS1103B"),
    ("Taller de bioseguridad y EPP",
     "Uso correcto de equipos de proteccion personal", "BIS1102"),
    ("Taller de quimica analitica",
     "Preparacion de reactivos y tecnicas de laboratorio farmaceutico", "PFS1115"),
    ("Taller de toma de muestra",
     "Tecnicas de extraccion de muestra y flebotomia", "ATS1111"),
    ("Taller de bioseguridad de laboratorio",
     "Uso correcto de EPP y manejo de residuos en laboratorio clinico", "BIS1111"),
    ("Taller de primeros auxilios odontologicos",
     "Manejo de emergencias y primeros auxilios en clinica dental", "ACS1102"),
    ("Taller de evaluacion de condicion fisica",
     "Medicion de parametros antropometricos y test de capacidad fisica", "EAS1102"),
]

# Formato: (taller_nombre, semestre, notas, items)
# taller_nombre referencia TALLERES_DATA por nombre unico.
# items: [(insumo_idx, cantidad, nota), ...] — insumo_idx referencia INSUMOS
#        por posicion (restriccion: constante no modificable).
PAQUETES_DATA = [
    ("Taller de venopuncion", "2026-1",
     "Para 30 alumnos. Verificar stock de catetes 20G antes del semestre.",
     [(0, 30, "Talla S/M segun alumno"), (1, 30, None), (4, 30, None),
      (40, 5, None), (41, 10, None), (49, 15, None),
      (51, 5, "Torniquete"), (11, 30, None)]),
    ("Taller de sutura basica", "2026-1",
     "Incluye set de instrumental de sutura por pareja de alumnos.",
     [(0, 20, None), (1, 20, None), (22, 15, None), (23, 10, None),
      (24, 8, None), (27, 4, "Una pinza por pareja"),
      (28, 4, "Una tijera por pareja"), (29, 4, None), (11, 20, None)]),
    ("Taller de RCP avanzado", "2026-1",
     "Usar SimMan 3G y Nursing Anne. Verificar AMBU antes de la clase.",
     [(0, 20, None), (1, 20, None), (4, 20, None),
      (57, 4, None), (59, 4, None), (62, 2, None),
      (63, 2, None), (64, 2, None)]),
    ("Taller de cuidados al recien nacido", "2026-1",
     "Requiere simulador neonatal. Coordinar con Maritza.",
     [(0, 25, "Talla S/XS"), (4, 25, None), (11, 20, None),
      (13, 15, None), (33, 5, None), (32, 5, None)]),
    ("Taller de bioseguridad y EPP", "2026-1",
     "EPP completo por alumno. Verificar stock de mascarillas N95.",
     [(0, 25, None), (1, 25, None), (4, 25, None), (5, 25, None),
      (6, 25, None), (7, 25, None), (8, 25, None)]),
    ("Taller de quimica analitica", "2026-1",
     "Insumos de higiene y seguridad para laboratorio quimico.",
     [(0, 20, None), (1, 20, None), (4, 20, None),
      (78, 5, "Frasco 1L"), (79, 5, None), (84, 4, None),
      (85, 4, None), (65, 10, None), (66, 10, None)]),
    ("Taller de toma de muestra", "2026-1",
     "Tecnicas de flebotomia. Cada alumno usa su propio kit de puncion.",
     [(0, 28, None), (1, 28, None), (4, 28, None),
      (41, 10, None), (49, 15, None), (51, 8, None),
      (52, 80, None), (53, 80, None), (55, 10, None)]),
    ("Taller de bioseguridad de laboratorio", "2026-1",
     "Manejo correcto de residuos biologicos y EPP de laboratorio.",
     [(0, 25, None), (4, 25, None), (6, 10, None),
      (65, 5, None), (66, 5, None), (67, 10, None),
      (68, 6, None), (83, 8, None)]),
    ("Taller de primeros auxilios odontologicos", "2026-1",
     "Protocolo de emergencias en clinica dental.",
     [(0, 20, None), (4, 20, None), (11, 10, None),
      (30, 5, None), (31, 5, None), (33, 5, None),
      (70, 3, None), (71, 3, None)]),
    ("Taller de evaluacion de condicion fisica", "2026-1",
     "Test de capacidad fisica y mediciones antropometricas.",
     [(0, 18, None), (4, 18, None),
      (31, 8, None), (32, 8, None), (33, 8, None),
      (39, 8, None)]),
]


# Formato: (taller_nombre, sala_nombre, fecha, hora_inicio, hora_fin,
#            docente_nombre, seccion, semestre, notas)
# taller_nombre referencia TALLERES_DATA por nombre unico.
# sala_nombre referencia SALAS por nombre unico.
PROGRAMACIONES_DATA = [
    ("Taller de venopuncion",
     "Sala 010", date(2026, 3, 12), "08:00", "10:30",
     "Paz Rodriguez",  "001D", "2026-1", None),
    ("Taller de sutura basica",
     "Sala 011", date(2026, 3, 26), "08:00", "10:30",
     "Paz Rodriguez",  "001D", "2026-1", None),
    ("Taller de RCP avanzado",
     "Sala 010", date(2026, 4,  9), "08:00", "11:00",
     "Michael Torres", "001D", "2026-1", "Requiere SimMan 3G operativo"),
    ("Taller de cuidados al recien nacido",
     "Sala 016", date(2026, 4, 23), "09:00", "11:30",
     None, "001D", "2026-1", "Usar ALS Simulator neonatal"),
    ("Taller de bioseguridad y EPP",
     "Sala 012", date(2026, 5,  7), "08:00", "09:30",
     None, "001D", "2026-1", None),
    ("Taller de quimica analitica",
     "Sala 013", date(2026, 5, 14), "10:00", "12:00",
     "Paz Rodriguez",  "001D", "2026-1", None),
    ("Taller de toma de muestra",
     "Sala 011", date(2026, 5, 21), "08:00", "10:00",
     None, "001D", "2026-1", None),
    ("Taller de bioseguridad de laboratorio",
     "Sala 012", date(2026, 5, 28), "08:00", "09:30",
     None, "001D", "2026-1", None),
    ("Taller de primeros auxilios odontologicos",
     "Sala 07 - Odontologia", date(2026, 6,  4), "09:00", "11:00",
     None, "001D", "2026-1", None),
    ("Taller de evaluacion de condicion fisica",
     "Sala 015", date(2026, 6, 11), "08:00", "10:00",
     None, "001D", "2026-1", None),
]

# Formato: (taller_nombre, fecha, estado, hora_inicio_rev, hora_fin_rev, notas, items)
# (taller_nombre, fecha) forma la clave compuesta que referencia PROGRAMACIONES_DATA.
# items: [(tipo, nombre, cantidad_esperada, cantidad_encontrada, conforme, notas_item)]
# tipo: 'insumo' | 'implemento' | 'activo_fijo'
REVISIONES_SALA_DATA = [
    ("Taller de venopuncion", date(2026, 3, 12), "completada", "10:35", "10:55", None, [
        ("insumo",     "Guantes de latex talla M",          30, 28, True,  None),
        ("insumo",     "Cateter venoso periferico 20G",     10,  9, True,  None),
        ("implemento", "Esfigmomanometro aneroide",          2,  2, True,  None),
        ("implemento", "Torniquete venoso",                  5,  5, True,  None),
    ]),
    ("Taller de sutura basica", date(2026, 3, 26), "completada", "10:35", "11:00", None, [
        ("insumo",     "Gasa esteril 10x10 cm",            20, 18, True,  None),
        ("insumo",  "Seda 2-0 con aguja triangular", 15, 13, True, "2 sobres con empaque danado"),
        ("implemento", "Pinza Adson con dientes",        4,  4, True,  None),
        ("implemento", "Porta aguja Hegar",              4,  3, False, "Una unidad no devuelta"),
    ]),
    ("Taller de RCP avanzado", date(2026, 4, 9), "completada", "11:05", "11:25", None, [
        ("insumo",      "Mascarillas quirurgicas",        20, 20, True, None),
        ("implemento",  "Bolsa autoinflable AMBU adulto", 3,  3, True, None),
        ("activo_fijo", "SimMan 3G",              None, None, True, "Falla en modulo de sonidos"),
        ("activo_fijo", "Camilla articulada con barandas", None, None, True, None),
    ]),
    ("Taller de cuidados al recien nacido", date(2026, 4, 23),
     "completada", "11:35", "11:55", None, [
        ("insumo",      "Guantes de latex talla S",      25, 24, True, None),
        ("insumo",      "Aposito adhesivo 10x8 cm",      15, 15, True, None),
        ("activo_fijo", "ALS Simulator neonatal",
         None, None, False, "Bateria baja, enviado a mantenimiento"),
    ]),
    ("Taller de bioseguridad y EPP", date(2026, 5, 7), "completada", "09:35", "09:50", None, [
        ("insumo",     "Guantes nitrilo sin polvo talla M", 25, 25, True, None),
        ("insumo",     "Mascarillas N95 FFP2",              25, 24, True, None),
        ("implemento", "Gafas de proteccion",        25, 23, True, "2 unidades con vidrio rayado"),
        ("implemento", "Careta de proteccion facial",       10, 10, True,  None),
    ]),
    ("Taller de quimica analitica", date(2026, 5, 14), "completada", "12:05", "12:20", None, [
        ("insumo",     "Alcohol isopropilico 70% 1000ml",    5,  5, True,  None),
        ("insumo",     "Clorhexidina gluconato 4% 500ml",    5,  4, True,  "Un frasco incompleto"),
        ("implemento", "Gafas de proteccion",               20, 20, True,  None),
    ]),
    ("Taller de toma de muestra", date(2026, 5, 21), "completada", "10:05", "10:20", None, [
        ("insumo",     "Aguja hipodermica 21G x 1.5",       80, 80, True,  None),
        ("insumo",     "Lancetas descartables x100",         10, 10, True,  None),
        ("implemento", "Torniquete venoso",                   8,  7, True,  "Una unidad en lavado"),
    ]),
    ("Taller de bioseguridad de laboratorio", date(2026, 5, 28),
     "completada", "09:35", "09:50", None, [
        ("insumo",     "Bolsa roja residuos peligrosos 60L",  5,  5, True, None),
        ("insumo",     "Contenedor biohazard 30L",             3,  3, True, None),
        ("implemento", "Gafas de proteccion",                 25, 24, True, None),
    ]),
    ("Taller de primeros auxilios odontologicos", date(2026, 6, 4),
     "en_revision", "11:05", None, None, [
        ("insumo",     "Gasa esteril 10x10 cm",             10, None, None, None),
        ("implemento", "Esfigmomanometro aneroide",           5, None, None, None),
    ]),
    ("Taller de evaluacion de condicion fisica", date(2026, 6, 11),
     "en_revision", "10:05", None, None, [
        ("insumo",     "Guantes de latex talla M",           18, None, None, None),
        ("implemento", "Cinta metrica flexible",              8,  None, None, None),
    ]),
]

# Formato: (activo_nombre, tipo, descripcion, sala_nombre, fecha_hora,
#            responsable_nombre, severidad, estado)
# activo_nombre referencia ACTIVOS_FIJOS_DEMO por nombre unico.
# sala_nombre referencia SALAS por nombre unico.
INCIDENCIAS_DATA = [
    ("SimMan 3G",
     TipoIncidencia.mal_funcionamiento,
     "Modulo de sonidos respiratorios sin respuesta durante simulacion de "
     "insuficiencia respiratoria. No reproduce ruidos pulmonares ni cardiacos.",
     "Sala 010",
     datetime(2026, 4, 9, 11, 20, tzinfo=timezone.utc),
     "Michael Torres",
     SeveridadIncidencia.moderada,
     EstadoIncidencia.en_revision),
    ("ALS Simulator neonatal",
     TipoIncidencia.mal_funcionamiento,
     "Bateria principal con descarga completa durante taller. "
     "Equipo se apago a los 40 minutos de uso.",
     "Sala 016",
     datetime(2026, 4, 23, 11, 10, tzinfo=timezone.utc),
     None,
     SeveridadIncidencia.critica,
     EstadoIncidencia.abierta),
    ("Nursing Anne",
     TipoIncidencia.pieza_perdida,
     "Brazalete de identificacion y capucha de simulacion no encontrados "
     "al cierre de sala. Posiblemente extraviados durante limpieza.",
     "Sala 011",
     datetime(2026, 3, 26, 11, 5, tzinfo=timezone.utc),
     "Paz Rodriguez",
     SeveridadIncidencia.leve,
     EstadoIncidencia.resuelta),
]

# Formato: (proveedor_key, tipo, estado, actividad_duoc, notas, items)
# proveedor_key referencia proveedores_map; None = sin proveedor asignado.
# items: [(insumo_nombre, cantidad_pedida, cantidad_recibida, costo_unitario, estado_item)]
# insumo_nombre referencia INSUMOS por nombre unico.
ORDENES_ENTRADA_DATA = [
    ("medsupply", TipoOrden.semanal, EstadoOrdenEntrada.cerrada,
     "1010", "Reposicion semanal de insumos de alta rotacion - sem 15",
     [
         ("Guantes de latex talla M",        200, 200, 3500, EstadoItemOrden.recibido),
         ("Mascarillas quirurgicas",          100, 100, 4000, EstadoItemOrden.recibido),
         ("Gasa esteril 10x10 cm",           200, 180,  650, EstadoItemOrden.recibido_parcial),
         ("Jeringa 10ml con aguja 21G",        50,  50,  380, EstadoItemOrden.recibido),
     ]),
    ("laerdal", TipoOrden.semestral, EstadoOrdenEntrada.confirmada,
     "1060", "Repuestos y accesorios anuales para phantomas Laerdal",
     [
         ("Resucitador AMBU con mascarilla",   2, None, 110000, EstadoItemOrden.pendiente),
         ("Bolsa autoinflable AMBU adulto",     2, None,  95000, EstadoItemOrden.pendiente),
     ]),
    ("medsupply", TipoOrden.emergencia, EstadoOrdenEntrada.borrador,
     "1137", "Reposicion urgente de sueros - stock critico",
     [
         ("Suero fisiologico NaCl 0.9% 1L",   20, None, 3500, EstadoItemOrden.pendiente),
         ("Suero fisiologico 0.9% 250ml",      30, None, 1800, EstadoItemOrden.pendiente),
         ("Solucion Ringer Lactato 1L",        15, None, 3200, EstadoItemOrden.pendiente),
     ]),
]


# ===========================================================================
# Utilidades
# ===========================================================================

def _prefijo_codigo(nombre: str) -> str:
    """Misma logica que el backend para generar prefijo de 3 chars."""
    n = (
        nombre.upper()
        .replace("Á", "A").replace("É", "E").replace("Í", "I")
        .replace("Ó", "O").replace("Ú", "U").replace("Ñ", "N")
    )
    return re.sub(r"[^A-Z0-9]", "", n)[:3].ljust(3, "X")


def fecha_aleatoria(dias_min, dias_max):
    ahora = datetime.now(timezone.utc)
    return ahora - timedelta(
        days=random.randint(dias_min, dias_max),
        hours=random.randint(0, 12),
        minutes=random.randint(0, 59),
    )


def _crear_paquete(db, taller_id, semestre, notas, usuario_id,
                   items, insumos_db):
    """Crea un PaqueteInsumo con sus items. Ignora items fuera de rango."""
    p = PaqueteInsumo(
        taller_id=taller_id, semestre=semestre,
        creado_por_id=usuario_id, notas=notas,
    )
    db.add(p)
    db.flush()
    for insumo_idx, cantidad, nota in items:
        if insumo_idx < len(insumos_db):
            db.add(PaqueteItem(
                paquete_id=p.id,
                insumo_id=insumos_db[insumo_idx].id,
                cantidad_requerida=cantidad,
                notas=nota,
            ))
        else:
            print(
                f"  ADVERTENCIA: paquete taller_id={taller_id} — "
                f"insumo_idx={insumo_idx} fuera de rango "
                f"(max={len(insumos_db) - 1}), item ignorado"
            )
    return p


# ===========================================================================
# Helpers de insercion
# ===========================================================================

def _limpiar(db) -> None:
    print("\nLimpiando datos existentes...")
    db.query(RevisionSalaItem).delete()
    db.query(RevisionSala).delete()
    db.query(OrdenMantenimientoItem).delete()
    db.query(PaqueteItem).delete()
    db.query(PaqueteInsumo).delete()
    db.query(ProgramacionTaller).delete()
    db.query(Taller).delete()
    db.query(UnidadImplemento).delete()
    db.query(OrdenMantenimiento).delete()
    db.query(Incidencia).delete()
    db.query(OrdenEntradaItem).delete()
    db.query(OrdenEntrada).delete()
    db.query(ActivoFijo).delete()
    db.query(Proveedor).delete()
    db.query(RetornoImplemento).delete()
    db.query(AuditLog).delete()
    db.query(SolicitudItem).delete()
    db.query(SolicitudRetiro).delete()
    db.query(Movimiento).delete()
    db.query(ClaseDocente).delete()
    db.query(ComentarioDocente).delete()
    db.query(Docente).delete()
    db.query(Insumo).delete()
    db.query(Asignatura).delete()
    db.query(Sala).delete()
    db.query(Categoria).delete()
    db.query(Usuario).delete()
    db.commit()
    print("  OK")


def _insertar_salas(db) -> dict:
    print("Insertando salas...")
    salas_por_nombre = {}
    for nombre, tipo, desc in SALAS:
        s = Sala(nombre=nombre, tipo=tipo, descripcion=desc)
        db.add(s)
        salas_por_nombre[nombre] = s
    db.flush()
    print(f"  {len(salas_por_nombre)} salas")
    return salas_por_nombre


def _insertar_categorias(db) -> list:
    print("Insertando categorias...")
    cats = []
    for nombre in CATEGORIAS:
        c = Categoria(nombre=nombre)
        db.add(c)
        cats.append(c)
    db.flush()
    print(f"  {len(cats)} categorias")
    return cats


def _insertar_usuarios(db) -> tuple:
    print("Insertando usuarios...")
    usuarios = []
    for nombre, email, pwd, rol in USUARIOS:
        u = Usuario(
            nombre=nombre, email=email,
            password_hash=hashear_password(pwd), rol=rol,
        )
        db.add(u)
        usuarios.append(u)
    db.flush()
    operadores = [u for u in usuarios if u.rol == RolUsuario.operador]
    print(f"  {len(usuarios)} usuarios")
    return usuarios, operadores


def _insertar_proveedores(db) -> dict:
    print("Insertando proveedores...")
    prov_laerdal = Proveedor(
        nombre="Laerdal Medical Chile SpA",
        rut="76.543.210-K",
        contacto_nombre="Roberto Salas",
        contacto_email="rsalas@laerdal.cl",
        telefono="+56 2 2345 6789",
        url_seneg="https://www.senegocia.com/proveedor/laerdal-chile",
        notas=(
            "Proveedor oficial de phantomas Laerdal. "
            "Mantenimiento preventivo semestral incluido en contrato."
        ),
    )
    prov_medsupply = Proveedor(
        nombre="MedSupply SpA",
        rut="76.111.222-3",
        contacto_nombre="Patricia Vega",
        contacto_email="pvega@medsupply.cl",
        telefono="+56 9 8765 4321",
        url_seneg=None,
        notas="Proveedor general de insumos medicos desechables.",
    )
    db.add(prov_laerdal)
    db.add(prov_medsupply)
    db.flush()
    print("  2 proveedores (Laerdal Chile, MedSupply SpA)")
    return {"laerdal": prov_laerdal.id, "medsupply": prov_medsupply.id}


def _insertar_docentes(db) -> dict:
    print("Insertando docentes...")
    docentes_por_nombre = {}
    for nombre, email, rut in DOCENTES_DATA:
        d = Docente(nombre=nombre, email=email, rut=rut, activo=True)
        db.add(d)
        docentes_por_nombre[nombre] = d
    db.flush()
    print(f"  {len(docentes_por_nombre)} docentes (Paz Rodriguez, Michael Torres)")
    return docentes_por_nombre


def _insertar_asignaturas(db) -> dict:
    print("Insertando asignaturas...")
    asignaturas_por_codigo = {}
    for nombre, codigo, carrera in ASIGNATURAS:
        a = Asignatura(nombre=nombre, codigo=codigo, carrera=carrera)
        db.add(a)
        asignaturas_por_codigo[codigo] = a
    db.flush()
    print(f"  {len(asignaturas_por_codigo)} asignaturas (5 carreras)")
    return asignaturas_por_codigo


def _insertar_clases(db, docentes_por_nombre, asignaturas_por_codigo) -> list:
    print("Insertando clases...")
    clases = []
    for doc_nombre, asig_codigo, seccion, semestre, num_est in CLASES_DOCENTE:
        c = ClaseDocente(
            docente_id=docentes_por_nombre[doc_nombre].id,
            asignatura_id=asignaturas_por_codigo[asig_codigo].id,
            seccion=seccion, semestre=semestre, num_estudiantes=num_est,
        )
        db.add(c)
        clases.append(c)
    db.flush()
    print(f"  {len(clases)} clases (semestre 2026-1)")
    return clases


def _insertar_insumos(db, cats) -> list:
    print("Insertando insumos...")
    insumos_db = []
    for nombre, unidad_medida, stock, minimo, cat_idx, tipo, costo in INSUMOS:
        i = Insumo(
            nombre=nombre,
            descripcion=unidad_medida,
            unidad_medida=unidad_medida,
            stock_actual=stock,
            stock_minimo=minimo,
            sala_id=None,
            categoria_id=cats[cat_idx].id,
            tipo=TipoInsumo(tipo),
            costo_unitario=costo,
        )
        db.add(i)
        insumos_db.append(i)
    db.flush()
    for ins in insumos_db:
        if not ins.sku:
            ins.sku = f"HST-{ins.id:05d}"
    db.flush()
    n_implementos = sum(1 for i in insumos_db if i.tipo == TipoInsumo.implemento)
    print(f"  {len(insumos_db)} insumos ({n_implementos} implementos)")
    return insumos_db


def _insertar_unidades_implemento(
    db, implementos_list, salas_por_nombre, cats_por_nombre
) -> int:
    print("Insertando unidades fisicas de implementos...")
    total_unidades = 0
    salas_clinicas = [
        salas_por_nombre["Sala 010"],
        salas_por_nombre["Sala 011"],
        salas_por_nombre["Sala 012"],
    ]
    cat_epp_id = cats_por_nombre["Proteccion Personal (EPP)"].id
    for impl in implementos_list:
        prefijo = _prefijo_codigo(impl.nombre)
        cantidad = random.randint(2, 5)
        for j in range(cantidad):
            estado = random.choice([
                EstadoUnidad.disponible, EstadoUnidad.disponible,
                EstadoUnidad.disponible, EstadoUnidad.en_uso,
            ])
            if j == 0 and impl.categoria_id == cat_epp_id:
                sala_asignada = salas_clinicas[0].id
            elif j == 1 and impl.categoria_id == cat_epp_id:
                sala_asignada = salas_clinicas[1].id
            else:
                sala_asignada = None
            u = UnidadImplemento(
                implemento_id=impl.id,
                estado=estado,
                sala_id=sala_asignada,
            )
            db.add(u)
            db.flush()
            u.codigo = f"{prefijo}-{u.id:05d}"
            total_unidades += 1
    db.commit()
    print(
        f"  {total_unidades} unidades "
        f"({len(implementos_list)} implementos cubiertos)"
    )
    return total_unidades


def _insertar_activos_fijos(db, salas_por_nombre, proveedores_map) -> tuple:
    print("Insertando activos fijos...")
    activos_por_nombre = {}
    for (nombre, desc, tipo, sala_nombre,
         fidelidad, notas, prov_key) in ACTIVOS_FIJOS_DEMO:
        prov_id = proveedores_map.get(prov_key) if prov_key else None
        af = ActivoFijo(
            nombre=nombre, descripcion=desc, tipo=tipo,
            sala_id=salas_por_nombre[sala_nombre].id, fidelidad=fidelidad,
            estado=EstadoActivo.disponible, notas=notas,
            proveedor_id=prov_id,
        )
        db.add(af)
        activos_por_nombre[nombre] = af
        db.flush()
        prefijo_af = "MUE" if tipo == TipoActivo.mueble else "PHN"
        af.codigo_interno = f"{prefijo_af}-{af.id:05d}"
    db.commit()
    n_muebles = sum(1 for a in ACTIVOS_FIJOS_DEMO if a[2] == TipoActivo.mueble)
    n_phantomas = len(ACTIVOS_FIJOS_DEMO) - n_muebles
    print(
        f"  {len(activos_por_nombre)} activos fijos "
        f"({n_muebles} muebles, {n_phantomas} phantomas)"
    )
    return activos_por_nombre, n_muebles, n_phantomas


def _insertar_orden_mantenimiento(
    db, activos_por_nombre, proveedores_map, operadores
) -> None:
    print("Insertando orden de mantenimiento demo...")
    simman = activos_por_nombre["SimMan 3G"]
    als    = activos_por_nombre["ALS Simulator neonatal"]
    simman.estado = EstadoActivo.en_mantenimiento
    als.estado    = EstadoActivo.en_mantenimiento

    orden_demo = OrdenMantenimiento(
        proveedor_id=proveedores_map["laerdal"],
        creado_por_id=operadores[0].id,
        estado=EstadoOrden.en_curso,
        fecha_visita=date.today() - timedelta(days=12),
        notas=(
            "Visita semestral preventiva Laerdal Chile. "
            "SimMan con falla en modulo de sonidos respiratorios. "
            "ALS Neonatal: revision de bateria y sensores."
        ),
    )
    db.add(orden_demo)
    db.flush()

    db.add(OrdenMantenimientoItem(
        orden_id=orden_demo.id,
        activo_fijo_id=simman.id,
        resultado=ResultadoItem.pendiente,
        descripcion_problema=(
            "Falla en modulo de sonidos respiratorios. "
            "No reproduce ruidos pulmonares durante simulacion "
            "de insuficiencia respiratoria."
        ),
    ))
    db.add(OrdenMantenimientoItem(
        orden_id=orden_demo.id,
        activo_fijo_id=als.id,
        resultado=ResultadoItem.pendiente,
        descripcion_problema=(
            "Revision preventiva de bateria y calibracion de sensores."
        ),
    ))
    db.commit()
    print("  1 orden (2 items: SimMan 3G + ALS Neonatal, en_curso)")


def _insertar_movimientos(db, insumos_db, usuarios, operadores) -> int:
    print("Insertando movimientos...")
    total_movs = 0
    for insumo in insumos_db:
        en_alerta = insumo.stock_actual <= insumo.stock_minimo
        ne = random.randint(1, 2) if en_alerta else random.randint(2, 4)
        ns = random.randint(5, 9) if en_alerta else random.randint(3, 7)
        rne = (40, 60) if en_alerta else (3, 50)
        rns = (0, 25) if en_alerta else (0, 50)
        subtipo_salida = (
            SubtipoMovimiento.prestamo_implemento
            if insumo.tipo == TipoInsumo.implemento
            else SubtipoMovimiento.consumo_taller
        )
        for _ in range(ne):
            db.add(Movimiento(
                tipo=TipoMovimiento.entrada,
                subtipo=SubtipoMovimiento.compra,
                cantidad=random.randint(30, 150),
                motivo=random.choice(MOTIVOS_ENTRADA),
                fecha=fecha_aleatoria(*rne),
                insumo_id=insumo.id,
                usuario_id=random.choice(operadores).id,
            ))
            total_movs += 1
        for _ in range(ns):
            db.add(Movimiento(
                tipo=TipoMovimiento.salida,
                subtipo=subtipo_salida,
                cantidad=random.randint(1, 8),
                motivo=random.choice(MOTIVOS_SALIDA),
                fecha=fecha_aleatoria(*rns),
                insumo_id=insumo.id,
                usuario_id=random.choice(usuarios).id,
            ))
            total_movs += 1
    db.commit()
    print(f"  {total_movs} movimientos (tipo + subtipo)")
    return total_movs


def _insertar_talleres(db, asignaturas_por_codigo) -> dict:
    print("Insertando talleres...")
    talleres_por_nombre = {}
    for nombre, desc, asig_codigo in TALLERES_DATA:
        t = Taller(
            nombre=nombre, descripcion=desc,
            asignatura_id=asignaturas_por_codigo[asig_codigo].id,
        )
        db.add(t)
        talleres_por_nombre[nombre] = t
    db.flush()
    print(f"  {len(talleres_por_nombre)} talleres (5 carreras)")
    return talleres_por_nombre


def _insertar_paquetes(db, talleres_por_nombre, insumos_db, operadores) -> int:
    print("Insertando paquetes de insumos...")
    total_paquetes = 0
    for taller_nombre, semestre, notas, items in PAQUETES_DATA:
        _crear_paquete(
            db,
            taller_id=talleres_por_nombre[taller_nombre].id,
            semestre=semestre, notas=notas,
            usuario_id=operadores[0].id,
            items=items, insumos_db=insumos_db,
        )
        total_paquetes += 1
    db.commit()
    print(f"  {total_paquetes} paquetes (5 carreras, semestre 2026-1)")
    return total_paquetes


def _insertar_programaciones(db, talleres_por_nombre, salas_por_nombre) -> dict:
    print("Insertando programaciones de talleres...")
    programaciones_por_clave = {}
    for (taller_nombre, sala_nombre, fecha, hora_inicio, hora_fin,
         docente_nombre, seccion, semestre, notas) in PROGRAMACIONES_DATA:
        p = ProgramacionTaller(
            taller_id=talleres_por_nombre[taller_nombre].id,
            sala_id=salas_por_nombre[sala_nombre].id,
            fecha=fecha,
            hora_inicio=hora_inicio,
            hora_fin=hora_fin,
            docente_nombre=docente_nombre,
            seccion=seccion,
            semestre=semestre,
            notas=notas,
        )
        db.add(p)
        programaciones_por_clave[f"{taller_nombre}|{fecha}"] = p
    db.flush()
    print(f"  {len(programaciones_por_clave)} programaciones (semestre 2026-1)")
    return programaciones_por_clave


def _insertar_revisiones_sala(
    db, programaciones_por_clave, salas_por_nombre, operadores
) -> int:
    print("Insertando revisiones de sala...")
    total_revisiones = 0
    total_items = 0
    for (taller_nombre, fecha, estado, hora_inicio_rev, hora_fin_rev,
         notas, items) in REVISIONES_SALA_DATA:
        prog = programaciones_por_clave[f"{taller_nombre}|{fecha}"]
        rev = RevisionSala(
            programacion_id=prog.id,
            sala_id=prog.sala_id,
            fecha=prog.fecha,
            operador_id=random.choice(operadores).id,
            estado=estado,
            hora_inicio_rev=hora_inicio_rev,
            hora_fin_rev=hora_fin_rev,
            notas=notas,
        )
        db.add(rev)
        db.flush()
        for (tipo, nombre, cant_esp, cant_enc, conforme, notas_item) in items:
            db.add(RevisionSalaItem(
                revision_id=rev.id,
                tipo=tipo,
                nombre=nombre,
                cantidad_esperada=cant_esp,
                cantidad_encontrada=cant_enc,
                conforme=conforme,
                notas_item=notas_item,
            ))
            total_items += 1
        total_revisiones += 1
    db.commit()
    print(f"  {total_revisiones} revisiones, {total_items} items")
    return total_revisiones


def _insertar_incidencias(db, activos_por_nombre, salas_por_nombre, usuarios) -> int:
    print("Insertando incidencias...")
    for (activo_nombre, tipo, descripcion, sala_nombre,
         fecha_hora, responsable_nombre, severidad, estado) in INCIDENCIAS_DATA:
        db.add(Incidencia(
            activo_fijo_id=activos_por_nombre[activo_nombre].id,
            tipo=tipo,
            descripcion=descripcion,
            sala_id=salas_por_nombre[sala_nombre].id,
            fecha_hora=fecha_hora,
            responsable_nombre=responsable_nombre,
            severidad=severidad,
            estado=estado,
        ))
    db.commit()
    print(f"  {len(INCIDENCIAS_DATA)} incidencias")
    return len(INCIDENCIAS_DATA)


def _insertar_ordenes_entrada(
    db, proveedores_map, insumos_db, usuarios, operadores
) -> int:
    print("Insertando ordenes de entrada...")
    insumos_por_nombre = {i.nombre: i for i in insumos_db}
    total_ordenes = 0
    for (prov_key, tipo, estado, actividad_duoc,
         notas, items) in ORDENES_ENTRADA_DATA:
        prov_id = proveedores_map.get(prov_key) if prov_key else None
        cerrado_por_id = operadores[0].id if estado == EstadoOrdenEntrada.cerrada else None
        orden = OrdenEntrada(
            proveedor_id=prov_id,
            tipo=tipo,
            estado=estado,
            actividad_duoc=actividad_duoc,
            notas=notas,
            creado_por_id=operadores[0].id,
            cerrado_por_id=cerrado_por_id,
        )
        db.add(orden)
        db.flush()
        for (insumo_nombre, cant_pedida, cant_recibida,
             costo_unitario, estado_item) in items:
            db.add(OrdenEntradaItem(
                orden_id=orden.id,
                tipo_item=TipoItemOrden.insumo,
                insumo_id=insumos_por_nombre[insumo_nombre].id,
                cantidad_pedida=cant_pedida,
                cantidad_recibida=cant_recibida,
                costo_unitario=costo_unitario,
                estado=estado_item,
            ))
        total_ordenes += 1
    total_items_entrada = sum(len(its) for *_, its in ORDENES_ENTRADA_DATA)
    db.commit()
    print(f"  {total_ordenes} ordenes ({total_items_entrada} items)")
    return total_ordenes


# ===========================================================================
# Punto de entrada
# ===========================================================================

def main():
    db = SessionLocal()
    try:
        print("\nHestia - Cargador de datos de demo")
        print("=" * 40)
        if input(
            "Esto eliminara TODOS los datos existentes. Continuar? (s/N): "
        ).strip().lower() != "s":
            print("Cancelado.")
            return

        _limpiar(db)
        salas_por_nombre     = _insertar_salas(db)
        cats                 = _insertar_categorias(db)
        cats_por_nombre      = {c.nombre: c for c in cats}
        usuarios, operadores = _insertar_usuarios(db)
        proveedores_map      = _insertar_proveedores(db)
        docentes_por_nombre  = _insertar_docentes(db)
        asignaturas_por_codigo = _insertar_asignaturas(db)
        clases     = _insertar_clases(db, docentes_por_nombre, asignaturas_por_codigo)
        insumos_db = _insertar_insumos(db, cats)
        implementos_list = [i for i in insumos_db if i.tipo == TipoInsumo.implemento]
        total_unidades = _insertar_unidades_implemento(
            db, implementos_list, salas_por_nombre, cats_por_nombre,
        )
        activos_por_nombre, n_muebles, n_phantomas = _insertar_activos_fijos(
            db, salas_por_nombre, proveedores_map,
        )
        _insertar_orden_mantenimiento(db, activos_por_nombre, proveedores_map, operadores)
        total_movs     = _insertar_movimientos(db, insumos_db, usuarios, operadores)
        talleres_por_nombre = _insertar_talleres(db, asignaturas_por_codigo)
        total_paquetes = _insertar_paquetes(db, talleres_por_nombre, insumos_db, operadores)
        programaciones_por_clave = _insertar_programaciones(
            db, talleres_por_nombre, salas_por_nombre,
        )
        total_revisiones = _insertar_revisiones_sala(
            db, programaciones_por_clave, salas_por_nombre, operadores,
        )
        total_incidencias = _insertar_incidencias(
            db, activos_por_nombre, salas_por_nombre, usuarios,
        )
        total_ordenes_entrada = _insertar_ordenes_entrada(
            db, proveedores_map, insumos_db, usuarios, operadores,
        )

        alertas = sum(1 for _, _, s, m, *_ in INSUMOS if s <= m)
        print("\n" + "=" * 40)
        print("Demo cargada exitosamente.")
        print(f"  Salas:             {len(salas_por_nombre)}")
        print(f"  Categorias:        {len(cats)}")
        print(f"  Usuarios:          {len(usuarios)}")
        print("  Proveedores:       2 (Laerdal Chile, MedSupply SpA)")
        print(f"  Docentes:          {len(docentes_por_nombre)} (Paz Rodriguez, Michael Torres)")
        print(f"  Asignaturas:       {len(asignaturas_por_codigo)} (5 carreras)")
        print(f"  Clases:            {len(clases)}")
        print(
            f"  Insumos:           {len(insumos_db)} "
            f"({alertas} en alerta) - todos en Bodega"
        )
        print(
            f"  Implementos:       {len(implementos_list)} "
            f"con {total_unidades} unidades fisicas"
        )
        print(
            f"  Activos fijos:     {len(activos_por_nombre)} "
            f"({n_muebles} muebles, {n_phantomas} phantomas)"
        )
        print("  Ordenes mant.:     1 (SimMan 3G + ALS Neonatal, en_curso)")
        print(f"  Movimientos:       {total_movs} (tipo + subtipo)")
        print(f"  Talleres:          {len(talleres_por_nombre)}")
        print(f"  Paquetes:          {total_paquetes}")
        print(f"  Programaciones:    {len(programaciones_por_clave)}")
        print(f"  Revisiones sala:   {total_revisiones}")
        print(f"  Incidencias:       {total_incidencias}")
        print(f"  Ordenes entrada:   {total_ordenes_entrada}")
        print("\nCredenciales:")
        for _, email, pwd, rol in USUARIOS:
            print(f"  {email:38} | {pwd:12} | {rol.value}")
        print()

    except Exception as e:
        db.rollback()
        print(f"\nError: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
