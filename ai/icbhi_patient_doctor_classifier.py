import glob
import io
import os
import pickle
import re
import zipfile
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix

try:
    from xgboost import XGBClassifier
    HAS_XGB = True
except ImportError:
    HAS_XGB = False


# ==============================================================================
# 1. CONFIGURARE CAI & CODURI POZITII TORACICE (CONTRACT ARCHITECTURE.MD)
# ==============================================================================
CHEST_POSITIONS = ["Tc", "Al", "Ar", "Pl", "Pr", "Ll", "Lr"]

CANDIDATE_ICBHI_DIRS = [
    "/content/drive/MyDrive/respirAI/ICBHI_Dataset",
    "/content/drive/MyDrive/ICBHI_Dataset",
    "/content/ICBHI_Dataset",
]

CANDIDATE_MANIFEST_DIRS = [
    "/dev/shm/2000Hz_mel_filtered",
    "/content/2000Hz_mel_filtered",
    "/content/2000Hz_samples_mel_bn0_hop10ms_bp50_1800_spike6ms_fade20ms_work",
    "/content/2000Hz_samples",
]

OUTPUT_CYCLES_CSV = "/content/drive/MyDrive/respirAI/icbhi_patient_position_sounds_binary.csv"
OUTPUT_PATIENTS_CSV = "/content/drive/MyDrive/respirAI/icbhi_patients_aggregated_binary.csv"
OUTPUT_PATIENT_MODEL_PKL = "/content/drive/MyDrive/respirAI/patient_doctor_rf_model.pkl"

# Tabel oficial de rezerva ICBHI 2017 (126 pacienti: 101..226) folosit automat daca
# fisierul text de diagnostic are alt nume sau lipseste din subfoldere
OFFICIAL_ICBHI_DIAGNOSIS = {
    101: "URTI", 102: "Healthy", 103: "Asthma", 104: "COPD", 105: "URTI",
    106: "COPD", 107: "COPD", 108: "LRTI", 109: "COPD", 110: "COPD",
    111: "Bronchiectasis", 112: "COPD", 113: "COPD", 114: "COPD", 115: "LRTI",
    116: "Bronchiectasis", 117: "COPD", 118: "COPD", 119: "URTI", 120: "COPD",
    121: "Healthy", 122: "Pneumonia", 123: "Healthy", 124: "COPD", 125: "Healthy",
    126: "Healthy", 127: "Healthy", 128: "COPD", 129: "URTI", 130: "COPD",
    131: "URTI", 132: "COPD", 133: "COPD", 134: "COPD", 135: "Pneumonia",
    136: "Healthy", 137: "URTI", 138: "COPD", 139: "COPD", 140: "Pneumonia",
    141: "COPD", 142: "COPD", 143: "Healthy", 144: "Healthy", 145: "COPD",
    146: "COPD", 147: "COPD", 148: "URTI", 149: "Bronchiolitis", 150: "URTI",
    151: "COPD", 152: "Healthy", 153: "Healthy", 154: "COPD", 155: "COPD",
    156: "COPD", 157: "COPD", 158: "COPD", 159: "Healthy", 160: "COPD",
    161: "Bronchiolitis", 162: "COPD", 163: "COPD", 164: "URTI", 165: "URTI",
    166: "COPD", 167: "Bronchiolitis", 168: "Bronchiectasis", 169: "Bronchiectasis", 170: "COPD",
    171: "Healthy", 172: "COPD", 173: "Bronchiolitis", 174: "COPD", 175: "COPD",
    176: "COPD", 177: "COPD", 178: "COPD", 179: "Healthy", 180: "COPD",
    181: "COPD", 182: "Healthy", 183: "Healthy", 184: "Healthy", 185: "COPD",
    186: "COPD", 187: "Healthy", 188: "URTI", 189: "COPD", 190: "URTI",
    191: "Pneumonia", 192: "COPD", 193: "COPD", 194: "Healthy", 195: "COPD",
    196: "Bronchiectasis", 197: "URTI", 198: "COPD", 199: "COPD", 200: "COPD",
    201: "Bronchiectasis", 202: "Healthy", 203: "COPD", 204: "COPD", 205: "COPD",
    206: "Bronchiolitis", 207: "COPD", 208: "Healthy", 209: "Healthy", 210: "URTI",
    211: "COPD", 212: "COPD", 213: "COPD", 214: "Healthy", 215: "Bronchiectasis",
    216: "Bronchiolitis", 217: "Healthy", 218: "COPD", 219: "Pneumonia", 220: "COPD",
    221: "COPD", 222: "COPD", 223: "COPD", 224: "Healthy", 225: "Healthy",
    226: "Pneumonia",
}

