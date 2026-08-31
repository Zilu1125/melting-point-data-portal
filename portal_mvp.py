import re
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image

# =========================================================
# Card Reader
# =========================================================

try:
    from card_reader import (
        connect_reader,
        disconnect_reader,
        get_reader_name,
        read_card,
    )
    CARD_READER_AVAILABLE = True
except Exception:
    CARD_READER_AVAILABLE = False


# =========================================================
# Configuration
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "portal_mvp.db"
RUNS_DIR = BASE_DIR / "runs"

# Confirmed OPM structure for this project
OPM_GLOBAL_HEADER_SIZE = 336
OPM_FRAME_SIZE = 28248
OPM_FRAME_HEADER_SIZE = 24
OPM_FRAME_WIDTH = 196
OPM_FRAME_HEIGHT = 144

# Person 2 fixed CSV formats
CALIBRATED_REQUIRED_COLUMNS = {
    "Channel",
    "Point",
    "Measured(C)",
    "Corrected(C)",
    "ExpandedUnc_U_k2(C)",
    "Extrapolated",
}

RAW_REQUIRED_COLUMNS = {
    "Time(s)",
    "Temp(C)",
    "Left",
    "Center",
    "Right",
}


# =========================================================
# Database
# =========================================================

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        card_id TEXT UNIQUE NOT NULL,
        student_name TEXT NOT NULL,
        email TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS experiment_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT UNIQUE NOT NULL,
        student_id INTEGER NOT NULL,
        opm_filename TEXT,
        opm_path TEXT,
        created_at TEXT,
        frame_count INTEGER DEFAULT 0,
        processing_status TEXT DEFAULT 'created',
        calibrated_file TEXT,
        raw_data_file TEXT,
        FOREIGN KEY(student_id) REFERENCES students(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        tube_position TEXT NOT NULL,
        sample_name TEXT NOT NULL,

        runtime_timestamp TEXT,
        ramp_rate REAL,
        heating_range_low REAL,
        heating_range_high REAL,

        machine_id TEXT,
        instrument_name TEXT,
        last_calibration_datetime TEXT,

        onset_point REAL,
        single_point REAL,
        clear_point REAL,

        measured_onset REAL,
        measured_single REAL,
        measured_clear REAL,

        onset_uncertainty REAL,
        single_uncertainty REAL,
        clear_uncertainty REAL,

        onset_extrapolated TEXT,
        single_extrapolated TEXT,
        clear_extrapolated TEXT,

        run_status TEXT DEFAULT 'completed',
        cooling_status TEXT DEFAULT 'cooled',
        report_status TEXT DEFAULT 'not generated',

        frame_folder TEXT,
        curve_file TEXT,
        imported_at TEXT
    )
    """)

    conn.commit()
    conn.close()


# =========================================================
# Card ID
# =========================================================

def normalize_card_id(card_id):
    if card_id is None:
        return None

    return re.sub(
        r"[^0-9A-Fa-f]",
        "",
        str(card_id)
    ).upper()


# =========================================================
# Card Reader
# =========================================================

def scan_card_once():
    if not CARD_READER_AVAILABLE:
        raise RuntimeError(
            "card_reader.py could not be loaded. "
            "Make sure card_reader.py is in the same folder as portal_mvp.py."
        )

    connected = False

    try:
        connected = connect_reader()

        if not connected:
            raise RuntimeError(
                "Could not connect to the rf IDEAS reader. "
                "Close rf IDEAS Configuration Utility and try again."
            )

        reader_name = get_reader_name()
        card = read_card()

        if card is None:
            raise RuntimeError(
                "No card detected. Place the card on the reader "
                "and click Scan Card again."
            )

        card["card_id"] = normalize_card_id(card["card_id"])
        card["reader_name"] = reader_name

        return card

    finally:
        if connected:
            disconnect_reader()


# =========================================================
# Students
# =========================================================

def create_student(card_id, student_name, email):
    card_id = normalize_card_id(card_id)
    student_name = student_name.strip()
    email = email.strip()

    if not card_id:
        raise ValueError("Card ID cannot be empty.")

    if not student_name:
        raise ValueError("Student name cannot be empty.")

    if not email:
        raise ValueError("Email cannot be empty.")

    conn = get_conn()

    try:
        conn.execute("""
        INSERT INTO students (
            card_id,
            student_name,
            email,
            created_at
        )
        VALUES (?, ?, ?, ?)
        """, (
            card_id,
            student_name,
            email,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ))

        conn.commit()

    except sqlite3.IntegrityError:
        raise ValueError(
            "This card has already been registered."
        )

    finally:
        conn.close()


def update_student_info(student_id, student_name, email):
    student_name = student_name.strip()
    email = email.strip()

    if not student_name:
        raise ValueError("Student name cannot be empty.")

    if not email:
        raise ValueError("Email cannot be empty.")

    conn = get_conn()

    conn.execute("""
        UPDATE students
        SET student_name = ?, email = ?
        WHERE id = ?
    """, (
        student_name,
        email,
        int(student_id),
    ))

    conn.commit()
    conn.close()


def fetch_students():
    conn = get_conn()

    df = pd.read_sql_query("""
        SELECT *
        FROM students
        ORDER BY student_name
    """, conn)

    conn.close()
    return df


def get_student_by_card(card_id):
    card_id = normalize_card_id(card_id)

    conn = get_conn()

    row = conn.execute("""
        SELECT *
        FROM students
        WHERE card_id = ?
    """, (
        card_id,
    )).fetchone()

    conn.close()

    if row:
        return dict(row)

    return None


def get_student_by_id(student_id):
    conn = get_conn()

    row = conn.execute("""
        SELECT *
        FROM students
        WHERE id = ?
    """, (
        int(student_id),
    )).fetchone()

    conn.close()

    if row:
        return dict(row)

    return None


# =========================================================
# Experiment Runs
# =========================================================

def fetch_runs():
    conn = get_conn()

    df = pd.read_sql_query("""
        SELECT
            r.*,
            s.student_name,
            s.email,
            s.card_id
        FROM experiment_runs r
        LEFT JOIN students s
            ON r.student_id = s.id
        ORDER BY r.id DESC
    """, conn)

    conn.close()
    return df


def create_run_record(
    run_id,
    student_id,
    opm_filename,
    opm_path
):
    conn = get_conn()

    conn.execute("""
    INSERT INTO experiment_runs (
        run_id,
        student_id,
        opm_filename,
        opm_path,
        created_at,
        processing_status
    )
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        run_id,
        int(student_id),
        opm_filename,
        opm_path,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "created",
    ))

    conn.commit()
    conn.close()


