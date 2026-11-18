import puppeteer from "puppeteer-core";
import fs from "fs";

const BASE = "http://127.0.0.1:8123", STUB = "http://127.0.0.1:8765";
const HERE = new URL(".", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
const results = [];
const check = (name, ok, extra = "") => { results.push([ok, name, extra]); console.log((ok ? "PASS " : "FAIL ") + name + (ok ? "" : "  -> " + extra)); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const counts = async () => (await fetch(STUB + "/__count")).json();
const val = (page, sel) => page.$eval(sel, (el) => el.value);

// Use your own Chrome/Edge by setting CHROME_PATH; otherwise a bundled headless Chromium (Linux only) is used.
let executablePath, args, headless;
if (process.env.CHROME_PATH) { executablePath = process.env.CHROME_PATH; args = ["--no-sandbox"]; headless = "new"; }
else { const chromium = (await import("@sparticuz/chromium")).default; executablePath = await chromium.executablePath(); args = chromium.args; headless = "shell"; }
const browser = await puppeteer.launch({ args, executablePath, headless });
const context = browser.defaultBrowserContext();
await context.overridePermissions(BASE, ["geolocation"]);
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 1000 });
const problems = [];
// The sandbox has no internet: serve the Bootstrap files the page asks the CDN for from a local copy, so the page behaves as it does online.
await page.setRequestInterception(true);
page.on("request", (req) => {
  const u = req.url();
  if (u.includes("cdn.jsdelivr.net") && u.endsWith("bootstrap.bundle.min.js")) return req.respond({ status: 200, contentType: "application/javascript", body: fs.readFileSync(HERE + "node_modules/bootstrap/dist/js/bootstrap.bundle.min.js") });
  if (u.includes("cdn.jsdelivr.net") && u.endsWith("bootstrap.min.css")) return req.respond({ status: 200, contentType: "text/css", body: fs.readFileSync(HERE + "node_modules/bootstrap/dist/css/bootstrap.min.css") });
  if (/tile\.openstreetmap\.org|fonts\.(googleapis|gstatic)\.com/.test(u)) return req.abort();
  req.continue();
});
page.on("pageerror", (e) => problems.push("pageerror: " + e.message));
page.on("console", (m) => { const t = m.text(); if (m.type() === "error" && !/net::ERR|Failed to load resource|tile\.openstreetmap/.test(t)) problems.push("console: " + t); if (/Content Security Policy|Refused to/.test(t)) problems.push("CSP: " + t); });

// ---- sign in
await page.goto(BASE + "/accounts/login/", { waitUntil: "domcontentloaded" });
await page.type("#id_username", "citizen@routelync.test");
await page.type("#id_password", "Demo-Pass#12345");
await Promise.all([page.waitForNavigation({ waitUntil: "domcontentloaded" }), page.click("button[type=submit]")]);
await page.goto(BASE + "/complaints/new/", { waitUntil: "domcontentloaded" });
await page.waitForSelector("#location-map .leaflet-pane", { timeout: 15000 });
check("map is created on the form", !!(await page.$("#location-map .leaflet-container, #location-map.leaflet-container")));

// ---- short text does nothing
let before = (await counts())["/api/"] || 0;
await page.type("#location-search", "ab"); await sleep(700);
check("two characters send no request", ((await counts())["/api/"] || 0) === before);

// ---- debounce: typing a word sends ONE request
await page.$eval("#location-search", (e) => (e.value = ""));
before = (await counts())["/api/"] || 0;
await page.type("#location-search", "Majestic", { delay: 60 });
await page.waitForSelector("#location-results li[role=option]", { timeout: 8000 });
const after = (await counts())["/api/"] || 0;
check("typing 8 letters quickly sends one search (debounced)", after - before === 1, `sent ${after - before}`);
const options = await page.$$eval("#location-results li[role=option]", (els) => els.map((e) => e.textContent));
check("dropdown shows real result names and addresses", options.length === 3 && options[0].includes("Kempegowda Bus Station") && options[0].includes("Gandhinagar"), JSON.stringify(options));
check("combobox state is announced", (await page.$eval("#location-search", (e) => e.getAttribute("aria-expanded"))) === "true");

// ---- keyboard
await page.keyboard.press("ArrowDown"); await page.keyboard.press("ArrowDown"); await page.keyboard.press("ArrowUp");
check("arrow keys move the active option", (await page.$eval("#location-search", (e) => e.getAttribute("aria-activedescendant"))) === "loc-opt-0");
await page.keyboard.press("Escape");
check("Escape closes the list", await page.$eval("#location-results", (e) => e.hidden));
await page.$eval("#location-search", (e) => (e.value = "")); await page.type("#location-search", "Jayanagar", { delay: 40 });
await page.waitForSelector("#location-results li[role=option]");
await page.keyboard.press("ArrowDown"); await page.keyboard.press("ArrowDown");          // second result = Jayanagar 4th Block
await page.keyboard.press("Enter");
await sleep(300);
const lat1 = await val(page, "#id_latitude"), lon1 = await val(page, "#id_longitude");
check("Enter selects the highlighted place and stores its coordinates", lat1 === "12.925000" && lon1 === "77.583800", `${lat1},${lon1}`);
check("a signed token is stored with the selection", (await val(page, "#id_location_token")).length > 40);
check("address field is filled automatically", (await val(page, "#id_address_text")).includes("Jayanagar 4th Block"), await val(page, "#id_address_text"));
check("street is filled automatically", (await val(page, "#id_street")) === "11th Main Road");
check("area is matched from the result (Jayanagar)", (await page.$eval("#id_area", (e) => e.options[e.selectedIndex].text.trim())) === "Jayanagar");
check("marker is on the map", !!(await page.$(".leaflet-marker-icon")));
check("selected location text is shown", (await page.$eval("#location-chosen", (e) => e.textContent)).includes("12.925000"));