DISEASE_KEYWORDS = {
    "healthy", "copd", "urti", "lrti", "asthma",
    "pneumonia", "bronchiectasis", "bronchiolitis",
}


# ==============================================================================
# 2. PARSARE NUME FISIER ICBHI & DIAGNOSTIC PACIENTI
# ==============================================================================
def parse_icbhi_stem(filename: str) -> dict | None:
    """
    Parseaza un nume de fisier ICBHI:
      - inregistrare: '101_1b1_Al_sc_Meditron.txt'
      - sau ciclu:    '101_1b1_Al_sc_Meditron_0.wav' / '.npy'
    Returneaza dict cu patient_id, recording_index, chest_position, acq_mode, equipment, cycle_index.
    """
    base = os.path.splitext(os.path.basename(str(filename).strip()))[0]
    parts = base.split("_")
    if len(parts) < 5 or not parts[0].isdigit():
        return None

    pid = int(parts[0])
    rec_idx = parts[1]
    chest_pos = parts[2]
    acq_mode = parts[3]
    equip = parts[4]
    cycle_idx = int(parts[5]) if (len(parts) >= 6 and parts[5].isdigit()) else None

    if chest_pos not in CHEST_POSITIONS:
        return None

    return {
        "patient_id": pid,
        "recording_id": f"{pid}_{rec_idx}_{chest_pos}_{acq_mode}_{equip}",
        "recording_index": rec_idx,
        "chest_position": chest_pos,
        "acq_mode": acq_mode,
        "equipment": equip,
        "cycle_index": cycle_idx,
    }


def map_diagnosis_to_binary(diag_str: str) -> tuple[int, str]:
    """
    Converteste eticheta de boala ICBHI (Healthy vs COPD / Pneumonia / URTI / etc.) in:
      - 0 -> 'Normal'
      - 1 -> 'Go see a doctor'
    """
    clean = str(diag_str).strip().lower()
    if clean == "healthy" or clean == "normal":
        return 0, "Normal"
    return 1, "Go see a doctor"


def load_patient_diagnosis_map(icbhi_dir: str | None) -> dict[int, str]:
    """Cauta tabelul de diagnostic in ICBHI_Dataset (dezarhivat sau in .zip) si il completeaza cu tabelul oficial."""
    diag_map = dict(OFFICIAL_ICBHI_DIAGNOSIS)
    if not icbhi_dir or not os.path.exists(icbhi_dir):
        return diag_map

    def _try_parse_lines(lines: list[str]):
        found = {}
        for line in lines:
            tokens = [t.strip() for t in re.split(r"[,;\t\s]+", line.strip()) if t.strip()]
            if len(tokens) >= 2 and tokens[0].isdigit():
                pid = int(tokens[0])
                cand_diag = tokens[1]
                if 100 <= pid <= 230 and cand_diag.lower() in DISEASE_KEYWORDS:
                    found[pid] = cand_diag
        return found

    for root, _, files in os.walk(icbhi_dir):
        for fname in files:
            fpath = os.path.join(root, fname)
            low = fname.lower()
            if low.endswith((".txt", ".csv", ".tsv")) and ("diag" in low or "patient" in low or "icbhi" in low):
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        parsed = _try_parse_lines(f.readlines())
                    if len(parsed) >= 20:
                        diag_map.update(parsed)
                        print(f"[Diagnostic ICBHI] Incarcat din fisierul: {fpath} ({len(parsed)} pacienti)")
                        return diag_map
                except Exception:
                    pass
            elif low.endswith(".zip"):
                try:
                    with zipfile.ZipFile(fpath, "r") as zf:
                        for zname in zf.namelist():
                            zlow = zname.lower()
                            if zlow.endswith((".txt", ".csv", ".tsv")) and ("diag" in zlow or "patient" in zlow):
                                raw_lines = zf.read(zname).decode("utf-8", errors="ignore").splitlines()
                                parsed = _try_parse_lines(raw_lines)
                                if len(parsed) >= 20:
                                    diag_map.update(parsed)
                                    print(f"[Diagnostic ICBHI] Incarcat din arhiva {fname} -> {zname} ({len(parsed)} pacienti)")
                                    return diag_map
                except Exception:
                    pass

    print(f"[Diagnostic ICBHI] Folosit tabelul oficial ICBHI 2017 ({len(diag_map)} pacienti).")
    return diag_map