def update_run_record(run_id, **updates):
    if not updates:
        return

    allowed = {
        "student_id",
        "frame_count",
        "processing_status",
        "calibrated_file",
        "raw_data_file",
    }

    safe_updates = {
        key: value
        for key, value in updates.items()
        if key in allowed
    }

    if not safe_updates:
        return

    fields = ", ".join(
        f"{key} = ?"
        for key in safe_updates
    )

    values = (
        list(safe_updates.values())
        +
        [run_id]
    )

    conn = get_conn()

    conn.execute(
        f"""
        UPDATE experiment_runs
        SET {fields}
        WHERE run_id = ?
        """,
        values
    )

    conn.commit()
    conn.close()


# =========================================================
# Run ID
# =========================================================

def generate_run_id(opm_filename):
    match = re.search(
        r"(\d{6})-(\d{6})",
        opm_filename
    )

    if match:
        try:
            dt = datetime.strptime(
                match.group(1) + match.group(2),
                "%y%m%d%H%M%S"
            )

            base = dt.strftime(
                "run_%Y%m%d_%H%M%S"
            )

        except ValueError:
            base = (
                "run_"
                +
                datetime.now().strftime(
                    "%Y%m%d_%H%M%S"
                )
            )

    else:
        base = (
            "run_"
            +
            datetime.now().strftime(
                "%Y%m%d_%H%M%S"
            )
        )

    run_id = base
    counter = 2

    while (
        RUNS_DIR
        /
        run_id
    ).exists():

        run_id = f"{base}_{counter}"
        counter += 1

    return run_id


# =========================================================
# OPM Processing
# =========================================================

def calculate_frame_count(opm_path):
    file_size = (
        Path(opm_path)
        .stat()
        .st_size
    )

    usable_bytes = (
        file_size
        -
        OPM_GLOBAL_HEADER_SIZE
    )

    if usable_bytes <= 0:
        return 0

    return (
        usable_bytes
        //
        OPM_FRAME_SIZE
    )


def extract_all_opm_frames(
    opm_path,
    output_folder
):
    opm_path = Path(opm_path)
    output_folder = Path(output_folder)

    output_folder.mkdir(
        parents=True,
        exist_ok=True
    )

    data = opm_path.read_bytes()

    frame_count = calculate_frame_count(
        opm_path
    )

    if frame_count <= 0:
        raise ValueError(
            "No frames were detected inside this OPM file."
        )

    expected_pixels = (
        OPM_FRAME_WIDTH
        *
        OPM_FRAME_HEIGHT
    )

    for index in range(frame_count):
        frame_start = (
            OPM_GLOBAL_HEADER_SIZE
            +
            index
            *
            OPM_FRAME_SIZE
        )

        frame_block = data[
            frame_start
            :
            frame_start + OPM_FRAME_SIZE
        ]

        pixel_start = OPM_FRAME_HEADER_SIZE

        pixels = frame_block[
            pixel_start
            :
            pixel_start + expected_pixels
        ]

        if len(pixels) != expected_pixels:
            raise ValueError(
                f"Frame {index} has unexpected pixel size."
            )

        image = Image.frombytes(
            "L",
            (
                OPM_FRAME_WIDTH,
                OPM_FRAME_HEIGHT
            ),
            pixels
        )

        image.save(
            output_folder
            /
            f"frame_{index:04d}.png"
        )

    return int(frame_count)


# =========================================================
# Split Left / Centre / Right
# =========================================================

def split_frames_by_position(
    frames_folder,
    left_folder,
    centre_folder,
    right_folder
):
    frames_folder = Path(frames_folder)

    target_folders = {
        "left": Path(left_folder),
        "centre": Path(centre_folder),
        "right": Path(right_folder),
    }

    for folder in target_folders.values():
        folder.mkdir(
            parents=True,
            exist_ok=True
        )

    frame_paths = sorted(
        frames_folder.glob(
            "frame_*.png"
        )
    )

    if not frame_paths:
        raise ValueError(
            "No extracted PNG frames found."
        )

    crops = {
        "left": (
            0,
            0,
            65,
            144
        ),

        "centre": (
            65,
            0,
            130,
            144
        ),

        "right": (
            130,
            0,
            196,
            144
        ),
    }

    for frame_path in frame_paths:
        with Image.open(frame_path) as image:

            for position, crop_box in crops.items():
                cropped = image.crop(
                    crop_box
                )

                cropped.save(
                    target_folders[
                        position
                    ]
                    /
                    frame_path.name
                )


# =========================================================
# Create Experiment
# =========================================================

