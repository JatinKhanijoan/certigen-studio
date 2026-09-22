const ICONS = {
  minus: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14"/></svg>',
  plus: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>',
  fit: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 3H3v5M16 3h5v5M8 21H3v-5M16 21h5v-5"/></svg>'
};

const HANDLES = ["nw", "n", "ne", "e", "se", "s", "sw", "w"];
const clamp = (value, min, max) => Math.min(Math.max(value, min), max);
const roundedGeometry = (geometry, imageWidth, imageHeight) => {
  const width = Math.round(clamp(geometry.width, 20, imageWidth));
  const height = Math.round(clamp(geometry.height, 20, imageHeight));
  return {
    left: Math.round(clamp(geometry.left, 0, imageWidth - width)),
    top: Math.round(clamp(geometry.top, 0, imageHeight - height)),
    width,
    height,
  };
};

export default function renderSelectionBox({ data, parentElement, setStateValue }) {
  const root = parentElement.querySelector(".certigen-selection-root");
  if (!root) throw new Error("Selection editor root was not found");

  const imageWidth = Number(data.imageWidth);
  const imageHeight = Number(data.imageHeight);
  let geometry = roundedGeometry({ ...data.geometry }, imageWidth, imageHeight);
  let zoom = 1;
  let interaction = null;

  root.innerHTML = `
    <style>@font-face { font-family: "CertiGenPreview"; src: url("${data.fontUrl}"); font-display: swap; }</style>
    <div class="certigen-editor-shell">
      <div class="certigen-toolbar">
        <div class="certigen-toolbar-copy">
          <div class="certigen-toolbar-title">Name placement</div>
          <div class="certigen-toolbar-help">Drag to move · resize from any handle · arrow keys nudge</div>
        </div>
        <div class="certigen-toolbar-actions" aria-label="Canvas zoom controls">
          <button class="certigen-icon-button" data-action="zoom-out" title="Zoom out" aria-label="Zoom out">${ICONS.minus}</button>
          <span class="certigen-zoom-label" aria-live="polite">100%</span>
          <button class="certigen-icon-button" data-action="zoom-in" title="Zoom in" aria-label="Zoom in">${ICONS.plus}</button>
          <button class="certigen-icon-button" data-action="fit" title="Fit to editor" aria-label="Fit to editor">${ICONS.fit}</button>
        </div>
      </div>
      <div class="certigen-viewport">
        <div class="certigen-stage">
          <img class="certigen-stage-image" src="${data.imageUrl}" alt="Certificate template" draggable="false" />
          <div class="certigen-guide certigen-guide-x"></div>
          <div class="certigen-guide certigen-guide-y"></div>
          <div class="certigen-selection" tabindex="0" role="group" aria-label="Recipient name placement box">
            <div class="certigen-live-text"></div>
            ${HANDLES.map(handle => `<span class="certigen-handle certigen-handle-${handle}" data-handle="${handle}" aria-hidden="true"></span>`).join("")}
          </div>
        </div>
      </div>
      <div class="certigen-status">
        <span class="certigen-position-status"></span>
        <span>Shift + arrow moves 10 px</span>
      </div>
    </div>`;

  const viewport = root.querySelector(".certigen-viewport");
  const stage = root.querySelector(".certigen-stage");
  const selection = root.querySelector(".certigen-selection");
  const liveText = root.querySelector(".certigen-live-text");
  const guideX = root.querySelector(".certigen-guide-x");
  const guideY = root.querySelector(".certigen-guide-y");
  const zoomLabel = root.querySelector(".certigen-zoom-label");
  const status = root.querySelector(".certigen-position-status");

  const baseStageWidth = () => Math.max(280, viewport.clientWidth - 36);
  const stageScale = () => stage.clientWidth / imageWidth;

  function fitText() {
    const scale = stageScale();
    const maxSize = Math.max(1, Math.round(Number(data.fontSize) * scale));
    const maxWidth = Math.max(1, geometry.width * scale - 16);
    const maxHeight = Math.max(1, geometry.height * scale - 8);
    const measure = document.createElement("canvas").getContext("2d");
    let size = maxSize;
    while (size > 1) {
      measure.font = `${size}px CertiGenPreview`;
      const metrics = measure.measureText(data.text || "Recipient name");
      const measuredHeight = (metrics.actualBoundingBoxAscent || size * .75) + (metrics.actualBoundingBoxDescent || size * .25);
      if (metrics.width <= maxWidth && measuredHeight <= maxHeight) break;
      size -= 1;
    }
    liveText.style.fontSize = `${size}px`;
  }

  function paint() {
    const baseWidth = baseStageWidth();
    stage.style.width = `${baseWidth * zoom}px`;
    stage.style.height = `${baseWidth * zoom * imageHeight / imageWidth}px`;
    const scale = stageScale();
    selection.style.left = `${geometry.left * scale}px`;
    selection.style.top = `${geometry.top * scale}px`;
    selection.style.width = `${geometry.width * scale}px`;
    selection.style.height = `${geometry.height * scale}px`;
    liveText.textContent = data.text || "Recipient name";
    liveText.style.color = data.fontColor;
    liveText.style.fontFamily = '"CertiGenPreview", sans-serif';
    zoomLabel.textContent = `${Math.round(zoom * 100)}%`;
    status.textContent = `Left ${geometry.left}px · Top ${geometry.top}px · ${geometry.width} × ${geometry.height}px`;
    fitText();
  }

  function showGuides(showX, showY) {
    guideX.classList.toggle("is-visible", showX);
    guideY.classList.toggle("is-visible", showY);
  }

  function commit() {
    geometry = roundedGeometry(geometry, imageWidth, imageHeight);
    paint();
    setStateValue("geometry", geometry);
  }

  function beginInteraction(event) {
    if (event.button !== 0) return;
    event.preventDefault();
    selection.focus({ preventScroll: true });
    interaction = {
      handle: event.target.dataset.handle || "move",
      startX: event.clientX,
      startY: event.clientY,
      origin: { ...geometry },
    };
    selection.setPointerCapture?.(event.pointerId);
  }

  function moveInteraction(event) {
    if (!interaction) return;
    event.preventDefault();
    const scale = stageScale();
    const dx = (event.clientX - interaction.startX) / scale;
    const dy = (event.clientY - interaction.startY) / scale;
    const origin = interaction.origin;
    const handle = interaction.handle;
    let next = { ...origin };

    if (handle === "move") {
      next.left = origin.left + dx;
      next.top = origin.top + dy;
    } else {
      if (handle.includes("e")) next.width = origin.width + dx;
      if (handle.includes("s")) next.height = origin.height + dy;
      if (handle.includes("w")) { next.left = origin.left + dx; next.width = origin.width - dx; }
      if (handle.includes("n")) { next.top = origin.top + dy; next.height = origin.height - dy; }
      if (next.width < 20) { if (handle.includes("w")) next.left = origin.left + origin.width - 20; next.width = 20; }
      if (next.height < 20) { if (handle.includes("n")) next.top = origin.top + origin.height - 20; next.height = 20; }
    }

    next.width = clamp(next.width, 20, imageWidth);
    next.height = clamp(next.height, 20, imageHeight);
    next.left = clamp(next.left, 0, imageWidth - next.width);
    next.top = clamp(next.top, 0, imageHeight - next.height);

    const snapDistance = 9 / scale;
    const centerDeltaX = next.left + next.width / 2 - imageWidth / 2;
    const centerDeltaY = next.top + next.height / 2 - imageHeight / 2;
    const snapX = Math.abs(centerDeltaX) <= snapDistance;
    const snapY = Math.abs(centerDeltaY) <= snapDistance;
    if (snapX) next.left = imageWidth / 2 - next.width / 2;
    if (snapY) next.top = imageHeight / 2 - next.height / 2;
    showGuides(snapX, snapY);
    geometry = next;
    paint();
  }

  function endInteraction() {
    if (!interaction) return;
    interaction = null;
    showGuides(false, false);
    commit();
  }

  function keydown(event) {
    const directions = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
    if (!directions[event.key]) return;
    event.preventDefault();
    const step = event.shiftKey ? 10 : 1;
    geometry.left += directions[event.key][0] * step;
    geometry.top += directions[event.key][1] * step;
    commit();
  }

  selection.addEventListener("pointerdown", beginInteraction);
  window.addEventListener("pointermove", moveInteraction);
  window.addEventListener("pointerup", endInteraction);
  selection.addEventListener("keydown", keydown);

  root.querySelector('[data-action="zoom-in"]').addEventListener("click", () => { zoom = clamp(zoom + .1, .6, 1.8); paint(); });
  root.querySelector('[data-action="zoom-out"]').addEventListener("click", () => { zoom = clamp(zoom - .1, .6, 1.8); paint(); });
  root.querySelector('[data-action="fit"]').addEventListener("click", () => { zoom = 1; viewport.scrollTo({ left: 0, top: 0, behavior: "smooth" }); paint(); });

  const observer = new ResizeObserver(paint);
  observer.observe(viewport);
  document.fonts?.ready.then(paint);
  paint();
  requestAnimationFrame(() => selection.focus({ preventScroll: true }));

  return () => {
    observer.disconnect();
    window.removeEventListener("pointermove", moveInteraction);
    window.removeEventListener("pointerup", endInteraction);
  };
}