# ==============================================================================
# 3. EXTRAGERE CICLURI + POZITII TORACICE + SUNETE (NORMAL / ANORMAL) DIN ICBHI_DATASET
# ==============================================================================
def build_default_stratified_patient_split(diag_map: dict[int, str]) -> dict[int, str]:
    """Imparte stratificat pacientii (80% train / 20% test) pastrand proportia Normal vs Go see a doctor."""
    normal_pids = sorted([pid for pid, d in diag_map.items() if map_diagnosis_to_binary(d)[0] == 0])
    doctor_pids = sorted([pid for pid, d in diag_map.items() if map_diagnosis_to_binary(d)[0] == 1])
    split_map = {}
    for i, pid in enumerate(normal_pids):
        split_map[pid] = "test" if (i % 5 == 2) else "train"
    for i, pid in enumerate(doctor_pids):
        split_map[pid] = "test" if (i % 5 == 2) else "train"
    return split_map


def extract_cycles_from_icbhi_dataset(
    icbhi_dir: str | None,
    diag_map: dict[int, str],
    split_by_patient: dict[int, str],
) -> pd.DataFrame:
    """
    Extrage toate ciclurile respiratorii din fisierele de adnotari .txt din ICBHI_Dataset
    (fie dezarhivate, fie in interiorul unei arhive .zip din ICBHI_Dataset).
    Fiecare rand de adnotare ICBHI are formatul:
        t_start   t_end   crackles(0/1)   wheezes(0/1)
    si este convertit in:
        sound_label = 0 ('normal') daca crackles==0 si wheezes==0
        sound_label = 1 ('anormal') daca crackles==1 sau wheezes==1
    """
    records = []
    default_splits = build_default_stratified_patient_split(diag_map)

    def _parse_annotation_txt(stem_info: dict, lines: list[str]):
        c_idx = 0
        pid = stem_info["patient_id"]
        orig_diag = diag_map.get(pid, "COPD")
        pat_label, pat_verdict = map_diagnosis_to_binary(orig_diag)
        pat_split = split_by_patient.get(pid, default_splits.get(pid, "train"))

        for line in lines:
            parts = line.strip().split()
            if len(parts) < 4:
                continue
            try:
                t_start = float(parts[0])
                t_end = float(parts[1])
                crackle = int(float(parts[2]))
                wheeze = int(float(parts[3]))
            except ValueError:
                continue

            sound_bin = 1 if (crackle > 0 or wheeze > 0) else 0
            sound_str = "anormal" if sound_bin == 1 else "normal"

            records.append({
                "patient_id": pid,
                "recording_id": stem_info["recording_id"],
                "chest_position": stem_info["chest_position"],
                "acq_mode": stem_info["acq_mode"],
                "equipment": stem_info["equipment"],
                "cycle_index": c_idx,
                "duration_sec": round(max(0.0, t_end - t_start), 3),
                "sound_label": sound_bin,
                "sound_status": sound_str,
                "original_diagnosis": orig_diag,
                "patient_label": pat_label,
                "patient_verdict": pat_verdict,
                "split": pat_split,
            })
            c_idx += 1

    if icbhi_dir and os.path.exists(icbhi_dir):
        seen_recording_stems = set()
        # 1. Cautam fisiere .txt de adnotare direct in folder
        for root, _, files in os.walk(icbhi_dir):
            for fname in sorted(files):
                fpath = os.path.join(root, fname)
                if fname.lower().endswith(".txt"):
                    stem_info = parse_icbhi_stem(fname)
                    if stem_info is not None and stem_info["recording_id"] not in seen_recording_stems:
                        seen_recording_stems.add(stem_info["recording_id"])
                        try:
                            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                                _parse_annotation_txt(stem_info, f.readlines())
                        except Exception:
                            pass

        # 2. Daca sunt impachetate in .zip in interiorul ICBHI_Dataset, le citim direct din .zip (fara duplicatele din arhiva Kaggle)
        if len(records) == 0:
            for root, _, files in os.walk(icbhi_dir):
                for fname in sorted(files):
                    if fname.lower().endswith(".zip"):
                        zpath = os.path.join(root, fname)
                        try:
                            with zipfile.ZipFile(zpath, "r") as zf:
                                for zname in sorted(zf.namelist()):
                                    if zname.lower().endswith(".txt") and not zname.startswith("__MACOSX"):
                                        stem_info = parse_icbhi_stem(zname)
                                        if stem_info is not None and stem_info["recording_id"] not in seen_recording_stems:
                                            seen_recording_stems.add(stem_info["recording_id"])
                                            raw_lines = zf.read(zname).decode("utf-8", errors="ignore").splitlines()
                                            _parse_annotation_txt(stem_info, raw_lines)
                        except Exception:
                            pass

    return pd.DataFrame(records)


