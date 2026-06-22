"""
cruzar_datos.py — Cruce de datos entre los CSVs de output para complementar
información faltante en programacion_talleres sin alterar la estructura de columnas.

Qué hace:
  1. Re-lee los docx de guías con el contexto de su carpeta (asig_code + sala_lab)
  2. Mapea folder → codigo_asignatura del horario_academico
  3. Enriquece programacion_talleres_S1/S2 con:
       - Sala    → sala más representativa del horario para ese código
       - Seccion → secciones únicas en horario (separadas por " | ")
       - Horario → dia + hora del horario (cuando disponible)
  4. Guarda los CSVs actualizados (sobreescribe output/)
"""

import io
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

for pkg in ["openpyxl", "python-docx", "pandas"]:
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg,
                           "--break-system-packages", "-q"])

import pandas as pd
from docx import Document

BASE = Path(__file__).parent
OUTPUT = BASE / "output"

# ── Mapeo carpeta-guía → codigo_asignatura en horario ────────────────────────
# Clave: fragmento del nombre de carpeta (uppercase, sin espacios) o nombre exacto
# Valor: codigo_asignatura tal como aparece en horario_academico

FOLDER_TO_HORARIO = {
    # ── Semestre 1 · Banco de Sangre ─────────────────────────────────────────
    "APS1121":   "PREP.DEPACIENTES",
    "ATS1111":   "AD.TOMADEMUESTRA",
    "BIS1111":   "BIOSEGURIDAD",
    "BSS3111":   "TEC.BANCOSANGRE",
    "LCS1111":   "PREP.DELAB.CLINICO",
    "LCS3111":   "MICROBIOLOGÍA",
    "TMS1111":   "TOMADEMUESTRA",
    # ── Semestre 1 · TENS ────────────────────────────────────────────────────
    "ANATOMIA-AFS1111":           "ANATOMIA",
    "BIOSEGURIDAD-EBS1121":       "BIOSEGURIDAD",
    "MANEJODEEQUIPOS-MES3111":    "MANEJODEEQUIPOS",
    "PEDIATRIA-CES3111":          "PEDIATRIA",
    "PRIMEROSAUXILIOS-AXS1102":   "PRIMEROSAUXILIOS",
    "TECNICASBASICAS-EBS1111":    "ROLDELTENS",
    "URGENCIAS-CES3121":          "URGENCIAS",
    # ── Semestre 1 · Odontología ─────────────────────────────────────────────
    "ENDODONCIA-EOS3131":         "ENDODONCIA",
    "ODRESTAADORAEEOS3111":       "ODONTOLOGIARESTAURADORA",  # OD RESTAURADORA EOS3111
    "ODRESTAADORAEEOS3111":       "ODONTOLOGIARESTAURADORA",
    "ANATOMIA":                   "ANATOMIA",
    "MANEJODEEQUIPOS":            "MANEJODEEQUIPOS",
    # Técnicas de diagnóstico → RX
    "TÉCNICASDEDIAGNOSTICOENODONTOLOGÍA": "RX",
    "TECNICASDEDIAGNOSTICOENODONTOLOGIA": "RX",
    # ── Semestre 2 · Banco de Sangre / TSLB ──────────────────────────────────
    "AXS1102":   "PRIMAUX",
    "BSS2111":   "BSS2111",
    "LCS2111":   "LCS2111",
    # ── Semestre 2 · TENS ────────────────────────────────────────────────────
    "ADMINISTRACIÓNDEFÁRMACOSOKEEBS2111":   "FARMACOS",
    "ADMINISTRACIONDEFARMACOSOKEEBS2111":   "FARMACOS",
    "HABILIDADESPARAELTRABAJOOKES4111":     "HABILIDADES",
    "HABILIDADESPARAELTRABAJOOKES4111":     "HABILIDADES",
    "MATERNO":                              "MATERNO",
    "MÉDICOQUIRÚRGICOOKES2121":             "MQ",
    "MEDICOQUIRURGICOOKES2121":             "MQ",
    "PROMOCIÓNENSALUDOK":                   "PROMOCION",
    "PROMOCIONENSALUDOK":                   "PROMOCION",
    "SALUDMENTALOKECES4111":                "SALUDMENTAL",
    "SALUDMENTALOKECES4111":                "SALUDMENTAL",
    # ── Semestre 2 · Odontología ─────────────────────────────────────────────
    "BIOMATERIALES":                        "BIOMATERIALES",
    "BIOSEGURIDAD":                         "BIOSEGURIDAD",
    "ODONTOPEDIATRIA":                      "ODONTOPEDIATRIA",
    "ORTODONCIAYORTOPEDIA":                 "ORTODONCIA",
    "PERIODONCIA":                          "PERIODONCIA",
    "PROMOCIONYPREVENCIÓENNSALUD":          "PROMOCIONSB",
    "REHABILITACIÓN":                       "REHABILITACIONORAL",
    "REHABILITACION":                       "REHABILITACIONORAL",
}

