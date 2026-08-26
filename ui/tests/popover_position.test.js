"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const { anchoredPopoverPosition } = require("../popover-position.js");

const viewport = { left: 0, top: 0, width: 1280, height: 800 };
const menu = { width: 240, height: 150 };

test("places every reasoning row above an ordinary docked composer without clipping", () => {
  assert.deepEqual(
    anchoredPopoverPosition(
      { left: 210, right: 330, top: 690, bottom: 730 },
      menu,
      viewport,
    ),
    { left: 210, top: 532, placement: "above" },
  );
});

test("tracks an expanded composer instead of using its former static offset", () => {
  assert.deepEqual(
    anchoredPopoverPosition(
      { left: 210, right: 330, top: 430, bottom: 470 },
      menu,
      viewport,
    ),
    { left: 210, top: 272, placement: "above" },
  );
});

test("falls below near the top and clamps inside visual viewport edges", () => {
  assert.deepEqual(
    anchoredPopoverPosition(
      { left: 610, right: 730, top: 24, bottom: 64 },
      menu,
      { left: 100, top: 10, width: 640, height: 400 },
      { direction: "rtl" },
    ),
    { left: 490, top: 72, placement: "below" },
  );
  assert.equal(
    anchoredPopoverPosition(
      { left: -20, right: 80, top: 300, bottom: 340 },
      menu,
      viewport,
    ).left,
    8,
  );
});