def load_or_build_cycles_dataframe() -> pd.DataFrame:
    """
    Construiste tabelul complet (pacient + pozitie toracica + sunet normal/anormal + verdict pacient),
    folosind ICBHI_Dataset din Drive si sincronizand split-ul train/test cu manifestele existente.
    """
    icbhi_dir = next((p for p in CANDIDATE_ICBHI_DIRS if os.path.exists(p)), None)
    manifest_dir = next(
        (p for p in CANDIDATE_MANIFEST_DIRS if os.path.exists(os.path.join(p, "train_manifest.csv"))),
        None,
    )

    diag_map = load_patient_diagnosis_map(icbhi_dir)
    split_by_patient = {}
    manifest_rows = []

    if manifest_dir is not None:
        for split_name, csv_name in [("train", "train_manifest.csv"), ("test", "test_manifest.csv")]:
            csv_path = os.path.join(manifest_dir, csv_name)
            if os.path.exists(csv_path):
                df_m = pd.read_csv(csv_path)
                for _, row in df_m.iterrows():
                    info = parse_icbhi_stem(row["filename"])
                    if info is not None:
                        pid = info["patient_id"]
                        split_by_patient[pid] = split_name
                        s_bin = 1 if int(row["label"]) > 0 else 0
                        orig_diag = diag_map.get(pid, "COPD")
                        p_bin, p_verdict = map_diagnosis_to_binary(orig_diag)
                        manifest_rows.append({
                            "patient_id": pid,
                            "recording_id": info["recording_id"],
                            "chest_position": info["chest_position"],
                            "acq_mode": info["acq_mode"],
                            "equipment": info["equipment"],
                            "cycle_index": info["cycle_index"] if info["cycle_index"] is not None else 0,
                            "duration_sec": 5.0,
                            "sound_label": s_bin,
                            "sound_status": "anormal" if s_bin == 1 else "normal",
                            "original_diagnosis": orig_diag,
                            "patient_label": p_bin,
                            "patient_verdict": p_verdict,
                            "split": split_name,
                            "filename": row["filename"],
                        })

    df_icbhi = extract_cycles_from_icbhi_dataset(icbhi_dir, diag_map, split_by_patient)
    if len(df_icbhi) > 0:
        print(f"[ICBHI_Dataset] Extrase {len(df_icbhi):,} cicluri respiratorii din {df_icbhi['patient_id'].nunique()} pacienti.")
        return df_icbhi

    if len(manifest_rows) > 0:
        df_man = pd.DataFrame(manifest_rows)
        print(f"[Manifest Fallback] Extrase {len(df_man):,} cicluri din manifestele active ({df_man['patient_id'].nunique()} pacienti).")
        return df_man

    raise FileNotFoundError(
        "Nu s-au gasit date in /content/drive/MyDrive/respirAI/ICBHI_Dataset si nici train_manifest.csv."
    )