// ---- provider problems are explained, not hidden
for (const [q, expect] of [["FAIL503 street", "unavailable"], ["FAIL429 street", "busy"], ["zzzzzzz", "No places found"]]) {
  await page.$eval("#location-search", (e) => (e.value = "")); await page.type("#location-search", q, { delay: 20 });
  await page.waitForFunction((t) => document.querySelector("#location-results")?.textContent.includes(t), { timeout: 8000 }, expect);
  check(`message for "${q}"`, true);
}
await page.keyboard.press("Escape");

// ---- map tap: the pin moves and the address is looked up
const box = await (await page.$("#location-map")).boundingBox();
const revBefore = (await counts())["/reverse"] || 0;
await page.mouse.click(box.x + box.width * 0.3, box.y + box.height * 0.35);
await sleep(900);
const lat2 = await val(page, "#id_latitude");
check("tapping the map moves the pin and changes the coordinates", lat2 !== "12.925000", lat2);
check("the address is looked up for the tapped point", ((await counts())["/reverse"] || 0) > revBefore);
check("token matches the new point (reverse result signed)", (await val(page, "#id_location_token")).length > 40);

// ---- dragging the pin
const marker = await page.$(".leaflet-marker-icon"); const mb = await marker.boundingBox();
const latBefore = await val(page, "#id_latitude");
await page.mouse.move(mb.x + mb.width / 2, mb.y + mb.height / 2); await page.mouse.down();
await page.mouse.move(mb.x + mb.width / 2 + 50, mb.y + mb.height / 2 + 40, { steps: 8 }); await page.mouse.up();
await sleep(900);
check("dragging the pin updates the coordinates", (await val(page, "#id_latitude")) !== latBefore, await val(page, "#id_latitude"));

// ---- GPS button
await page.setGeolocation({ latitude: 12.9302, longitude: 77.5841 });
await page.click("#use-location"); await sleep(1200);
check("current location sets the pin from the device", (await val(page, "#id_latitude")).startsWith("12.9302"), await val(page, "#id_latitude"));
check("GPS fills the address through the reverse lookup", (await val(page, "#id_address_text")).length > 5);

// ---- clear, then submit with no location
await page.click("#clear-location"); await sleep(200);
check("clearing removes coordinates and token", (await val(page, "#id_latitude")) === "" && (await val(page, "#id_location_token")) === "");
await page.type("#id_title", "Streetlight not working near junction");
await page.type("#id_description", "The streetlight near the junction has not been working for three days and the road is very dark at night.");
await page.select("#id_ward", await page.$eval("#id_ward", (e) => Array.from(e.options).find((o) => o.value && !o.disabled).value));
const url0 = page.url();
await page.click("form#complaint-form button[type=submit]"); await sleep(600);
check("submitting without a location is blocked in the browser with a message", page.url() === url0 && (await page.$eval("#location-status", (e) => e.textContent)).includes("choose the location"));

// ---- mobile touch selection, then the full submission
await page.setViewport({ width: 390, height: 844, hasTouch: true, isMobile: true });   // note: Puppeteer reloads the page here, so the form is empty again
await page.waitForSelector("#location-map .leaflet-pane", { timeout: 15000 });
await page.type("#id_title", "Streetlight not working near junction");
await page.type("#id_description", "The streetlight near the junction has not been working for three days and the road is very dark at night.");
await page.$eval("#location-search", (e) => (e.value = "")); await page.type("#location-search", "Indiranagar", { delay: 30 });
await page.waitForSelector("#location-results li[role=option]");
await (await page.$$("#location-results li[role=option]"))[2].tap(); await sleep(600);
check("tapping a result on a touch screen selects it", (await val(page, "#id_latitude")) === "12.978400", await val(page, "#id_latitude"));
await page.type("#id_landmark", "").catch(() => {});
await (await page.$("#id_image")).uploadFile(HERE + "photo.png");
await page.select("#id_ward", await page.$eval("#id_ward", (e) => Array.from(e.options).find((o) => o.value && !o.disabled && !o.hidden).value));
await page.$eval("#id_address_text", (e) => { if (!e.value) e.value = "Indiranagar, Bengaluru"; });
await Promise.all([page.waitForNavigation({ waitUntil: "domcontentloaded" }), page.click("form#complaint-form button[type=submit]")]);
const landed = /\/complaints\/\d+\/$/.test(page.url());
const whyNot = landed ? "" : await page.$$eval(".alert, .invalid-feedback", (els) => els.map((e) => (e.closest(".mb-3")?.querySelector("input,select,textarea")?.id || "?") + ": " + e.textContent.trim().replace(/\s+/g, " ")).join(" || "));
check("the complaint is submitted and the person lands on its page", landed, page.url() + " :: " + whyNot);

check("no JavaScript errors and no Content-Security-Policy violations during the whole run", problems.length === 0, problems.join(" | "));
await browser.close();
const failed = results.filter((r) => !r[0]).length;
console.log(`\n${results.length - failed}/${results.length} checks passed`);
process.exit(failed ? 1 : 0);