def create_experiment_run(
    uploaded_opm,
    student_id
):
    RUNS_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    run_id = generate_run_id(
        uploaded_opm.name
    )

    run_folder = (
        RUNS_DIR
        /
        run_id
    )

    source_folder = (
        run_folder
        /
        "source"
    )

    frames_folder = (
        run_folder
        /
        "frames"
    )

    left_folder = (
        run_folder
        /
        "left_frames"
    )

    centre_folder = (
        run_folder
        /
        "centre_frames"
    )

    right_folder = (
        run_folder
        /
        "right_frames"
    )

    curves_folder = (
        run_folder
        /
        "curves"
    )

    for folder in [
        source_folder,
        frames_folder,
        left_folder,
        centre_folder,
        right_folder,
        curves_folder,
    ]:
        folder.mkdir(
            parents=True,
            exist_ok=True
        )

    opm_path = (
        source_folder
        /
        uploaded_opm.name
    )

    with open(
        opm_path,
        "wb"
    ) as f:
        f.write(
            uploaded_opm.getbuffer()
        )

    create_run_record(
        run_id,
        student_id,
        uploaded_opm.name,
        str(opm_path)
    )

    try:
        update_run_record(
            run_id,
            processing_status="extracting frames"
        )

        frame_count = (
            extract_all_opm_frames(
                opm_path,
                frames_folder
            )
        )

        update_run_record(
            run_id,
            processing_status="splitting frames"
        )

        split_frames_by_position(
            frames_folder,
            left_folder,
            centre_folder,
            right_folder
        )

        update_run_record(
            run_id,
            frame_count=frame_count,
            processing_status="ready for Person 2 data"
        )

        return {
            "run_id": run_id,
            "frame_count": frame_count,
        }

    except Exception:
        update_run_record(
            run_id,
            processing_status="processing failed"
        )
        raise


# =========================================================
# Person 2 Validation
# =========================================================

def validate_person2_files(
    calibrated_df,
    raw_df
):
    missing_calibrated = (
        CALIBRATED_REQUIRED_COLUMNS
        -
        set(calibrated_df.columns)
    )

    if missing_calibrated:
        raise ValueError(
            "Calibrated Results file is missing: "
            +
            ", ".join(
                sorted(missing_calibrated)
            )
        )

    missing_raw = (
        RAW_REQUIRED_COLUMNS
        -
        set(raw_df.columns)
    )

    if missing_raw:
        raise ValueError(
            "RawData file is missing: "
            +
            ", ".join(
                sorted(missing_raw)
            )
        )


# =========================================================
# Parse Calibration
# =========================================================