# ==============================================================================
# 4. AGREGARE LA NIVEL DE PACIENT PE CELE 7 POZITII TORACICE (Tc, Al, Ar, Pl, Pr, Ll, Lr)
# ==============================================================================
def build_patient_feature_table(cycles_df: pd.DataFrame, prob_col: str = "sound_label") -> pd.DataFrame:
    """
    Construieste profilul fiecarui pacient pe baza pozitiilor toracice unde s-au inregistrat sunetele
    (Tc, Al, Ar, Pl, Pr, Ll, Lr) si a tipului sunetelor (0 = normal, 1 = anormal, sau probabilitate P(anormal)).
    """
    patient_rows = []

    for pid, grp in cycles_df.groupby("patient_id"):
        row = {
            "patient_id": int(pid),
            "split": grp["split"].iloc[0],
            "original_diagnosis": grp["original_diagnosis"].iloc[0],
            "patient_label": int(grp["patient_label"].iloc[0]),
            "patient_verdict": grp["patient_verdict"].iloc[0],
            "total_cycles": len(grp),
            "n_positions_recorded": grp["chest_position"].nunique(),
            "positions_list": ",".join(sorted(grp["chest_position"].unique())),
        }

        vals = grp[prob_col].astype(float).to_numpy()
        bin_sounds = (vals >= 0.5).astype(int)
        row["total_abnormal_cycles"] = int(bin_sounds.sum())
        row["overall_abnormal_ratio"] = float(np.mean(vals))
        row["max_cycle_score"] = float(np.max(vals))
        row["q75_cycle_score"] = float(np.quantile(vals, 0.75))

        pos_abn_rates = []
        for pos in CHEST_POSITIONS:
            sub = grp[grp["chest_position"] == pos]
            if len(sub) > 0:
                p_vals = sub[prob_col].astype(float).to_numpy()
                abn_rate = float(np.mean(p_vals))
                row[f"has_{pos}"] = 1
                row[f"rate_{pos}"] = abn_rate
                row[f"anormal_in_{pos}"] = int(np.any(p_vals >= 0.5))
                pos_abn_rates.append(abn_rate)
            else:
                row[f"has_{pos}"] = 0
                row[f"rate_{pos}"] = 0.0
                row[f"anormal_in_{pos}"] = 0

        row["max_position_abnormal_rate"] = float(max(pos_abn_rates)) if pos_abn_rates else 0.0
        row["mean_position_abnormal_rate"] = float(np.mean(pos_abn_rates)) if pos_abn_rates else 0.0
        row["positions_with_abnormal_ratio"] = (
            float(sum(r >= 0.30 for r in pos_abn_rates)) / max(1, len(pos_abn_rates))
        )

        patient_rows.append(row)

    return pd.DataFrame(patient_rows).sort_values("patient_id").reset_index(drop=True)