# Sala de laboratorio por disciplina (carpeta padre de guías)
DISCIPLINA_SALA = {
    "BANCO SANGRE": "Banco de Sangre",
    "BANCO DE SANGRE": "Banco de Sangre",
    "TENS": "TENS",
    "ODONTOLOGIA": "Odontología",
    "ODONTOLOGÍA": "Odontología",
    "QUIMICA": "Química",
    "QUÍMICA": "Química",
}


def folder_key(name: str) -> str:
    """Normaliza nombre de carpeta para buscar en FOLDER_TO_HORARIO."""
    s = re.sub(r"\s+", "", name).upper()
    # Eliminar tilde (normalización básica)
    s = s.replace("Á","A").replace("É","E").replace("Í","I").replace("Ó","O").replace("Ú","U")
    s = s.replace("Ñ","N")
    return s


def folder_to_horario_code(folder_name: str) -> str | None:
    """Retorna el codigo_asignatura correspondiente a una carpeta de guía."""
    key = folder_key(folder_name)
    # Búsqueda exacta primero
    if key in FOLDER_TO_HORARIO:
        return FOLDER_TO_HORARIO[key]
    # Búsqueda por versión con tildes
    plain = folder_name.upper().strip()
    for k, v in FOLDER_TO_HORARIO.items():
        if k in plain or plain.startswith(k):
            return v
    # Búsqueda parcial: extrae código alfanumérico del nombre
    codes = re.findall(r"[A-Z]{2,4}\d{4}", folder_name.upper())
    for c in codes:
        if c in FOLDER_TO_HORARIO:
            return FOLDER_TO_HORARIO[c]
    return None


def disciplina_from_path(folder_path: Path) -> str:
    """Determina la sala de laboratorio a partir de la jerarquía de carpetas."""
    for part in reversed(folder_path.parts):
        up = part.upper()
        for key, val in DISCIPLINA_SALA.items():
            if key in up:
                return val
    return ""


def get_taller_name(docx_bytes: bytes) -> str:
    """Extrae el nombre de taller del primer campo 'Nombre del Taller' en tablas."""
    try:
        doc = Document(io.BytesIO(docx_bytes))
        for table in doc.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells]
                if len(cells) >= 2 and "Nombre del Taller" in cells[0]:
                    for c in cells[1:]:
                        if c and c.strip():
                            return c.strip()
    except Exception:
        pass
    return ""


def extract_guias(semestre: int) -> list[dict]:
    """Re-extrae talleres de los docx con contexto de carpeta."""
    base = BASE / f"Semestre_{semestre}"
    guias_root = None
    for d in base.iterdir():
        if d.is_dir() and "GUIA" in d.name.upper():
            guias_root = d
            break
    if not guias_root:
        return []

    records = []
    for docx_path in sorted(guias_root.rglob("*.docx")):
        content = docx_path.read_bytes()
        name = get_taller_name(content)
        if not name:
            continue

        # La carpeta inmediata del docx es la asig_folder
        asig_folder = docx_path.parent
        # Si hay sub-carpetas de tipo GUIAS ALUMNOS / GUIAS ALUMNO, sube un nivel
        if any(kw in asig_folder.name.upper() for kw in ["GUIA", "ALUMNO", "IMPRESION"]):
            asig_folder = asig_folder.parent

        horario_code = folder_to_horario_code(asig_folder.name)
        sala_lab = disciplina_from_path(asig_folder)

        records.append({
            "Nombre de Taller": name,
            "asig_code": horario_code or "",
            "sala_lab": sala_lab,
        })

    return records


