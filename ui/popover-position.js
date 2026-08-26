/* Viewport-safe positioning for document-level popovers anchored to clipped controls. */
"use strict";

((global) => {
  const finite = (value, fallback = 0) => Number.isFinite(Number(value)) ? Number(value) : fallback;
  const clamp = (value, low, high) => Math.min(Math.max(value, low), Math.max(low, high));

  function anchoredPopoverPosition(anchor, popover, viewport, options = {}) {
    const margin = Math.max(0, finite(options.margin, 8));
    const gap = Math.max(0, finite(options.gap, 8));
    const view = {
      left: finite(viewport?.left),
      top: finite(viewport?.top),
      width: Math.max(0, finite(viewport?.width)),
      height: Math.max(0, finite(viewport?.height)),
    };
    const menu = {
      width: Math.max(0, finite(popover?.width)),
      height: Math.max(0, finite(popover?.height)),
    };
    const button = {
      left: finite(anchor?.left),
      right: finite(anchor?.right),
      top: finite(anchor?.top),
      bottom: finite(anchor?.bottom),
    };
    const minLeft = view.left + margin;
    const maxLeft = view.left + view.width - margin - menu.width;
    const preferredLeft = options.direction === "rtl"
      ? button.right - menu.width
      : button.left;
    const minTop = view.top + margin;
    const maxTop = view.top + view.height - margin - menu.height;
    const above = button.top - gap - menu.height;
    const below = button.bottom + gap;
    const roomAbove = button.top - minTop;
    const roomBelow = view.top + view.height - margin - button.bottom;
    const placement = above >= minTop || roomAbove >= roomBelow ? "above" : "below";
    return {
      left: clamp(preferredLeft, minLeft, maxLeft),
      top: clamp(placement === "above" ? above : below, minTop, maxTop),
      placement,
    };
  }

  const api = { anchoredPopoverPosition };
  global.MutaPopoverPosition = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : window);
