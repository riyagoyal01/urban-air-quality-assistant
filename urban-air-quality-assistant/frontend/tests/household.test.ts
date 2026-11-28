import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  buildChatPayload,
  buildIndoorAdvicePayload,
  createRequestSequence,
  isLocationRequestCurrent,
} from "../src/household.ts";

test("purifier and cooking fuel refresh payloads use the latest selections", () => {
  assert.deepEqual(
    buildIndoorAdvicePayload(24.5, "yes", "electricity", "µg/m³"),
    {
      pm2_5: 24.5,
      pm2_5_unit: "µg/m³",
      has_air_purifier: true,
      cooking_fuel: "electricity",
    },
  );
  assert.equal(
    buildIndoorAdvicePayload(24.5, "no", "wood").has_air_purifier,
    false,
  );
});

test("rapid preference changes only accept the newest indoor request", () => {
  const sequence = createRequestSequence();
  const first = sequence.begin();
  const second = sequence.begin();

  assert.equal(sequence.isCurrent(first), false);
  assert.equal(sequence.isCurrent(second), true);
});

test("city changes reject results from an earlier city", () => {
  const sequence = createRequestSequence();
  const cityARequest = sequence.begin();
  const cityBRequest = sequence.begin();

  assert.equal(
    isLocationRequestCurrent(
      sequence,
      cityARequest,
      { latitude: 40, longitude: 20 },
      { latitude: 40, longitude: 20 },
    ),
    false,
  );
  assert.equal(
    isLocationRequestCurrent(
      sequence,
      cityBRequest,
      { latitude: 40, longitude: 20 },
      { latitude: 40, longitude: 20 },
    ),
    true,
  );
});

test("chat payload includes the latest preference values and recommendation objects", () => {
  const recommendations = [
    { category: "Outdoor", priority: "High", action: "Stay indoors" },
  ];
  const payload = buildChatPayload(
    "What should we do?",
    {
      current: { pm2_5: 65.7, pm10: 69.4, ozone: 21.3, nitrogen_dioxide: 14.2 },
      current_units: { pm2_5: "µg/m³", pm10: "µg/m³", ozone: "µg/m³", nitrogen_dioxide: "µg/m³" },
    },
    "yes",
    "electricity",
    "family_with_children",
    recommendations,
  );

  assert.equal(payload.pm2_5, 65.7);
  assert.equal(payload.pm10, 69.4);
  assert.equal(payload.has_air_purifier, true);
  assert.equal(payload.cooking_fuel, "electricity");
  assert.equal(payload.pm2_5_unit, "µg/m³");
  assert.deepEqual(payload.recommendations, recommendations);
});

test("partial readings and missing units remain null", () => {
  const payload = buildChatPayload(
    "What is available?",
    { current: { pm2_5: null, pm10: null, ozone: 30, nitrogen_dioxide: null } },
    "no",
    "lpg",
    "family_with_children",
    [],
  );

  assert.equal(payload.pm2_5, null);
  assert.equal(payload.pm10, null);
  assert.equal(payload.ozone, 30);
  assert.equal(payload.ozone_unit, null);
  assert.equal(payload.nitrogen_dioxide, null);
});

test("chat history is bounded, chronological, and excludes invalid entries", () => {
  const history = [
    { role: "user" as const, content: "first" },
    { role: "assistant" as const, content: "second" },
    { role: "system" as never, content: "not allowed" },
    { role: "user" as const, content: "   " },
  ];
  history.push(
    ...Array.from({ length: 25 }, (_, index) => ({
      role: (index % 2 === 0 ? "user" : "assistant") as "user" | "assistant",
      content: `turn ${index}`,
    })),
  );

  const payload = buildChatPayload(
    "latest",
    { current: { pm2_5: 65.7, pm10: 69.4, ozone: 21.3, nitrogen_dioxide: 14.2 } },
    "no",
    "lpg",
    "family_with_children",
    [],
    history,
  );

  assert.equal(payload.history.length, 20);
  assert.equal(payload.history[0].content, "turn 5");
  assert.equal(payload.history.at(-1)?.content, "turn 24");
  assert.equal(payload.history.some((item) => item.role === "system"), false);
  assert.equal(payload.history.some((item) => item.content.trim() === ""), false);
});

test("failed or superseded refresh UI is guarded by clearing old advice", async () => {
  const appSource = await readFile(
    new URL("../src/App.tsx", import.meta.url),
    "utf8",
  );

  assert.match(appSource, /setIndoorAdvice\(\[\]\)/);
  assert.match(appSource, /setIndoorError\(/);
  assert.match(appSource, /indoorRequestSequence\.current\.isCurrent/);
  assert.match(appSource, /\[data, hasPurifier, cookingFuel\]/);
  assert.match(appSource, /Boolean\(indoorError\)/);
  assert.match(appSource, /setChatMessages\(\[\]\)/);
});

test("city search is sequenced and validated before results are shown", async () => {
  const appSource = await readFile(
    new URL("../src/App.tsx", import.meta.url),
    "utf8",
  );

  assert.match(appSource, /searchRequestSequence\.current\.begin/);
  assert.match(appSource, /searchRequestSequence\.current\.isCurrent/);
  assert.match(appSource, /searchRequestAbort\.current\?\.abort/);
  assert.match(appSource, /Location search returned invalid data/);
});