def build_horario_index(horario_df: pd.DataFrame) -> dict:
    """
    Construye índice: codigo_asignatura →
        {salas: Counter, secciones: set, horarios: set}
    """
    idx = {}
    for _, row in horario_df.iterrows():
        code = str(row.get("codigo_asignatura", "")).strip()
        if not code:
            continue
        if code not in idx:
            idx[code] = {"salas": Counter(), "secciones": set(), "horarios": set()}
        sala = str(row.get("sala", "")).strip()
        if sala and sala not in ("", "nan", "None", "Sin sala asignada"):
            idx[code]["salas"][sala] += 1
        sec = str(row.get("seccion", "")).strip()
        if sec and sec not in ("", "nan", "None", "SECCI", "Sala"):
            idx[code]["secciones"].add(sec)
        dia = str(row.get("dia_semana", "")).strip()
        h_ini = str(row.get("hora_inicio", "")).strip()
        h_fin = str(row.get("hora_fin", "")).strip()
        if dia and h_ini and dia not in ("", "nan"):
            idx[code]["horarios"].add(f"{dia} {h_ini}-{h_fin}")
    return idx


def best_sala(idx_entry: dict) -> str:
    if not idx_entry["salas"]:
        return ""
    return idx_entry["salas"].most_common(1)[0][0]


_SECCION_GARBAGE = {"SECCI", "SALA", "SECCIóN", "SECCIÓN", "None", "nan"}
_YEAR_RE = re.compile(r"^\d{4}$")         # años como 2026
_DAY_RE  = re.compile(r"^(LUNES|MARTES|MI[EÉ]RCOLES|JUEVES|VIERNES|JUEVE)$", re.I)
_FLOAT_RE = re.compile(r"^\d+\.0$")       # floats tipo 5.0, 13.0


def _is_valid_seccion(s: str) -> bool:
    s = s.strip()
    if not s or s in _SECCION_GARBAGE:
        return False
    if _YEAR_RE.match(s) or _DAY_RE.match(s) or _FLOAT_RE.match(s):
        return False
    if len(s) > 12:
        return False
    return True


def format_secciones(secciones: set) -> str:
    clean = sorted(s for s in secciones if _is_valid_seccion(s))
    return " | ".join(clean[:8]) if clean else ""


def format_horarios(horarios: set) -> str:
    clean = sorted(h for h in horarios if len(h) > 4)
    return " | ".join(clean[:4]) if clean else ""


def enrich_programacion(semestre: int):
    prog_path = OUTPUT / f"programacion_talleres_S{semestre}.csv"
    horario_path = OUTPUT / f"horario_academico_S{semestre}.csv"

    if not prog_path.exists():
        print(f"  ⚠ No encontrado: {prog_path.name}")
        return 0

    prog_df = pd.read_csv(prog_path, dtype=str).fillna("")
    horario_df = pd.read_csv(horario_path, dtype=str).fillna("") if horario_path.exists() else pd.DataFrame()

    horario_idx = build_horario_index(horario_df) if not horario_df.empty else {}

    # Re-extrae guías con contexto
    guias = extract_guias(semestre)

    # Construye lookup: Nombre de Taller (normalizado) → {asig_code, sala_lab}
    guia_lookup: dict[str, dict] = {}
    for g in guias:
        key = g["Nombre de Taller"].strip().lower()
        # Solo registra si tiene información útil
        if g["asig_code"] or g["sala_lab"]:
            guia_lookup[key] = g

    enriched = 0
    for idx_row, row in prog_df.iterrows():
        nombre = row.get("Nombre de Taller", "").strip()
        if not nombre:
            continue

        # Busca en lookup (exacto primero, luego parcial)
        guia_info = guia_lookup.get(nombre.lower())
        if not guia_info:
            # Búsqueda parcial
            for key, val in guia_lookup.items():
                if nombre.lower() in key or key in nombre.lower():
                    guia_info = val
                    break

        if not guia_info:
            continue

        asig_code = guia_info.get("asig_code", "")
        sala_lab = guia_info.get("sala_lab", "")

        changed = False

        # Sala: primero desde horario (sala concreta), si no desde disciplina
        if not row.get("Sala", "").strip():
            if asig_code and asig_code in horario_idx:
                sala_val = best_sala(horario_idx[asig_code])
                if not sala_val:
                    sala_val = sala_lab
            else:
                sala_val = sala_lab
            if sala_val:
                prog_df.at[idx_row, "Sala"] = sala_val
                changed = True

        # Seccion: desde horario
        if not row.get("Seccion", "").strip():
            if asig_code and asig_code in horario_idx:
                sec_val = format_secciones(horario_idx[asig_code]["secciones"])
                if sec_val:
                    prog_df.at[idx_row, "Seccion"] = sec_val
                    changed = True

        # Horario: desde horario_academico
        if not row.get("Horario", "").strip():
            if asig_code and asig_code in horario_idx:
                hor_val = format_horarios(horario_idx[asig_code]["horarios"])
                if hor_val:
                    prog_df.at[idx_row, "Horario"] = hor_val
                    changed = True

        if changed:
            enriched += 1

    prog_df.to_csv(prog_path, index=False, encoding="utf-8-sig")
    return enriched


