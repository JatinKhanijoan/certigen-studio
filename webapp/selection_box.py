"""Purpose-built Streamlit component for positioning certificate text."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

import streamlit as st


@lru_cache(maxsize=1)
def _component() -> Callable[..., Any]:
    asset_dir = Path(__file__).resolve().parent
    return st.components.v2.component(
        "certigen.selection-box",
        js=(asset_dir / "selection_box.js").read_text(encoding="utf-8"),
        css=(asset_dir / "selection_box.css").read_text(encoding="utf-8"),
        html='<div class="certigen-selection-root"></div>',
    )


def _noop() -> None:
    """Components v2 requires a callback for every returned state field."""


def selection_box(
    *,
    image_url: str,
    image_width: int,
    image_height: int,
    geometry: dict[str, int],
    text: str,
    font_size: int,
    font_color: str,
    font_url: str,
    revision: int,
    height: int,
    key: str,
) -> dict[str, int] | None:
    """Render the text placement editor and return committed geometry."""
    raw = _component()(
        key=key,
        data={
            "imageUrl": image_url,
            "imageWidth": image_width,
            "imageHeight": image_height,
            "geometry": geometry,
            "text": text,
            "fontSize": font_size,
            "fontColor": font_color,
            "fontUrl": font_url,
            "revision": revision,
        },
        default={"geometry": None},
        on_geometry_change=_noop,
        height=height,
    )
    return getattr(raw, "geometry", None)