def parse_calibrated_results(
    calibrated_df
):
    df = calibrated_df.copy()

    df["Channel_norm"] = (
        df["Channel"]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    df["Point_norm"] = (
        df["Point"]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    results = {}

    for source_channel, system_position in [
        ("left", "left"),
        ("center", "centre"),
        ("right", "right"),
    ]:

        channel_df = df[
            df[
                "Channel_norm"
            ]
            ==
            source_channel
        ]

        if channel_df.empty:
            raise ValueError(
                f"No calibrated result for {source_channel}."
            )

        result = {}

        for point_name in [
            "onset",
            "single",
            "clear"
        ]:

            point_df = channel_df[
                channel_df[
                    "Point_norm"
                ]
                ==
                point_name
            ]

            if point_df.empty:
                raise ValueError(
                    f"{source_channel} has no {point_name} result."
                )

            row = point_df.iloc[0]

            result[
                point_name
            ] = {
                "measured":
                    float(
                        row[
                            "Measured(C)"
                        ]
                    ),

                "corrected":
                    float(
                        row[
                            "Corrected(C)"
                        ]
                    ),

                "uncertainty":
                    float(
                        row[
                            "ExpandedUnc_U_k2(C)"
                        ]
                    ),

                "extrapolated":
                    str(
                        row[
                            "Extrapolated"
                        ]
                    ),
            }

        results[
            system_position
        ] = result

    return results


# =========================================================
# Curves
# =========================================================

def save_split_curves(
    raw_df,
    curves_folder
):
    curves_folder = Path(
        curves_folder
    )

    curves_folder.mkdir(
        parents=True,
        exist_ok=True
    )

    channel_map = {
        "left": "Left",
        "centre": "Center",
        "right": "Right",
    }

    curve_files = {}

    for position, source_column in channel_map.items():

        curve_df = pd.DataFrame({
            "Time(s)":
                raw_df[
                    "Time(s)"
                ],

            "Temp(C)":
                raw_df[
                    "Temp(C)"
                ],

            "Signal":
                raw_df[
                    source_column
                ],
        })

        path = (
            curves_folder
            /
            f"{position}_curve.csv"
        )

        curve_df.to_csv(
            path,
            index=False
        )

        curve_files[
            position
        ] = str(path)

    return curve_files


# =========================================================
# Submission Upsert
# =========================================================

def upsert_submission(record):
    conn = get_conn()

    existing = conn.execute("""
        SELECT *
        FROM submissions
        WHERE run_id = ?
        AND tube_position = ?
        LIMIT 1
    """, (
        record["run_id"],
        record["tube_position"],
    )).fetchone()

    if existing:

        current_name = (
            existing[
                "sample_name"
            ]
        )

        if current_name not in [
            "Left",
            "Centre",
            "Right",
        ]:
            record[
                "sample_name"
            ] = current_name

        conn.execute("""
        UPDATE submissions
        SET
            sample_name = ?,
            runtime_timestamp = ?,
            ramp_rate = ?,
            heating_range_low = ?,
            heating_range_high = ?,
            machine_id = ?,
            instrument_name = ?,
            last_calibration_datetime = ?,
            onset_point = ?,
            single_point = ?,
            clear_point = ?,
            measured_onset = ?,
            measured_single = ?,
            measured_clear = ?,
            onset_uncertainty = ?,
            single_uncertainty = ?,
            clear_uncertainty = ?,
            onset_extrapolated = ?,
            single_extrapolated = ?,
            clear_extrapolated = ?,
            frame_folder = ?,
            curve_file = ?,
            imported_at = ?
        WHERE id = ?
        """, (
            record["sample_name"],
            record["runtime_timestamp"],
            record["ramp_rate"],
            record["heating_range_low"],
            record["heating_range_high"],
            record["machine_id"],
            record["instrument_name"],
            record["last_calibration_datetime"],
            record["onset_point"],
            record["single_point"],
            record["clear_point"],
            record["measured_onset"],
            record["measured_single"],
            record["measured_clear"],
            record["onset_uncertainty"],
            record["single_uncertainty"],
            record["clear_uncertainty"],
            record["onset_extrapolated"],
            record["single_extrapolated"],
            record["clear_extrapolated"],
            record["frame_folder"],
            record["curve_file"],
            record["imported_at"],
            existing["id"],
        ))

    else:

        conn.execute("""
        INSERT INTO submissions (
            run_id,
            tube_position,
            sample_name,
            runtime_timestamp,
            ramp_rate,
            heating_range_low,
            heating_range_high,
            machine_id,
            instrument_name,
            last_calibration_datetime,
            onset_point,
            single_point,
            clear_point,
            measured_onset,
            measured_single,
            measured_clear,
            onset_uncertainty,
            single_uncertainty,
            clear_uncertainty,
            onset_extrapolated,
            single_extrapolated,
            clear_extrapolated,
            frame_folder,
            curve_file,
            imported_at
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?
        )
        """, (
            record["run_id"],
            record["tube_position"],
            record["sample_name"],
            record["runtime_timestamp"],
            record["ramp_rate"],
            record["heating_range_low"],
            record["heating_range_high"],
            record["machine_id"],
            record["instrument_name"],
            record["last_calibration_datetime"],
            record["onset_point"],
            record["single_point"],
            record["clear_point"],
            record["measured_onset"],
            record["measured_single"],
            record["measured_clear"],
            record["onset_uncertainty"],
            record["single_uncertainty"],
            record["clear_uncertainty"],
            record["onset_extrapolated"],
            record["single_extrapolated"],
            record["clear_extrapolated"],
            record["frame_folder"],
            record["curve_file"],
            record["imported_at"],
        ))

    conn.commit()
    conn.close()


# =========================================================
# Import Person 2
# =========================================================

def import_person2_data(
    run_id,
    calibrated_df,
    raw_df,
    runtime_timestamp,
    ramp_rate,
    heating_range_low,
    heating_range_high,
    instrument_name,
    machine_id,
    last_calibration_datetime,
):
    validate_person2_files(
        calibrated_df,
        raw_df
    )

    run_folder = (
        RUNS_DIR
        /
        run_id
    )

    if not run_folder.exists():
        raise ValueError(
            "Run folder does not exist."
        )

    results = (
        parse_calibrated_results(
            calibrated_df
        )
    )

    curve_files = (
        save_split_curves(
            raw_df,
            run_folder
            /
            "curves"
        )
    )

    calibrated_path = (
        run_folder
        /
        "calibrated_results.csv"
    )

    raw_path = (
        run_folder
        /
        "raw_data.csv"
    )

    calibrated_df.to_csv(
        calibrated_path,
        index=False
    )

    raw_df.to_csv(
        raw_path,
        index=False
    )

    pretty_names = {
        "left": "Left",
        "centre": "Centre",
        "right": "Right",
    }

    imported_at = (
        datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    )

    for position in [
        "left",
        "centre",
        "right",
    ]:

        result = (
            results[
                position
            ]
        )

        record = {
            "run_id":
                run_id,

            "tube_position":
                position,

            "sample_name":
                pretty_names[
                    position
                ],

            "runtime_timestamp":
                runtime_timestamp.strip(),

            "ramp_rate":
                ramp_rate,

            "heating_range_low":
                heating_range_low,

            "heating_range_high":
                heating_range_high,

            "machine_id":
                machine_id.strip(),

            "instrument_name":
                instrument_name.strip(),

            "last_calibration_datetime":
                last_calibration_datetime.strip(),

            "onset_point":
                result[
                    "onset"
                ][
                    "corrected"
                ],

            "single_point":
                result[
                    "single"
                ][
                    "corrected"
                ],

            "clear_point":
                result[
                    "clear"
                ][
                    "corrected"
                ],

            "measured_onset":
                result[
                    "onset"
                ][
                    "measured"
                ],

            "measured_single":
                result[
                    "single"
                ][
                    "measured"
                ],

            "measured_clear":
                result[
                    "clear"
                ][
                    "measured"
                ],

            "onset_uncertainty":
                result[
                    "onset"
                ][
                    "uncertainty"
                ],

            "single_uncertainty":
                result[
                    "single"
                ][
                    "uncertainty"
                ],

            "clear_uncertainty":
                result[
                    "clear"
                ][
                    "uncertainty"
                ],

            "onset_extrapolated":
                result[
                    "onset"
                ][
                    "extrapolated"
                ],

            "single_extrapolated":
                result[
                    "single"
                ][
                    "extrapolated"
                ],

            "clear_extrapolated":
                result[
                    "clear"
                ][
                    "extrapolated"
                ],

            "frame_folder":
                str(
                    run_folder
                    /
                    f"{position}_frames"
                ),

            "curve_file":
                curve_files[
                    position
                ],

            "imported_at":
                imported_at,
        }

        upsert_submission(
            record
        )

    update_run_record(
        run_id,

        calibrated_file=
            str(
                calibrated_path
            ),

        raw_data_file=
            str(
                raw_path
            ),

        processing_status=
            "complete"
    )


# =========================================================
# Material Names
# =========================================================

def fetch_run_submissions(run_id):
    conn = get_conn()

    df = pd.read_sql_query("""
        SELECT *
        FROM submissions
        WHERE run_id = ?
        ORDER BY
        CASE tube_position
            WHEN 'left' THEN 1
            WHEN 'centre' THEN 2
            WHEN 'right' THEN 3
            ELSE 4
        END
    """,
    conn,
    params=(run_id,)
    )

    conn.close()
    return df


def update_sample_names(
    run_id,
    names
):
    conn = get_conn()

    for position, sample_name in names.items():

        sample_name = (
            sample_name.strip()
        )

        if not sample_name:
            conn.close()

            raise ValueError(
                f"{position} material name cannot be empty."
            )

        conn.execute("""
        UPDATE submissions
        SET sample_name = ?
        WHERE
            run_id = ?
            AND
            tube_position = ?
        """, (
            sample_name,
            run_id,
            position
        ))

    conn.commit()
    conn.close()


# =========================================================
# Recommendation
# =========================================================

def get_recommendations(
    predicted_mp,
    top_n=2
):
    conn = get_conn()

    df = pd.read_sql_query("""
        SELECT *
        FROM submissions
        WHERE clear_point IS NOT NULL
    """, conn)

    conn.close()

    if df.empty:
        return pd.DataFrame()

    df["difference"] = (
        df[
            "clear_point"
        ]
        .astype(float)
        -
        float(predicted_mp)
    ).abs()

    return (
        df
        .sort_values(
            "difference"
        )
        .head(
            top_n
        )
        .reset_index(
            drop=True
        )
    )


# =========================================================
# Viewer Queries
# =========================================================

def fetch_all_results():
    conn = get_conn()

    df = pd.read_sql_query("""
        SELECT
            sub.*,
            r.student_id,
            s.student_name,
            s.email
        FROM submissions sub
        LEFT JOIN experiment_runs r
            ON sub.run_id = r.run_id
        LEFT JOIN students s
            ON r.student_id = s.id
        ORDER BY sub.id DESC
    """, conn)

    conn.close()
    return df


def fetch_student_results(student_id):
    conn = get_conn()

    df = pd.read_sql_query("""
        SELECT
            sub.*,
            r.student_id
        FROM submissions sub
        JOIN experiment_runs r
            ON sub.run_id = r.run_id
        WHERE r.student_id = ?
        ORDER BY r.id DESC
    """,
    conn,
    params=(
        int(student_id),
    )
    )

    conn.close()
    return df


# =========================================================
# Viewer
# =========================================================

def load_frame_paths(frame_folder):
    if (
        frame_folder is None
        or
        pd.isna(
            frame_folder
        )
    ):
        return []

    folder = Path(
        str(
            frame_folder
        )
    )

    if not folder.exists():
        return []

    return sorted(
        folder.glob(
            "frame_*.png"
        )
    )


def render_melting_viewer(
    selected,
    key_prefix
):
    st.markdown(
        "### Sample Details"
    )

    c1, c2, c3 = (
        st.columns(3)
    )

    with c1:
        st.write(
            f"**Material:** "
            f"{selected['sample_name']}"
        )

        st.write(
            f"**Run ID:** "
            f"{selected['run_id']}"
        )

    with c2:
        st.write(
            f"**Position:** "
            f"{selected['tube_position']}"
        )

        st.write(
            f"**Instrument:** "
            f"{selected['instrument_name']}"
        )

    with c3:
        if pd.notna(
            selected[
                "clear_point"
            ]
        ):
            st.write(
                f"**Clear Point:** "
                f"{float(selected['clear_point']):.2f} °C"
            )

        if pd.notna(
            selected[
                "clear_uncertainty"
            ]
        ):
            st.write(
                f"**Expanded uncertainty (k=2):** "
                f"± "
                f"{float(selected['clear_uncertainty']):.2f} °C"
            )

    frame_paths = (
        load_frame_paths(
            selected[
                "frame_folder"
            ]
        )
    )

    if not frame_paths:
        st.warning(
            "No image frames found."
        )
        return

    curve_file = (
        selected[
            "curve_file"
        ]
    )

    if (
        curve_file is None
        or
        pd.isna(
            curve_file
        )
        or
        not Path(
            str(
                curve_file
            )
        ).exists()
    ):
        st.warning(
            "No linked temperature data found."
        )
        return

    curve_df = pd.read_csv(
        curve_file
    )

    usable_count = min(
        len(
            frame_paths
        ),
        len(
            curve_df
        )
    )

    temperatures = (
        curve_df[
            "Temp(C)"
        ]
        .iloc[
            :usable_count
        ]
        .astype(float)
        .tolist()
    )

    times = (
        curve_df[
            "Time(s)"
        ]
        .iloc[
            :usable_count
        ]
        .astype(float)
        .tolist()
    )

    frame_index = (
        st.select_slider(
            "Temperature",

            options=
                list(
                    range(
                        usable_count
                    )
                ),

            value=0,

            format_func=
                lambda i:
                    f"{temperatures[i]:.2f} °C",

            key=
                f"{key_prefix}_temperature"
        )
    )

    current_temperature = (
        temperatures[
            frame_index
        ]
    )

    current_time = (
        times[
            frame_index
        ]
    )

    st.markdown(
        f"### "
        f"{current_temperature:.2f} °C"
    )

    st.caption(
        f"Experiment time: "
        f"{current_time:.2f} s"
    )

    with Image.open(
        frame_paths[
            frame_index
        ]
    ) as image:

        st.image(
            image,

            caption=(
                f"{selected['sample_name']} "
                f"| "
                f"{selected['tube_position']} "
                f"| "
                f"{current_temperature:.2f} °C"
            ),

            width=300
        )


# =========================================================
# Streamlit Setup
# =========================================================

st.set_page_config(
    page_title=
        "Melting Point Experimental Data Portal",
    layout=
        "wide"
)

init_db()


# =========================================================
# Session State
# =========================================================

if (
    "registration_card_value"
    not in
    st.session_state
):
    st.session_state[
        "registration_card_value"
    ] = ""

if (
    "clear_registration_form"
    not in
    st.session_state
):
    st.session_state[
        "clear_registration_form"
    ] = False

if (
    "student_access_id"
    not in
    st.session_state
):
    st.session_state[
        "student_access_id"
    ] = None

if (
    "create_student_id"
    not in
    st.session_state
):
    st.session_state[
        "create_student_id"
    ] = None


# =========================================================
# Title
# =========================================================

st.title(
    "Melting Point Experimental Data Portal"
)

(
    tab_students,
    tab_create,
    tab_import,
    tab_assign,
    tab_recommend,
    tab_view,
    tab_student,
) = st.tabs([
    "Students",
    "Create Experiment Run",
    "Import Person 2 Data",
    "Assign Material Names",
    "Material Recommendation",
    "Admin Viewer",
    "Student Access",
])


# =========================================================
# TAB 1 - Students
# =========================================================

with tab_students:

    st.subheader(
        "Student Registration"
    )

    st.write(
        "Register each student once. "
        "The card credential is used as the student's Card ID."
    )

    # Clear form safely BEFORE widgets are created
    if st.session_state[
        "clear_registration_form"
    ]:

        st.session_state[
            "registration_card_value"
        ] = ""

        st.session_state[
            "student_name_input"
        ] = ""

        st.session_state[
            "student_email_input"
        ] = ""

        st.session_state[
            "clear_registration_form"
        ] = False

    if CARD_READER_AVAILABLE:

        if st.button(
            "Scan Card",
            key=
                "register_scan"
        ):

            try:
                card = scan_card_once()

                st.session_state[
                    "registration_card_value"
                ] = card[
                    "card_id"
                ]

                st.success(
                    f"Card detected: "
                    f"{card['card_id']}"
                )

            except Exception as e:
                st.error(
                    str(e)
                )

    else:
        st.warning(
            "card_reader.py was not found."
        )

    st.text_input(
        "Card ID",

        value=
            st.session_state[
                "registration_card_value"
            ],

        disabled=True
    )

    student_name = st.text_input(
        "Student Name",
        key=
            "student_name_input"
    )

    email = st.text_input(
        "Email",
        key=
            "student_email_input"
    )

    if st.button(
        "Register Student",

        type=
            "primary",

        key=
            "register_student"
    ):

        try:
            create_student(
                st.session_state[
                    "registration_card_value"
                ],
                student_name,
                email
            )

            st.success(
                "Student registered successfully."
            )

            st.session_state[
                "clear_registration_form"
            ] = True

            st.rerun()

        except Exception as e:
            st.error(
                str(e)
            )

    st.markdown(
        "### Registered Students"
    )

    students_df = fetch_students()

    if students_df.empty:
        st.info(
            "No students registered."
        )

    else:
        st.dataframe(
            students_df[[
                "id",
                "student_name",
                "email",
                "card_id",
                "created_at",
            ]],

            use_container_width=True,
            hide_index=True
        )

        st.markdown(
            "### Edit Student Information"
        )

        student_ids = (
            students_df[
                "id"
            ]
            .astype(int)
            .tolist()
        )

        edit_student_id = (
            st.selectbox(
                "Select Student",

                options=
                    student_ids,

                format_func=
                    lambda sid:
                        students_df.loc[
                            students_df[
                                "id"
                            ]
                            == sid,
                            "student_name"
                        ].iloc[0],

                key=
                    "edit_student_select"
            )
        )

        selected_student_row = (
            students_df[
                students_df[
                    "id"
                ]
                ==
                edit_student_id
            ]
            .iloc[0]
        )

        edit_name = st.text_input(
            "Edit Student Name",

            value=
                str(
                    selected_student_row[
                        "student_name"
                    ]
                ),

            key=
                "edit_student_name"
        )

        current_email = (
            selected_student_row[
                "email"
            ]
            if
            pd.notna(
                selected_student_row[
                    "email"
                ]
            )
            else
            ""
        )

        edit_email = st.text_input(
            "Edit Email",

            value=
                str(
                    current_email
                ),

            key=
                "edit_student_email"
        )

        if st.button(
            "Update Student",

            key=
                "update_student_button"
        ):

            try:
                update_student_info(
                    edit_student_id,
                    edit_name,
                    edit_email
                )

                st.success(
                    "Student information updated."
                )

                st.rerun()

            except Exception as e:
                st.error(
                    str(e)
                )


# =========================================================
# TAB 2 - Create Experiment Run
# =========================================================

with tab_create:

    st.subheader(
        "Create New Experiment Run"
    )

    students_df = fetch_students()

    if students_df.empty:
        st.warning(
            "Register a student first."
        )

    else:
        st.write(
            "One experiment run belongs to one student "
            "and contains three material positions."
        )

        student_options = {}

        for _, row in students_df.iterrows():

            student_id = int(
                row[
                    "id"
                ]
            )

            student_name_value = str(
                row[
                    "student_name"
                ]
            )

            email_value = (
                str(
                    row[
                        "email"
                    ]
                ).strip()
                if
                pd.notna(
                    row[
                        "email"
                    ]
                )
                else
                ""
            )

            if email_value:
                label = (
                    f"{student_name_value} "
                    f"({email_value})"
                )
            else:
                label = (
                    student_name_value
                )

            student_options[
                student_id
            ] = label

        if CARD_READER_AVAILABLE:

            if st.button(
                "Scan Card to Select Student",
                key=
                    "create_scan"
            ):

                try:
                    card = scan_card_once()

                    student = (
                        get_student_by_card(
                            card[
                                "card_id"
                            ]
                        )
                    )

                    if student is None:
                        st.error(
                            "This card is not registered."
                        )

                    else:
                        st.session_state[
                            "create_student_id"
                        ] = student[
                            "id"
                        ]

                        st.success(
                            f"Student detected: "
                            f"{student['student_name']}"
                        )

                except Exception as e:
                    st.error(
                        str(e)
                    )

        ids = list(
            student_options.keys()
        )

        if (
            st.session_state[
                "create_student_id"
            ]
            in ids
        ):
            default_index = (
                ids.index(
                    st.session_state[
                        "create_student_id"
                    ]
                )
            )

        else:
            default_index = 0

        selected_student_id = (
            st.selectbox(
                "Student",

                options=
                    ids,

                index=
                    default_index,

                format_func=
                    lambda x:
                        student_options[x],

                key=
                    "create_student_select"
            )
        )

        st.session_state[
            "create_student_id"
        ] = selected_student_id

        uploaded_opm = (
            st.file_uploader(
                "Upload OPM File",

                type=[
                    "opm"
                ],

                key=
                    "opm_upload"
            )
        )

        if st.button(
            "Process OPM and Create Run",

            type=
                "primary",

            key=
                "create_run_button"
        ):

            if uploaded_opm is None:
                st.error(
                    "Please upload an OPM file."
                )

            else:
                try:
                    with st.spinner(
                        "Processing OPM..."
                    ):
                        result = (
                            create_experiment_run(
                                uploaded_opm,
                                selected_student_id
                            )
                        )

                    student = (
                        get_student_by_id(
                            selected_student_id
                        )
                    )

                    st.success(
                        "Experiment run created successfully."
                    )

                    st.write(
                        f"**Student:** "
                        f"{student['student_name']}"
                    )

                    st.write(
                        f"**Run ID:** "
                        f"{result['run_id']}"
                    )

                    st.write(
                        f"**Frames extracted:** "
                        f"{result['frame_count']}"
                    )

                except Exception as e:
                    st.error(
                        f"OPM processing failed: {e}"
                    )

    st.markdown(
        "### Existing Runs"
    )

    runs_df = fetch_runs()

    if not runs_df.empty:

        st.dataframe(
            runs_df[[
                "run_id",
                "student_name",
                "email",
                "opm_filename",
                "frame_count",
                "processing_status",
                "created_at",
            ]],

            use_container_width=True,
            hide_index=True
        )


# =========================================================
# TAB 3 - Person 2
# =========================================================

with tab_import:

    st.subheader(
        "Import Person 2 Data"
    )

    runs_df = fetch_runs()

    if runs_df.empty:
        st.warning(
            "Create an experiment run first."
        )

    else:
        selected_run = (
            st.selectbox(
                "Experiment Run",

                runs_df[
                    "run_id"
                ]
                .tolist(),

                key=
                    "person2_run"
            )
        )

        selected_run_info = (
            runs_df[
                runs_df[
                    "run_id"
                ]
                ==
                selected_run
            ]
            .iloc[0]
        )

        st.write(
            f"**Student:** "
            f"{selected_run_info['student_name']}"
        )

        st.write(
            f"**Email:** "
            f"{selected_run_info['email']}"
        )

        st.write(
            f"**OPM:** "
            f"{selected_run_info['opm_filename']}"
        )

        c1, c2 = st.columns(2)

        with c1:
            calibrated_file = (
                st.file_uploader(
                    "Calibrated Results CSV",

                    type=[
                        "csv"
                    ],

                    key=
                        "calibrated_file"
                )
            )

        with c2:
            raw_file = (
                st.file_uploader(
                    "RawData CSV",

                    type=[
                        "csv"
                    ],

                    key=
                        "raw_file"
                )
            )

        st.markdown(
            "### Run Information"
        )

        a, b = st.columns(2)

        with a:
            runtime_timestamp = (
                st.text_input(
                    "Run-time Timestamp",
                    value=""
                )
            )

            instrument_name = (
                st.text_input(
                    "Instrument Name",
                    value="CG052"
                )
            )

            machine_id = (
                st.text_input(
                    "Machine ID",
                    value="machine 1"
                )
            )

        with b:
            ramp_rate = (
                st.number_input(
                    "Ramp Rate (°C/min)",
                    value=15.0
                )
            )

            heating_range_low = (
                st.number_input(
                    "Heating Range Low (°C)",
                    value=36.0
                )
            )

            heating_range_high = (
                st.number_input(
                    "Heating Range High (°C)",
                    value=150.0
                )
            )

            last_calibration = (
                st.text_input(
                    "Last Calibration",
                    value=""
                )
            )

        if st.button(
            "Import Person 2 Results",

            type=
                "primary",

            key=
                "person2_import"
        ):

            if (
                calibrated_file is None
                or
                raw_file is None
            ):
                st.error(
                    "Upload both CSV files."
                )

            else:
                try:
                    calibrated_file.seek(0)
                    raw_file.seek(0)

                    calibrated_df = (
                        pd.read_csv(
                            calibrated_file
                        )
                    )

                    raw_df = (
                        pd.read_csv(
                            raw_file
                        )
                    )

                    import_person2_data(
                        selected_run,
                        calibrated_df,
                        raw_df,
                        runtime_timestamp,
                        ramp_rate,
                        heating_range_low,
                        heating_range_high,
                        instrument_name,
                        machine_id,
                        last_calibration
                    )

                    st.success(
                        "Person 2 data imported successfully."
                    )

                except Exception as e:
                    st.error(
                        f"Import failed: {e}"
                    )


# =========================================================
# TAB 4 - Material Names
# =========================================================

with tab_assign:

    st.subheader(
        "Assign Material Names"
    )

    runs_df = fetch_runs()

    completed = runs_df[
        runs_df[
            "processing_status"
        ]
        ==
        "complete"
    ]

    if completed.empty:
        st.info(
            "Import Person 2 data first."
        )

    else:
        assign_run = (
            st.selectbox(
                "Experiment Run",

                completed[
                    "run_id"
                ]
                .tolist(),

                key=
                    "assign_run"
            )
        )

        info = (
            completed[
                completed[
                    "run_id"
                ]
                ==
                assign_run
            ]
            .iloc[0]
        )

        st.write(
            f"**Student:** "
            f"{info['student_name']}"
        )

        st.write(
            f"**Email:** "
            f"{info['email']}"
        )

        submission_df = (
            fetch_run_submissions(
                assign_run
            )
        )

        if not submission_df.empty:

            current = {
                row[
                    "tube_position"
                ]:
                row[
                    "sample_name"
                ]

                for _, row
                in submission_df.iterrows()
            }

            x, y, z = (
                st.columns(3)
            )

            with x:
                left_name = (
                    st.text_input(
                        "Left Material",

                        value=
                            current.get(
                                "left",
                                "Left"
                            )
                    )
                )

            with y:
                centre_name = (
                    st.text_input(
                        "Centre Material",

                        value=
                            current.get(
                                "centre",
                                "Centre"
                            )
                    )
                )

            with z:
                right_name = (
                    st.text_input(
                        "Right Material",

                        value=
                            current.get(
                                "right",
                                "Right"
                            )
                    )
                )

            if st.button(
                "Save Material Names",

                type=
                    "primary",

                key=
                    "save_material_names"
            ):

                try:
                    update_sample_names(
                        assign_run,

                        {
                            "left":
                                left_name,

                            "centre":
                                centre_name,

                            "right":
                                right_name,
                        }
                    )

                    st.success(
                        "Material names saved."
                    )

                except Exception as e:
                    st.error(
                        str(e)
                    )


# =========================================================
# TAB 5 - Recommendation
# =========================================================

with tab_recommend:

    st.subheader(
        "Material Recommendation"
    )

    predicted_mp = (
        st.number_input(
            "Predicted Melting Point (°C)",
            value=100.0
        )
    )

    if st.button(
        "Recommend 2 Closest Materials",

        key=
            "recommend"
    ):

        recommendations = (
            get_recommendations(
                predicted_mp
            )
        )

        if recommendations.empty:
            st.warning(
                "No historical data available."
            )

        else:
            st.dataframe(
                recommendations[[
                    "sample_name",
                    "clear_point",
                    "clear_uncertainty",
                    "difference",
                    "run_id",
                ]],

                use_container_width=True,
                hide_index=True
            )


# =========================================================
# TAB 6 - Admin Viewer
# =========================================================

with tab_view:

    st.subheader(
        "Admin Viewer"
    )

    all_results = (
        fetch_all_results()
    )

    if all_results.empty:
        st.info(
            "No results available."
        )

    else:
        working = (
            all_results[[
                "id",
                "student_name",
                "email",
                "sample_name",
                "run_id",
                "tube_position",
                "instrument_name",
                "clear_point",
                "clear_uncertainty",
                "frame_folder",
                "curve_file",
            ]]
            .reset_index(
                drop=True
            )
        )

        display = (
            working.drop(
                columns=[
                    "frame_folder",
                    "curve_file"
                ]
            )
        )

        selection = (
            st.dataframe(
                display,

                use_container_width=True,
                hide_index=True,

                selection_mode=
                    "single-row",

                on_select=
                    "rerun"
            )
        )

        selected_rows = (
            selection
            .selection
            .rows

            if
            selection.selection

            else
            []
        )

        if selected_rows:
            selected = (
                working
                .iloc[
                    selected_rows[0]
                ]
                .to_dict()
            )

            render_melting_viewer(
                selected,
                f"admin_{selected['id']}"
            )

        else:
            st.info(
                "Click a material above."
            )


# =========================================================
# TAB 7 - Student Access
# =========================================================

with tab_student:

    st.subheader(
        "Student Access"
    )

    st.write(
        "Place your student card "
        "on the reader and click Scan Card."
    )

    if CARD_READER_AVAILABLE:

        if st.button(
            "Scan Student Card",

            type=
                "primary",

            key=
                "student_login_scan"
        ):

            try:
                card = scan_card_once()

                student = (
                    get_student_by_card(
                        card[
                            "card_id"
                        ]
                    )
                )

                if student is None:
                    st.session_state[
                        "student_access_id"
                    ] = None

                    st.error(
                        "This card is not registered."
                    )

                else:
                    st.session_state[
                        "student_access_id"
                    ] = student[
                        "id"
                    ]

                    st.success(
                        f"Welcome, "
                        f"{student['student_name']}."
                    )

            except Exception as e:
                st.error(
                    str(e)
                )

    if (
        st.session_state[
            "student_access_id"
        ]
        is not None
    ):

        student = get_student_by_id(
            st.session_state[
                "student_access_id"
            ]
        )

        st.markdown(
            f"### "
            f"{student['student_name']}'s Experiments"
        )

        st.write(
            f"**Email:** "
            f"{student['email']}"
        )

        student_results = (
            fetch_student_results(
                student[
                    "id"
                ]
            )
        )

        if student_results.empty:
            st.info(
                "No experiments found."
            )

        else:
            working = (
                student_results[[
                    "id",
                    "sample_name",
                    "run_id",
                    "tube_position",
                    "instrument_name",
                    "clear_point",
                    "clear_uncertainty",
                    "frame_folder",
                    "curve_file",
                ]]
                .reset_index(
                    drop=True
                )
            )

            display = (
                working.drop(
                    columns=[
                        "frame_folder",
                        "curve_file"
                    ]
                )
            )

            selection = (
                st.dataframe(
                    display,

                    use_container_width=True,
                    hide_index=True,

                    selection_mode=
                        "single-row",

                    on_select=
                        "rerun",

                    key=
                        "student_table"
                )
            )

            selected_rows = (
                selection
                .selection
                .rows

                if
                selection.selection

                else
                []
            )

            if selected_rows:
                selected = (
                    working
                    .iloc[
                        selected_rows[0]
                    ]
                    .to_dict()
                )

                render_melting_viewer(
                    selected,
                    f"student_{selected['id']}"
                )

            else:
                st.info(
                    "Click one material "
                    "to view the melting process."
                )

        if st.button(
            "Log Out",

            key=
                "student_logout"
        ):

            st.session_state[
                "student_access_id"
            ] = None

            st.rerun()