def enrich_insumos(semestre: int):
    """
    Enriquece insumos.sala con el código de sala del horario cuando
    la sala actual solo contiene el nombre del laboratorio.
    """
    ins_path = OUTPUT / f"insumos_S{semestre}.csv"
    horario_path = OUTPUT / f"horario_academico_S{semestre}.csv"

    if not ins_path.exists() or not horario_path.exists():
        return 0

    ins_df = pd.read_csv(ins_path, dtype=str).fillna("")
    horario_df = pd.read_csv(horario_path, dtype=str).fillna("")

    # Mapa categoria → codigo_asignatura (manual + inferido)
    # Construido usando la misma lógica que el mapeo de carpetas
    CATEGORIA_TO_HORARIO = {
        # S1
        "TÉCNICAS DE BANCO DE SANGRE":                              "TEC.BANCOSANGRE",
        "TÉCNICAS DE BANCO DE SANGRE":                              "TEC.BANCOSANGRE",
        "Microbiología para laboratorio clínico":                   "MICROBIOLOGÍA",
        "PREPARACIÓN DE LABORATORIO CLÍNICO":                       "PREP.DELAB.CLINICO",
        "PREPARACIÓN DEL PACIENTE PARA LA TOMA DE MUESTRA Y FELBOTOMÍA": "PREP.DEPACIENTES",
        "Administración para la toma de muestra":                   "AD.TOMADEMUESTRA",
        "TOMA DE MUESTRA":                                          "TOMADEMUESTRA",
        "bioseguridad":                                             "BIOSEGURIDAD",
        # S2
        "ADMINISTRACION DE FARMACOS":                               "FARMACOS",
        "Medico quirurgico":                                        "MQ",
        "INSTRUMENTAL PARA DESTARTRAJE SUPRA Y SUBGINGIVAL":        "PERIODONCIA",
        "INSTRUMENTAL DE TRATAMIENTO PERIODONTAL NO QUIRÚRGICO Y PULIDO RADICULAR": "PERIODONCIA",
        "INSTRUMENTAL DE TRATAMIENTO PERIODONTAL QUIRÚRGICO":       "PERIODONCIA",
    }

    horario_idx = build_horario_index(horario_df)

    enriched = 0
    for idx_row, row in ins_df.iterrows():
        categoria = row.get("categoria", "").strip()
        current_sala = row.get("sala", "").strip()

        # Solo procesa filas donde sala es nombre de laboratorio (no código)
        is_lab_name = any(
            lab in current_sala
            for lab in ["Banco de Sangre", "Odontología", "Química", "TENS", "Farmacia"]
        )
        if not is_lab_name:
            continue

        horario_code = CATEGORIA_TO_HORARIO.get(categoria)
        if not horario_code or horario_code not in horario_idx:
            continue

        sala_real = best_sala(horario_idx[horario_code])
        if sala_real:
            # Enriquece: "Banco de Sangre (SB-013)"
            nueva_sala = f"{current_sala} ({sala_real})"
            ins_df.at[idx_row, "sala"] = nueva_sala
            enriched += 1

    ins_df.to_csv(ins_path, index=False, encoding="utf-8-sig")
    return enriched


def main():
    print("🔗 Cruzando datos entre documentos de output...\n")

    for s in [1, 2]:
        print(f"── Semestre {s} ──────────────────────────────────────────────")

        n_prog = enrich_programacion(s)
        print(f"  programacion_talleres_S{s}.csv → {n_prog} talleres enriquecidos")

        n_ins = enrich_insumos(s)
        print(f"  insumos_S{s}.csv               → {n_ins} salas actualizadas con código\n")

    print("✅ Cruce completado. Archivos actualizados en output/")


if __name__ == "__main__":
    main()
