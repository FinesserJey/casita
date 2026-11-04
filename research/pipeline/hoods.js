/* hoods.js — Chicago search areas and their neighborhood filters. */
const HOODS = (() => {
  "use strict";

  const ALIASES = new Map([
    ["near north side", "River North"],
    ["river north chicago", "River North"],
    ["west loop gate", "West Loop"],
    ["fulton market", "Fulton Market"],
    ["south loop", "South Loop"],
    ["printer's row", "South Loop"],
  ]);
  const canonical = (name) => ALIASES.get((name || "").trim().toLowerCase()) || (name || "").trim();

  const NOTES = {
    "River North": "A dense downtown area with CTA Red, Brown and Purple Line access, restaurants, galleries and shopping.",
    "West Loop": "West of the Loop, with CTA Green and Pink Line access and a dense restaurant scene.",
    "Fulton Market": "A mixed-use part of the West Loop with restaurants, offices, galleries and Green/Pink Line access.",
    "South Loop": "South of downtown, served by CTA Red, Green and Orange Lines and close to the lakefront and Museum Campus.",
  };

  const DISTRICTS = [
    ["North Side", "pin", ["River North"]],
    ["West Side", "pin", ["West Loop", "Fulton Market"]],
    ["South Side", "pin", ["South Loop"]],
  ];

  function areaOf(a) {
    return canonical(a.hood || "Chicago");
  }

  function districtOf(area) {
    const name = canonical(area);
    const hit = DISTRICTS.find(([, , list]) => list.includes(name));
    return hit ? hit[0] : "Elsewhere";
  }

  function districts(all) {
    const counts = new Map();
    for (const a of all) {
      const district = districtOf(areaOf(a));
      counts.set(district, (counts.get(district) || 0) + 1);
    }
    return DISTRICTS.map(([name, icon]) => ({ name, icon, n: counts.get(name) || 0 }))
      .filter((district) => district.n >= 5)
      .concat(counts.get("Elsewhere") >= 5
        ? [{ name: "Elsewhere", icon: "pin", n: counts.get("Elsewhere") }] : []);
  }

  function areasIn(all, district) {
    const counts = new Map();
    for (const a of all) {
      const area = areaOf(a);
      if (districtOf(area) !== district) continue;
      counts.set(area, (counts.get(area) || 0) + 1);
    }
    return [...counts.entries()].filter(([, count]) => count >= 3)
      .sort((a, b) => b[1] - a[1]).slice(0, 5);
  }

  function index(all) {
    const counts = new Map();
    for (const a of all) {
      const area = areaOf(a);
      counts.set(area, (counts.get(area) || 0) + 1);
    }
    return [...counts.entries()].filter(([, count]) => count >= 3)
      .sort((a, b) => b[1] - a[1]);
  }

  const noteFor = (area) => NOTES[canonical(area)] || null;
  const splitNote = () => null;

  return { areaOf, noteFor, splitNote, index, districts, areasIn, districtOf,
           SPLITS: {}, NOTES };
})();