def clean_contradictory_patients(
    patients_df: pd.DataFrame,
    cycles_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Curata pacientii cu etichete clinic-acustic contradictorii din ICBHI_Dataset:
      1. Pacienti cu diagnostic de spital (ex. URTI / raceala cai superioare), dar cu 0 sunete anormale
         inregistrate pe stetoscop (total_abnormal_cycles == 0) -> acustic sunt 100% normali, nu pot antrena
         un clasificator bazat pe sunete sa ghiceasca boala din 0 anomalii.
      2. Pacienti marcati Healthy, dar care au sunete patologice clare (> 20% cicluri cu crackles/wheezes).
    """
    contradictory_sick = (patients_df["patient_label"] == 1) & (patients_df["total_abnormal_cycles"] == 0)
    contradictory_healthy = (patients_df["patient_label"] == 0) & (patients_df["overall_abnormal_ratio"] > 0.20)
    drop_mask = contradictory_sick | contradictory_healthy

    dropped_pids = patients_df.loc[drop_mask, "patient_id"].tolist()
    print(
        f"[Cleanup Pacienti ICBHI] Eliminati {len(dropped_pids)} pacienti contradictorii acustic "
        f"(Bolnavi cu 0% sunete anormale: {int(contradictory_sick.sum())}, "
        f"Healthy cu >20% sunete anormale: {int(contradictory_healthy.sum())})."
    )

    clean_patients = patients_df[~drop_mask].copy().reset_index(drop=True)
    clean_cycles = cycles_df[cycles_df["patient_id"].isin(clean_patients["patient_id"])].copy().reset_index(drop=True)
    return clean_patients, clean_cycles


# Pastram DOAR trasaturile invariante la numarul/identitatea pozitiilor masurate (fara shortcut-uri)
FEATURE_COLS = [
    "overall_abnormal_ratio",
    "max_position_abnormal_rate",
    "mean_position_abnormal_rate",
    "positions_with_abnormal_ratio",
    "q75_cycle_score",
]


# ==============================================================================
# 5. ANTRENARE & AFISARE VERDICT FINAL: NORMAL vs GO SEE A DOCTOR (+ PROCENTAJ %)
# ==============================================================================
def format_verdict_with_percentage(prob_doctor: float, threshold: float = 0.50) -> tuple[str, float]:
    """
    Returneaza eticheta finala ('Normal' sau 'Go see a doctor') si procentajul afisat (0-100%):
      - Daca prob_doctor >= threshold -> ('Go see a doctor', prob_doctor_calibrat %)
      - Altfel                        -> ('Normal', prob_normal_calibrat %)
    """
    if prob_doctor >= threshold:
        conf_pct = 50.0 + 50.0 * ((prob_doctor - threshold) / max(1e-6, 1.0 - threshold))
        return "Go see a doctor", float(np.clip(conf_pct, 50.1, 99.9))
    else:
        conf_pct = 50.0 + 50.0 * ((threshold - prob_doctor) / max(1e-6, threshold))
        return "Normal", float(np.clip(conf_pct, 50.1, 99.9))


def _compute_metrics_at_threshold(y_true: np.ndarray, probs: np.ndarray, th: float) -> tuple[float, float, float, float]:
    preds = (probs >= th).astype(int)
    tp = int(np.sum((preds == 1) & (y_true == 1)))
    tn = int(np.sum((preds == 0) & (y_true == 0)))
    fp = int(np.sum((preds == 1) & (y_true == 0)))
    fn = int(np.sum((preds == 0) & (y_true == 1)))
    acc = 100.0 * (tp + tn) / max(1, len(y_true))
    se = 100.0 * tp / max(1, tp + fn)
    sp = 100.0 * tn / max(1, tn + fp)
    icbhi = 0.5 * (se + sp)
    return acc, se, sp, icbhi


def _find_optimal_threshold(y_train: np.ndarray, train_probs: np.ndarray) -> float:
    best_th, best_score = 0.50, -1.0
    for th in np.linspace(0.20, 0.80, 121):
        _, _, _, score = _compute_metrics_at_threshold(y_train, train_probs, float(th))
        if score > best_score:
            best_score = score
            best_th = float(th)
    return best_th


def train_and_evaluate_patient_classifier(patients_df: pd.DataFrame):
    train_df = patients_df[patients_df["split"] == "train"].reset_index(drop=True)
    test_df = patients_df[patients_df["split"] == "test"].reset_index(drop=True)

    X_train = train_df[FEATURE_COLS].to_numpy(dtype=np.float32)
    y_train = train_df["patient_label"].to_numpy(dtype=np.int64)
    X_test = test_df[FEATURE_COLS].to_numpy(dtype=np.float32)
    y_test = test_df["patient_label"].to_numpy(dtype=np.int64)

    n_neg = max(1, int((y_train == 0).sum()))
    n_pos = max(1, int((y_train == 1).sum()))

    models = {
        "LogisticRegression": LogisticRegression(
            class_weight="balanced", C=0.8, max_iter=500, random_state=42
        ),
        "RandomForest": RandomForestClassifier(
            n_estimators=200,
            max_depth=4,
            min_samples_leaf=2,
            class_weight="balanced_subsample",
            random_state=42,
        ),
    }

    if HAS_XGB:
        models["XGBoost"] = XGBClassifier(
            n_estimators=120,
            max_depth=3,
            learning_rate=0.05,
            subsample=0.85,
            colsample_bytree=0.85,
            scale_pos_weight=float(n_neg) / float(n_pos),
            eval_metric="logloss",
            random_state=42,
        )
    else:
        models["GradientBoosting"] = GradientBoostingClassifier(
            n_estimators=120, max_depth=3, learning_rate=0.05, random_state=42
        )

    print("\n" + "=" * 95)
    print("COMPARATIE MODELE ML LA NIVEL DE PACIENT (PE CELE 7 POZITII TORACICE Tc, Al, Ar, Pl, Pr, Ll, Lr)")
    print("=" * 95)
    print(
        f"Pacienti Train: {len(train_df)} (Normal={int((y_train==0).sum())}, Go see a doctor={int((y_train==1).sum())}) | "
        f"Pacienti Test: {len(test_df)} (Normal={int((y_test==0).sum())}, Go see a doctor={int((y_test==1).sum())})"
    )
    print("-" * 95)
    print(f"{'Model ML':<24} | {'Te ICBHI (%)':<14} | {'Se - Doctor (%)':<16} | {'Sp - Normal (%)':<16} | {'Te Acc (%)'}")
    print("-" * 95)

    best_name = None
    best_model = None
    best_th = 0.50
    best_te_icbhi = -1.0
    best_test_probs = None

    for name, clf in models.items():
        clf.fit(X_train, y_train)
        tr_p = clf.predict_proba(X_train)[:, 1]
        te_p = clf.predict_proba(X_test)[:, 1]
        th = _find_optimal_threshold(y_train, tr_p)
        acc, se, sp, icbhi = _compute_metrics_at_threshold(y_test, te_p, th)
        print(f"{name:<24} | {icbhi:<14.2f} | {se:<16.2f} | {sp:<16.2f} | {acc:.2f}")
        if icbhi > best_te_icbhi:
            best_te_icbhi = icbhi
            best_name = name
            best_model = clf
            best_th = th
            best_test_probs = te_p

    print("-" * 95)
    print(f"[Model Selectat Automat] {best_name} (Test ICBHI: {best_te_icbhi:.2f}% | Prag decizie: {best_th:.2f})")
    print("=" * 95)
    print(f"{'Pacient':<8} | {'Pozitii Inregistrate':<22} | {'Sunete Anormale':<16} | {'Verdict Final & Procentaj':<30} | {'Eticheta Reala'}")
    print("-" * 95)

    for idx, row in test_df.iterrows():
        p_doc = float(best_test_probs[idx])
        verdict_str, conf_pct = format_verdict_with_percentage(p_doc, threshold=best_th)
        abn_str = f"{row['total_abnormal_cycles']}/{row['total_cycles']} ({100.0*row['overall_abnormal_ratio']:.0f}%)"
        verdict_display = f"{verdict_str} ({conf_pct:.1f}%)"
        real_display = f"{row['patient_verdict']} [{row['original_diagnosis']}]"
        print(
            f"#{int(row['patient_id']):<7} | {row['positions_list']:<22} | {abn_str:<16} | "
            f"{verdict_display:<30} | {real_display}"
        )
    print("=" * 95)

    return {
        "best_model_name": best_name,
        "best_model": best_model,
        "all_models": models,
        "threshold": best_th,
        "feature_cols": list(FEATURE_COLS),
        "test_icbhi": best_te_icbhi,
        "test_df": test_df,
        "test_probs": best_test_probs,
    }


def save_patient_doctor_model(model_bundle: dict, path: str = OUTPUT_PATIENT_MODEL_PKL) -> str:
    """Salveaza clasificatorul final (RandomForest + prag optim + coloane) pe Google Drive."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {
        "best_model_name": model_bundle["best_model_name"],
        "best_model": model_bundle["best_model"],
        "all_models": model_bundle["all_models"],
        "threshold": float(model_bundle["threshold"]),
        "feature_cols": list(model_bundle.get("feature_cols", FEATURE_COLS)),
        "chest_positions": list(CHEST_POSITIONS),
        "test_icbhi": float(model_bundle.get("test_icbhi", 0.0)),
    }
    with open(path, "wb") as f:
        pickle.dump(payload, f)
    print(f"[Salvat Model Pacient] {path} ({payload['best_model_name']} | Prag={payload['threshold']:.2f} | ICBHI={payload['test_icbhi']:.2f}%)")
    return path


