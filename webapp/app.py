"""CertiGen Studio — polished certificate batch editor."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from PIL import Image, ImageStat

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from certigen import CertificateGenerator, TextRegion
from webapp.selection_box import selection_box


DEFAULT_FONT_PATH = ROOT_DIR / "examples" / "OpenSans-VariableFont_wdth,wght.ttf"


def _workspace() -> Path:
    if "workspace" not in st.session_state:
        st.session_state.workspace = Path(tempfile.mkdtemp(prefix="certigen-web-"))
    return st.session_state.workspace


def _clear_workspace() -> None:
    upload_generation = st.session_state.get("upload_generation", 0) + 1
    workspace = st.session_state.get("workspace")
    if workspace:
        shutil.rmtree(workspace, ignore_errors=True)
    for key in list(st.session_state):
        del st.session_state[key]
    # File uploaders retain their browser state even after session keys are
    # deleted. New widget keys make Streamlit render empty uploaders.
    st.session_state.upload_generation = upload_generation


def _save_upload(upload: Any, destination: Path) -> Path:
    destination.write_bytes(upload.getvalue())
    return destination


def _data_url(data: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _read_csv(upload: Any) -> pd.DataFrame:
    try:
        return pd.read_csv(io.BytesIO(upload.getvalue()), encoding="utf-8-sig")
    except UnicodeDecodeError:
        return pd.read_csv(io.BytesIO(upload.getvalue()), encoding="latin-1")


def _column_index(columns: list[str], candidates: list[str], default: int = 0) -> int:
    lowered = {column.strip().lower(): index for index, column in enumerate(columns)}
    for candidate in candidates:
        if candidate in lowered:
            return lowered[candidate]
    return default


def _default_placement(image_size: tuple[int, int]) -> dict[str, int]:
    image_width, image_height = image_size
    width = min(max(160, round(image_width * 0.55)), image_width)
    height = min(max(48, round(image_height * 0.10)), image_height)
    return {
        "left": (image_width - width) // 2,
        "top": (image_height - height) // 2,
        "width": width,
        "height": height,
    }


def _suggest_text_color(template_path: Path, placement: dict[str, int]) -> str:
    """Choose a readable initial color from the background under the name box."""
    with Image.open(template_path).convert("RGB") as image:
        left, top = placement["left"], placement["top"]
        crop = image.crop((left, top, left + placement["width"], top + placement["height"]))
        crop.thumbnail((160, 80))
        red, green, blue = ImageStat.Stat(crop).mean[:3]
    luminance = (0.2126 * red) + (0.7152 * green) + (0.0722 * blue)
    return "#F8FAFC" if luminance < 145 else "#111827"


def _clamp_placement(placement: dict[str, Any], image_size: tuple[int, int]) -> dict[str, int]:
    image_width, image_height = image_size
    width = min(max(20, round(float(placement["width"]))), image_width)
    height = min(max(20, round(float(placement["height"]))), image_height)
    left = min(max(0, round(float(placement["left"]))), image_width - width)
    top = min(max(0, round(float(placement["top"]))), image_height - height)
    return {"left": left, "top": top, "width": width, "height": height}


def _invalidate_output() -> None:
    st.session_state.pop("zip_bytes", None)
    st.session_state.pop("zip_label", None)


def _commit_placement(new_placement: dict[str, Any], *, external: bool = False) -> None:
    new_value = _clamp_placement(new_placement, tuple(st.session_state.image_size))
    current = st.session_state.get("placement")
    if current == new_value:
        return
    if current:
        history = list(st.session_state.get("placement_history", []))
        history.append(current.copy())
        st.session_state.placement_history = history[-50:]
    st.session_state.placement = new_value
    st.session_state.placement_redo = []
    if external:
        st.session_state.editor_revision = st.session_state.get("editor_revision", 0) + 1
    _invalidate_output()


def _sync_geometry_inputs(placement: dict[str, int]) -> None:
    st.session_state.placement_left = placement["left"]
    st.session_state.placement_top = placement["top"]
    st.session_state.placement_width = placement["width"]
    st.session_state.placement_height = placement["height"]


def _apply_geometry_inputs() -> None:
    _commit_placement(
        {
            "left": st.session_state.placement_left,
            "top": st.session_state.placement_top,
            "width": st.session_state.placement_width,
            "height": st.session_state.placement_height,
        },
        external=True,
    )


def _undo_placement() -> None:
    history = list(st.session_state.get("placement_history", []))
    if not history:
        return
    current = st.session_state.placement.copy()
    st.session_state.placement = history.pop()
    st.session_state.placement_history = history
    st.session_state.placement_redo = list(st.session_state.get("placement_redo", [])) + [current]
    st.session_state.editor_revision = st.session_state.get("editor_revision", 0) + 1
    _invalidate_output()


def _redo_placement() -> None:
    redo = list(st.session_state.get("placement_redo", []))
    if not redo:
        return
    current = st.session_state.placement.copy()
    st.session_state.placement = redo.pop()
    st.session_state.placement_redo = redo
    st.session_state.placement_history = list(st.session_state.get("placement_history", [])) + [current]
    st.session_state.editor_revision = st.session_state.get("editor_revision", 0) + 1
    _invalidate_output()


def _center_placement() -> None:
    placement = st.session_state.placement.copy()
    placement["left"] = (st.session_state.image_size[0] - placement["width"]) // 2
    _commit_placement(placement, external=True)


def _reset_placement() -> None:
    _commit_placement(_default_placement(tuple(st.session_state.image_size)), external=True)


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def _text_region(placement: dict[str, int], font_size: int, font_color: str) -> TextRegion:
    return TextRegion(
        x=round(placement["left"] + placement["width"] / 2),
        y=round(placement["top"] + placement["height"] / 2),
        width=placement["width"],
        height=placement["height"],
        text_color=_hex_to_rgb(font_color),
        bg_color=(255, 255, 255),
        detected_font_size=font_size,
        placeholder_box=None,
        placeholder_found=True,
        center_text=True,
        box_left=placement["left"],
        box_top=placement["top"],
        text_align="center",
    )


def _generator(
    template_path: Path,
    names_path: Path,
    font_path: Path,
    placement: dict[str, int],
    font_size: int,
    font_color: str,
) -> CertificateGenerator:
    region = _text_region(placement, font_size, font_color)
    generator = CertificateGenerator(
        template_path=str(template_path),
        excel_path=str(names_path),
        name_column="Name",
        font_path=str(font_path),
        output_dir=str(names_path.parent / "output"),
        manual_position=(region.x, region.y),
        max_text_width=region.width,
        base_font_size=font_size,
        min_font_size=1,
        verbose=False,
    )
    generator.text_region = region
    return generator


def _safe_filename(name_parts: list[str], used: set[str], extension: str) -> str:
    def clean(value: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9]+", "_", str(value).strip())
        return cleaned.strip("_").lower() or "unknown"

    base = "_".join(clean(part) for part in name_parts if str(part).strip()) or "unknown"
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}_{suffix}"
        suffix += 1
    used.add(candidate)
    return f"{candidate}.{extension}"


st.set_page_config(page_title="CertiGen Studio", page_icon="C", layout="wide")
st.markdown(
    """<style>
    :root { color-scheme: dark; }
    .stApp { background: #090f1a; }
    .block-container { max-width: 1360px; padding: 4.5rem 2rem 4rem; }
    h1, h2, h3 { letter-spacing: -0.025em; }
    [data-testid="stFileUploaderDropzone"] { border: 1px dashed #475569; background: #111827; border-radius: 12px; }
    [data-testid="stFileUploaderDropzone"]:hover { border-color: #38bdf8; }
    [data-testid="stMetric"] { border: 1px solid #263449; border-radius: 12px; padding: 14px 16px; background: #111827; }
    [data-testid="stVerticalBlockBorderWrapper"] { border-color: #263449; border-radius: 14px; background: #0d1524; }
    .certigen-kicker { color: #38bdf8; font-size: .78rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }
    .certigen-lead { max-width: 760px; color: #a7b4c7; font-size: 1.05rem; line-height: 1.65; }
    .certigen-step { display: inline-flex; align-items: center; gap: .5rem; margin-bottom: .45rem; color: #7dd3fc; font-size: .78rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
    .certigen-step span { display: inline-grid; width: 1.55rem; height: 1.55rem; place-items: center; border-radius: 999px; background: #0c4a6e; color: #e0f2fe; }
    .certigen-hint { color: #94a3b8; font-size: .86rem; line-height: 1.55; }
    .certigen-summary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .65rem; margin-top: .5rem; }
    .certigen-summary div { padding: .75rem; border: 1px solid #263449; border-radius: 10px; background: #111827; }
    .certigen-summary small { display: block; color: #8291a7; }
    .certigen-summary strong { display: block; margin-top: .2rem; color: #e5eef8; font-variant-numeric: tabular-nums; }
    @media (max-width: 760px) { .block-container { padding: 4rem .8rem 3rem; } .certigen-summary { grid-template-columns: repeat(2, 1fr); } }
    </style>""",
    unsafe_allow_html=True,
)

header_left, header_right = st.columns([5, 1])
with header_left:
    st.markdown('<div class="certigen-kicker">Certificate batch studio</div>', unsafe_allow_html=True)
    st.title("CertiGen Studio")
    st.markdown(
        '<div class="certigen-lead">Add a clean certificate, place a live recipient name exactly where it belongs, '
        "and export production-ready certificates without OCR or destructive placeholder removal.</div>",
        unsafe_allow_html=True,
    )
with header_right:
    st.button("Start over", on_click=_clear_workspace, width="stretch")

st.markdown("---")
st.markdown('<div class="certigen-step"><span>1</span> Add your content</div>', unsafe_allow_html=True)
st.subheader("Upload a clean template and recipient list")
st.markdown(
    '<div class="certigen-hint">Use a PNG or JPEG without a sample name. Your background artwork and underline remain untouched.</div>',
    unsafe_allow_html=True,
)

upload_left, upload_right = st.columns(2)
with upload_left:
    template_upload = st.file_uploader(
        "Clean certificate template",
        type=["png", "jpg", "jpeg"],
        help="Upload the final certificate artwork without placeholder text.",
        key=f"template_upload_{st.session_state.get('upload_generation', 0)}",
    )
with upload_right:
    names_upload = st.file_uploader(
        "Recipients CSV",
        type=["csv"],
        help="Use two columns (first and last name) or three (first, middle, and last name).",
        key=f"recipients_upload_{st.session_state.get('upload_generation', 0)}",
    )

if not template_upload or not names_upload:
    st.info("Upload both files to open the placement editor.")
    st.stop()

workspace = _workspace()
template_suffix = Path(template_upload.name).suffix.lower() or ".png"
template_path = workspace / f"template{template_suffix}"
template_hash = hashlib.sha256(template_upload.getvalue()).hexdigest()

if st.session_state.get("template_hash") != template_hash:
    _save_upload(template_upload, template_path)
    image_size = Image.open(template_path).size
    st.session_state.template_hash = template_hash
    st.session_state.image_size = list(image_size)
    st.session_state.placement = _default_placement(image_size)
    st.session_state.font_color = _suggest_text_color(template_path, st.session_state.placement)
    st.session_state.font_size = min(120, max(48, image_size[1] // 18))
    st.session_state.placement_history = []
    st.session_state.placement_redo = []
    st.session_state.editor_revision = 0
    for key in ("placement_left", "placement_top", "placement_width", "placement_height"):
        st.session_state.pop(key, None)
    _invalidate_output()
else:
    image_size = tuple(st.session_state.image_size)

try:
    names_df = _read_csv(names_upload)
except Exception as exc:
    st.error(f"Could not read the CSV: {exc}")
    st.stop()

if names_df.empty or not list(names_df.columns):
    st.error("The CSV needs a header row and at least one recipient.")
    st.stop()

columns = list(names_df.columns)
if len(columns) not in (2, 3):
    st.error("The CSV must have exactly two columns (first and last name) or three (first, middle, and last name).")
    st.stop()

mapping_columns = st.columns(4 if len(columns) == 3 else 3)
with mapping_columns[0]:
    first_column = st.selectbox("First-name column", columns, index=_column_index(columns, ["first_name", "first name", "firstname"]))
if len(columns) == 3:
    with mapping_columns[1]:
        middle_column = st.selectbox("Middle-name column", columns, index=_column_index(columns, ["middle_name", "middle name", "middlename", "middle"], default=1))
    last_mapping_column = mapping_columns[2]
    format_mapping_column = mapping_columns[3]
else:
    middle_column = None
    last_mapping_column = mapping_columns[1]
    format_mapping_column = mapping_columns[2]
with last_mapping_column:
    last_column = st.selectbox("Last-name column", columns, index=_column_index(columns, ["last_name", "last name", "lastname", "surname"], default=len(columns) - 1))
with format_mapping_column:
    output_format = st.selectbox("Output format", ["PDF", "PNG", "JPEG"])

selected_name_columns = [first_column, *([middle_column] if middle_column else []), last_column]
if len(set(selected_name_columns)) != len(selected_name_columns):
    st.error("Choose a different CSV column for each name part.")
    st.stop()

recipients = names_df[selected_name_columns].copy().dropna(how="all")
for column in selected_name_columns:
    recipients[column] = recipients[column].fillna("").astype(str).str.strip()
recipients = recipients[recipients[selected_name_columns].ne("").any(axis=1)]
recipients["Name"] = recipients[selected_name_columns].agg(" ".join, axis=1).str.replace(r"\s+", " ", regex=True).str.strip()
if recipients.empty:
    st.error("No usable recipients were found in the selected columns.")
    st.stop()

st.markdown("---")
st.markdown('<div class="certigen-step"><span>2</span> Design the name field</div>', unsafe_allow_html=True)
st.subheader("Place the live recipient name")

editor_column, settings_column = st.columns([2.25, 1], gap="large")
with settings_column:
    with st.container(border=True):
        st.markdown("#### Preview content")
        preview_name = st.selectbox("Sample recipient", recipients["Name"].tolist(), index=0)

        st.markdown("#### Typography")
        custom_font = st.file_uploader(
            "Custom font",
            type=["ttf", "otf"],
            help="Optional. Upload the licensed font used by your certificate design.",
        )
        font_size = st.slider(
            "Maximum font size",
            min_value=8,
            max_value=max(48, min(320, image_size[1] // 3)),
            key="font_size",
        )
        font_color = st.color_picker("Text color", key="font_color")
        st.caption("Long names automatically shrink to stay inside the box.")

        if custom_font:
            font_suffix = Path(custom_font.name).suffix.lower()
            font_path = workspace / f"custom_font{font_suffix}"
            _save_upload(custom_font, font_path)
            font_bytes = custom_font.getvalue()
            font_mime = "font/otf" if font_suffix == ".otf" else "font/ttf"
        else:
            font_path = DEFAULT_FONT_PATH
            font_bytes = DEFAULT_FONT_PATH.read_bytes()
            font_mime = "font/ttf"

        st.markdown("#### Position and size")
        placement = _clamp_placement(st.session_state.placement, image_size)
        st.session_state.placement = placement
        _sync_geometry_inputs(placement)
        input_left, input_top = st.columns(2)
        with input_left:
            st.number_input("Left", min_value=0, max_value=max(0, image_size[0] - placement["width"]), step=1, key="placement_left", on_change=_apply_geometry_inputs)
        with input_top:
            st.number_input("Top", min_value=0, max_value=max(0, image_size[1] - placement["height"]), step=1, key="placement_top", on_change=_apply_geometry_inputs)
        input_width, input_height = st.columns(2)
        with input_width:
            st.number_input("Width", min_value=20, max_value=image_size[0], step=1, key="placement_width", on_change=_apply_geometry_inputs)
        with input_height:
            st.number_input("Height", min_value=20, max_value=image_size[1], step=1, key="placement_height", on_change=_apply_geometry_inputs)

        history_left, history_right = st.columns(2)
        with history_left:
            st.button("Undo", on_click=_undo_placement, disabled=not st.session_state.get("placement_history"), width="stretch")
        with history_right:
            st.button("Redo", on_click=_redo_placement, disabled=not st.session_state.get("placement_redo"), width="stretch")
        center_column, reset_column = st.columns(2)
        with center_column:
            st.button("Center", on_click=_center_placement, width="stretch", help="Center horizontally")
        with reset_column:
            st.button("Reset", on_click=_reset_placement, width="stretch", help="Restore the initial centered box")

        placement = st.session_state.placement
        st.markdown(
            f'<div class="certigen-summary"><div><small>Left</small><strong>{placement["left"]} px</strong></div>'
            f'<div><small>Top</small><strong>{placement["top"]} px</strong></div>'
            f'<div><small>Width</small><strong>{placement["width"]} px</strong></div>'
            f'<div><small>Height</small><strong>{placement["height"]} px</strong></div></div>',
            unsafe_allow_html=True,
        )

with editor_column:
    image_mime = "image/png" if template_suffix == ".png" else "image/jpeg"
    component_height = min(790, max(480, round(820 * image_size[1] / image_size[0]) + 125))
    canvas_geometry = selection_box(
        image_url=_data_url(template_upload.getvalue(), image_mime),
        image_width=image_size[0],
        image_height=image_size[1],
        geometry=st.session_state.placement,
        text=preview_name,
        font_size=font_size,
        font_color=font_color,
        font_url=_data_url(font_bytes, font_mime),
        revision=st.session_state.editor_revision,
        height=component_height,
        key=f"name_editor_{template_hash}",
    )
    if canvas_geometry:
        previous_canvas_geometry = st.session_state.placement.copy()
        _commit_placement(canvas_geometry)
        if st.session_state.placement != previous_canvas_geometry:
            st.rerun()

st.markdown("---")
st.markdown('<div class="certigen-step"><span>3</span> Review and export</div>', unsafe_allow_html=True)
st.subheader("Verify the production render")

names_path = workspace / "names.csv"
pd.DataFrame({"Name": recipients["Name"]}).to_csv(names_path, index=False)
active_placement = _clamp_placement(st.session_state.placement, image_size)
render_signature = hashlib.sha256(
    json.dumps(
        {
            "template": template_hash,
            "recipients": recipients["Name"].tolist(),
            "format": output_format,
            "placement": active_placement,
            "font_size": font_size,
            "font_color": font_color,
            "font": hashlib.sha256(font_bytes).hexdigest(),
        },
        sort_keys=True,
    ).encode("utf-8")
).hexdigest()
if st.session_state.get("zip_signature") not in (None, render_signature):
    _invalidate_output()
    st.session_state.pop("zip_signature", None)

try:
    generator = _generator(template_path, names_path, font_path, active_placement, font_size, font_color)
    preview = generator.render_certificate(preview_name)
except Exception as exc:
    st.error(f"Could not render the certificate: {exc}")
    st.stop()

review_left, review_right = st.columns([2.25, 1], gap="large")
with review_left:
    st.image(preview, caption=f"Production preview · {preview_name}", width="stretch")
with review_right:
    metric_left, metric_right = st.columns(2)
    metric_left.metric("Recipients", len(recipients))
    metric_right.metric("Format", output_format)
    st.markdown("#### Final placement")
    st.markdown(
        f'<div class="certigen-summary"><div><small>Left</small><strong>{active_placement["left"]} px</strong></div>'
        f'<div><small>Top</small><strong>{active_placement["top"]} px</strong></div>'
        f'<div><small>Width</small><strong>{active_placement["width"]} px</strong></div>'
        f'<div><small>Height</small><strong>{active_placement["height"]} px</strong></div></div>',
        unsafe_allow_html=True,
    )
    with st.expander("Review recipient data"):
        st.dataframe(recipients[selected_name_columns + ["Name"]], hide_index=True, width="stretch")

    if st.button("Generate certificate ZIP", type="primary", width="stretch"):
        output_dir = workspace / "certificates"
        output_dir.mkdir(exist_ok=True)
        extension = {"PDF": "pdf", "PNG": "png", "JPEG": "jpeg"}[output_format]
        used: set[str] = set()
        zip_path = workspace / "certificates.zip"
        try:
            progress = st.progress(0, text="Preparing certificates…")
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
                for index, (_, recipient) in enumerate(recipients.iterrows(), start=1):
                    filename = _safe_filename([recipient[column] for column in selected_name_columns], used, extension)
                    certificate_path = output_dir / filename
                    CertificateGenerator.save_certificate(generator.render_certificate(recipient["Name"]), str(certificate_path), extension)
                    archive.write(certificate_path, arcname=filename)
                    progress.progress(index / len(recipients), text=f"Created {index} of {len(recipients)} certificates")
            st.session_state.zip_bytes = zip_path.read_bytes()
            st.session_state.zip_label = f"certificates_{output_format.lower()}.zip"
            st.session_state.zip_signature = render_signature
            st.success(f"Created {len(recipients)} certificates successfully.")
        except Exception as exc:
            st.error(f"Generation failed: {exc}")

    if zip_bytes := st.session_state.get("zip_bytes"):
        st.download_button(
            "Download ZIP",
            data=zip_bytes,
            file_name=st.session_state.zip_label,
            mime="application/zip",
            type="primary",
            width="stretch",
        )
