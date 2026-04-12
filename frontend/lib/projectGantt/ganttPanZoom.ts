type PanZoomOptions = {
  shell: HTMLElement;
  host: HTMLElement;
  onZoomChange?: (zoom: number) => void;
};

const MIN_ZOOM = 0.7;
const MAX_ZOOM = 1.9;

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function isInteractiveTarget(target: EventTarget | null) {
  if (!(target instanceof Element)) return false;
  return Boolean(
    target.closest("button, input, textarea, select, a, .bar-wrapper, .popup-wrapper"),
  );
}

export function setGanttZoom(host: HTMLElement, nextZoom: number) {
  host.style.zoom = `${nextZoom}`;
}

export function attachGanttPanZoom({ shell, host, onZoomChange }: PanZoomOptions) {
  const container = host.querySelector<HTMLElement>(".gantt-container");
  if (!container) return () => undefined;

  let zoom = Number.parseFloat(host.style.zoom || "1") || 1;
  let dragging = false;
  let pointerStartX = 0;
  let pointerStartY = 0;
  let scrollStartLeft = 0;
  let scrollStartTop = 0;

  const handleMouseDown = (event: MouseEvent) => {
    if (event.button !== 0) return;
    if (isInteractiveTarget(event.target)) return;
    dragging = true;
    pointerStartX = event.clientX;
    pointerStartY = event.clientY;
    scrollStartLeft = container.scrollLeft;
    scrollStartTop = container.scrollTop;
    shell.classList.add("is-panning");
    event.preventDefault();
  };

  const handleMouseMove = (event: MouseEvent) => {
    if (!dragging) return;
    const nextLeft = scrollStartLeft - (event.clientX - pointerStartX);
    const nextTop = scrollStartTop - (event.clientY - pointerStartY);
    container.scrollLeft = nextLeft;
    container.scrollTop = nextTop;
  };

  const stopDrag = () => {
    dragging = false;
    shell.classList.remove("is-panning");
  };

  const handleWheel = (event: WheelEvent) => {
    if (isInteractiveTarget(event.target)) return;
    event.preventDefault();
    zoom = clamp(zoom - event.deltaY * 0.0012, MIN_ZOOM, MAX_ZOOM);
    setGanttZoom(host, zoom);
    onZoomChange?.(zoom);
  };

  shell.addEventListener("mousedown", handleMouseDown);
  shell.addEventListener("wheel", handleWheel, { passive: false });
  window.addEventListener("mousemove", handleMouseMove);
  window.addEventListener("mouseup", stopDrag);

  return () => {
    shell.removeEventListener("mousedown", handleMouseDown);
    shell.removeEventListener("wheel", handleWheel);
    window.removeEventListener("mousemove", handleMouseMove);
    window.removeEventListener("mouseup", stopDrag);
  };
}