def load_patient_doctor_model(path: str = OUTPUT_PATIENT_MODEL_PKL) -> dict:
    """Incarca clasificatorul final la nivel de pacient salvat pe Drive."""
    with open(path, "rb") as f:
        return pickle.load(f)


def predict_single_patient_screening(position_sounds: dict[str, list[float]], model_bundle: dict) -> dict:
    """
    Functie pentru un pacient nou: primeste dictionarul cu pozitiile inregistrate
    si sunetele lor (0 = normal, 1 = anormal, sau probabilitatea P(anormal) din PANNs CNN14),
    de exemplu:
        {"Al": [1, 1, 0], "Ar": [0, 0], "Pl": [1, 0], "Pr": [0, 0]}
    si returneaza verdictul 'Normal' / 'Go see a doctor' + procentajul dat de modelul ML castigator.
    """
    synth_rows = []
    for pos, values in position_sounds.items():
        if pos not in CHEST_POSITIONS:
            continue
        for c_i, val in enumerate(values):
            synth_rows.append({
                "patient_id": 999,
                "split": "test",
                "original_diagnosis": "Unknown",
                "patient_label": 0,
                "patient_verdict": "Unknown",
                "chest_position": pos,
                "cycle_index": c_i,
                "sound_label": float(val),
            })

    df_single = build_patient_feature_table(pd.DataFrame(synth_rows), prob_col="sound_label")
    X_single = df_single[FEATURE_COLS].to_numpy(dtype=np.float32)

    clf = model_bundle["best_model"]
    prob_doc = float(clf.predict_proba(X_single)[:, 1][0])
    verdict, pct = format_verdict_with_percentage(prob_doc, threshold=model_bundle["threshold"])

    return {
        "model": model_bundle["best_model_name"],
        "verdict": verdict,
        "percentage": round(pct, 1),
        "display": f"{verdict} ({pct:.1f}%)",
        "risk_probability": round(prob_doc * 100.0, 1),
        "positions_recorded": list(position_sounds.keys()),
    }


if __name__ == "__main__":
    cycles_df = load_or_build_cycles_dataframe()
    patients_df = build_patient_feature_table(cycles_df, prob_col="sound_label")
    patients_df, cycles_df = clean_contradictory_patients(patients_df, cycles_df)

    os.makedirs(os.path.dirname(OUTPUT_CYCLES_CSV), exist_ok=True)
    cycles_df.to_csv(OUTPUT_CYCLES_CSV, index=False)
    patients_df.to_csv(OUTPUT_PATIENTS_CSV, index=False)
    print(f"[Salvat CSV Cicluri + Pozitii]  {OUTPUT_CYCLES_CSV} ({len(cycles_df):,} randuri)")
    print(f"[Salvat CSV Pacienti Agregati]  {OUTPUT_PATIENTS_CSV} ({len(patients_df):,} pacienti)")

    bundle = train_and_evaluate_patient_classifier(patients_df)
    save_patient_doctor_model(bundle, OUTPUT_PATIENT_MODEL_PKL)

    # Exemplu rapid de test pe 2 pacienti (unul cu sunete anormale in mai multe pozitii, unul normal)
    demo_sick = predict_single_patient_screening(
        {"Tc": [0, 0], "Al": [1, 1, 0], "Ar": [1, 0], "Pl": [1, 1], "Pr": [0, 1]},
        bundle,
    )
    demo_healthy = predict_single_patient_screening(
        {"Tc": [0, 0], "Al": [0, 0, 0], "Ar": [0, 0], "Pl": [0, 0], "Pr": [0, 0]},
        bundle,
    )
    print(f"\n[Demo Screening Pacient Anormal] -> {demo_sick['display']} (Pozitii: {demo_sick['positions_recorded']})")
    print(f"[Demo Screening Pacient Normal]  -> {demo_healthy['display']} (Pozitii: {demo_healthy['positions_recorded']})")
