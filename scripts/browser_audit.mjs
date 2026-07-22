import { spawn } from "node:child_process";
import { mkdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const dashboardUrl = process.argv[2] ?? "http://127.0.0.1:5173/";
const chrome = process.env.AIRVIEW_CHROME_PATH ?? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const debugPort = 9333;
const profile = resolve(join(tmpdir(), `airview-browser-audit-${Date.now()}`));
const reportDirectory = resolve("outputs/reports");
await mkdir(profile, { recursive: true });
await mkdir(reportDirectory, { recursive: true });

const child = spawn(chrome, [
  "--headless=new",
  "--disable-gpu",
  "--no-first-run",
  "--no-default-browser-check",
  `--remote-debugging-port=${debugPort}`,
  `--user-data-dir=${profile}`,
  "about:blank",
], { stdio: "ignore", windowsHide: true });

const delay = (milliseconds) => new Promise((resolveDelay) => setTimeout(resolveDelay, milliseconds));
async function retry(callback, timeout = 15000) {
  const deadline = Date.now() + timeout;
  let lastError;
  while (Date.now() < deadline) {
    try { return await callback(); } catch (error) { lastError = error; await delay(150); }
  }
  throw lastError ?? new Error("Timed out");
}

let socket;
try {
  await retry(async () => {
    const response = await fetch(`http://127.0.0.1:${debugPort}/json/version`);
    if (!response.ok) throw new Error("Chrome debugging endpoint is not ready");
  });
  const targetResponse = await fetch(
    `http://127.0.0.1:${debugPort}/json/new?${encodeURIComponent(dashboardUrl)}`,
    { method: "PUT" },
  );
  const target = await targetResponse.json();
  socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolveOpen, rejectOpen) => {
    socket.addEventListener("open", resolveOpen, { once: true });
    socket.addEventListener("error", rejectOpen, { once: true });
  });

  let messageId = 0;
  const pending = new Map();
  const consoleErrors = [];
  const failedRequests = [];
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (message.id && pending.has(message.id)) {
      const { resolve: resolveMessage, reject } = pending.get(message.id);
      pending.delete(message.id);
      if (message.error) reject(new Error(message.error.message));
      else resolveMessage(message.result);
      return;
    }
    if (message.method === "Runtime.exceptionThrown") {
      consoleErrors.push(message.params.exceptionDetails?.text ?? "Unhandled browser exception");
    }
    if (message.method === "Runtime.consoleAPICalled" && message.params.type === "error") {
      consoleErrors.push(message.params.args.map((argument) => argument.value ?? argument.description).join(" "));
    }
    if (message.method === "Network.responseReceived") {
      const { response } = message.params;
      if (response.url.includes("/api/") && response.status >= 400) {
        failedRequests.push(`${response.status} ${response.url}`);
      }
    }
    if (message.method === "Network.loadingFailed") {
      const url = message.params.blockedReason ?? message.params.errorText;
      if (!String(url).includes("ERR_ABORTED")) failedRequests.push(String(url));
    }
  });

  function command(method, params = {}) {
    const id = ++messageId;
    return new Promise((resolveMessage, reject) => {
      pending.set(id, { resolve: resolveMessage, reject });
      socket.send(JSON.stringify({ id, method, params }));
    });
  }
  async function evaluate(expression) {
    const result = await command("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
    if (result.exceptionDetails) {
      throw new Error(result.exceptionDetails.exception?.description ?? result.exceptionDetails.text);
    }
    return result.result.value;
  }
  async function waitFor(expression, timeout = 45000) {
    return retry(async () => {
      const value = await evaluate(expression);
      if (!value) throw new Error(`Condition not met: ${expression}`);
      return value;
    }, timeout);
  }
  async function selectControl(index, value) {
    await waitFor(`document.querySelectorAll('.control-bar select').length > ${index}`, 10000);
    const selected = await retry(() => evaluate(`(() => { const element = document.querySelectorAll('.control-bar select')[${index}]; if (!element) throw new Error('Control unavailable'); const option = Array.from(element.options).find((item) => item.value === ${JSON.stringify(value)}); if (!option) return { value: null, options: Array.from(element.options).map((item) => item.value) }; element.selectedIndex = option.index; element.dispatchEvent(new Event('input', { bubbles: true })); element.dispatchEvent(new Event('change', { bubbles: true })); return { value: element.value, options: [] }; })()`), 5000);
    if (selected.value !== value) throw new Error(`Control ${index} does not offer ${value}: ${selected.options.join(", ")}`);
    await delay(100);
  }
  async function waitForHeader(name) {
    await waitFor(`document.querySelector('main h1')?.textContent?.trim() === ${JSON.stringify(name)}`, 8000);
    await waitFor(`!document.querySelector('[data-testid="current-card"] [aria-busy="true"]')`, 60000);
  }
  async function searchCity(name) {
    try {
      await waitFor("Boolean(document.querySelector('#city-search-input'))", 10000);
    } catch (error) {
      const diagnostic = await evaluate("({ url: location.href, title: document.title, body: document.body.innerText.slice(0, 500) })");
      throw new Error(`${error.message}; console=${consoleErrors.join(" | ")}; page=${JSON.stringify(diagnostic)}`);
    }
    await evaluate("(() => { const input = document.querySelector('#city-search-input'); input.focus(); input.select(); return true; })()");
    await command("Input.insertText", { text: name });
    await waitFor("!document.querySelector('.city-search form button').disabled");
    await evaluate("document.querySelector('#city-search-input').form.requestSubmit(); true");
    await waitFor(`Array.from(document.querySelectorAll('.city-search li button')).some((button) => button.textContent.includes(${JSON.stringify(name)}))`, 30000);
    await evaluate(`(() => { const button = Array.from(document.querySelectorAll('.city-search li button')).find((item) => item.textContent.includes(${JSON.stringify(name)})); button.click(); return true; })()`);
    await waitForHeader(name);
  }
  async function activateCityByName(name) {
    await waitFor(`Array.from(document.querySelectorAll('.control-bar select')[0].options).some((item) => item.textContent.trim() === ${JSON.stringify(name)})`, 10000);
    const value = await evaluate(`Array.from(document.querySelectorAll('.control-bar select')[0].options).find((item) => item.textContent.trim() === ${JSON.stringify(name)}).value`);
    await selectControl(0, value);
  }
  async function selectCityByName(name) {
    await activateCityByName(name);
    await waitForHeader(name);
  }
  async function captureMapState(name) {
    await waitFor("document.querySelector('[data-grid-cell-count] .leaflet-container')?.dataset.mapCityId", 60000);
    return evaluate(`(() => { const frame = document.querySelector('[data-grid-cell-count]'); const map = frame.querySelector('.leaflet-container'); const expectedGridCells = Number(frame.dataset.gridCellCount); const gridPaths = frame.querySelectorAll('.airview-grid-cell').length; const stationPaths = frame.querySelectorAll('.airview-station-marker').length; const firmsPaths = frame.querySelectorAll('.airview-firms-marker').length; return { city: ${JSON.stringify(name)}, renderedCity: frame.dataset.cityName, cityNameMatches: frame.dataset.cityName === ${JSON.stringify(name)}, cityId: map.dataset.mapCityId, cityIdMatchesFrame: map.dataset.mapCityId === frame.dataset.cityId, mapCenter: map.dataset.mapCenter, snapshotId: frame.dataset.snapshotId, expectedGridCells, gridPaths, stationPaths, firmsPaths, totalOperationalPaths: gridPaths + stationPaths + firmsPaths, allLeafletInteractivePaths: frame.querySelectorAll('.leaflet-interactive').length, activeGridMatchesMetadata: gridPaths === expectedGridCells }; })()`);
  }
  async function captureDecisionContent(name) {
    try {
      await waitFor("document.querySelector('[data-testid=\"source-screening\"]') && document.querySelector('[data-testid=\"citizen-advisory-panel\"]') && document.querySelector('[data-testid=\"forecast-card\"]')?.dataset.snapshotId", 60000);
    } catch (error) {
      const diagnostic = await evaluate("({ header: document.querySelector('main h1')?.textContent, forecast: document.querySelector('[data-testid=\"forecast-card\"]')?.innerText, sourcePanel: Array.from(document.querySelectorAll('section')).find((item) => item.textContent.includes('Likely contributing context'))?.innerText, advisoryPanel: Array.from(document.querySelectorAll('section')).find((item) => item.textContent.includes('Citizen advisory'))?.innerText })");
      throw new Error(`${error.message}; decision-panel diagnostic=${JSON.stringify(diagnostic)}`);
    }
    return evaluate(`(() => {
      const sourcePanel = document.querySelector('[data-testid="source-screening"]');
      const actionPanel = document.querySelector('[data-testid="action-queue-panel"]');
      const advisoryPanel = document.querySelector('[data-testid="citizen-advisory-panel"]');
      const advisory = document.querySelector('[data-testid="citizen-advisory"]');
      const forecast = document.querySelector('[data-testid="forecast-card"]');
      const sources = Array.from(sourcePanel.querySelectorAll('.source-evidence')).map((item) => ({ sourceId: item.querySelector('strong')?.textContent?.trim(), score: item.dataset.score === 'unavailable' ? null : Number(item.dataset.score), strength: item.dataset.evidenceStrength }));
      const actions = Array.from(document.querySelectorAll('.action-card')).map((item) => ({ sourceId: item.dataset.sourceId, evidenceScore: Number(item.dataset.evidenceScore), title: item.querySelector('.action-heading strong')?.textContent?.trim(), text: item.querySelector(':scope > p:not(.action-source)')?.textContent?.trim() }));
      const visibleText = [sourcePanel.innerText, actionPanel.innerText, advisoryPanel.innerText].join(' ');
      const actionKeys = actions.map((item) => item.sourceId);
      const actionCopy = actions.map((item) => item.text);
      return {
        city: ${JSON.stringify(name)},
        pollutant: document.querySelectorAll('.control-bar select')[1].value,
        horizon: Number(document.querySelectorAll('.control-bar select')[2].value),
        sources,
        actions,
        advisoryAvailable: Boolean(advisory),
        snapshots: { forecast: forecast.dataset.snapshotId, sources: sourcePanel.dataset.snapshotId, actions: actionPanel.dataset.snapshotId, advisory: advisoryPanel.dataset.snapshotId },
        snapshotAligned: [sourcePanel.dataset.snapshotId, actionPanel.dataset.snapshotId, advisoryPanel.dataset.snapshotId].every((value) => value === forecast.dataset.snapshotId),
        categoryAligned: advisory ? advisory.dataset.category === forecast.dataset.category : !forecast.dataset.category && advisoryPanel.dataset.status === 'unavailable',
        allActionsSignificant: actions.every((item) => item.evidenceScore >= 25),
        uniqueActionSources: new Set(actionKeys).size === actionKeys.length,
        uniqueActionCopy: new Set(actionCopy).size === actionCopy.length,
        forbiddenVisibleWording: ['indicator', 'unclassified', 'sensitivity', 'Influence indicators rank supporting context', 'Public-information guidance based on a model forecast'].filter((value) => visibleText.toLowerCase().includes(value.toLowerCase())),
      };
    })()`);
  }

  await command("Page.enable");
  await command("Runtime.enable");
  await command("Network.enable");
  await command("Emulation.setDeviceMetricsOverride", { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
  await waitFor("document.querySelector('main h1')?.textContent?.trim() === 'Delhi NCR'", 30000);
  const progressiveSkeletonObserved = await evaluate("document.querySelectorAll('[aria-busy=\"true\"]').length > 0");
  await waitFor("!document.querySelector('[data-testid=\"current-card\"] [aria-busy=\"true\"]')", 60000);

  await searchCity("Mysuru");
  await searchCity("Jaipur");
  await searchCity("Pune");
  await selectControl(0, "delhi-ncr");
  await waitForHeader("Delhi NCR");

  const testedCitySequence = ["Delhi NCR", "Ludhiana", "Mysuru", "Jaipur", "Delhi NCR"];
  const mapLayerCounts = [await captureMapState("Delhi NCR")];
  for (const name of testedCitySequence.slice(1)) {
    await selectCityByName(name);
    mapLayerCounts.push(await captureMapState(name));
  }
  const citySnapshots = mapLayerCounts.map((item) => item.snapshotId);

  await selectControl(1, "pm10");
  await waitFor("document.querySelector('main header')?.textContent?.includes('PM10')");
  for (const horizon of ["24", "48", "72"]) {
    await selectControl(2, horizon);
    await waitFor(`document.querySelector('main header')?.textContent?.includes('next ${horizon} hours')`);
    await waitFor("!document.querySelector('[data-testid=\"forecast-card\"] [aria-busy=\"true\"]')", 60000);
  }

  const rapidSwitchSequence = ["Agra", "Amritsar", "Ludhiana", "Jaipur", "Delhi NCR"];
  for (const name of rapidSwitchSequence) {
    await activateCityByName(name);
  }
  await waitForHeader("Delhi NCR");
  await waitFor("document.querySelector('.leaflet-container') && document.querySelectorAll('.leaflet-interactive').length > 1", 60000);
  const rapidSwitchFinalMap = await captureMapState("Delhi NCR");

  await selectControl(1, "pm2_5");
  await selectControl(2, "24");
  const contentCitySequence = ["Ludhiana", "Delhi NCR", "Agra", "Amritsar", "Lucknow", "Mysuru", "Jaipur"];
  const contentScenarios = [];
  for (const name of contentCitySequence) {
    await selectCityByName(name);
    contentScenarios.push(await captureDecisionContent(name));
    if (name === "Ludhiana") {
      await evaluate("document.querySelector('[data-testid=\"source-screening\"]').scrollIntoView({ block: 'center' }); true");
      await delay(250);
      const sourceScreenshot = await command("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
      await writeFile(join(reportDirectory, "airview-content-source-actions.png"), Buffer.from(sourceScreenshot.data, "base64"));
      await evaluate("document.querySelector('[data-testid=\"action-queue-panel\"]')?.scrollIntoView({ block: 'center' }); true");
      await delay(250);
      const actionsScreenshot = await command("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
      await writeFile(join(reportDirectory, "airview-content-actions.png"), Buffer.from(actionsScreenshot.data, "base64"));
      await evaluate("document.querySelector('[data-testid=\"citizen-advisory-panel\"]').scrollIntoView({ block: 'center' }); true");
      await delay(250);
      const advisoryScreenshot = await command("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
      await writeFile(join(reportDirectory, "airview-content-advisory.png"), Buffer.from(advisoryScreenshot.data, "base64"));
    }
  }
  await selectCityByName("Ludhiana");
  for (const pollutantValue of ["pm2_5", "pm10"]) {
    await selectControl(1, pollutantValue);
    for (const horizonValue of ["24", "48", "72"]) {
      await selectControl(2, horizonValue);
      contentScenarios.push(await captureDecisionContent("Ludhiana"));
    }
  }

  const allSourceScores = contentScenarios.flatMap((scenario) => scenario.sources.map((source) => source.score)).filter((score) => score != null);
  const sourceScoreBandsCovered = {
    zero: allSourceScores.some((score) => score === 0),
    medium: allSourceScores.some((score) => score >= 25 && score < 50),
    high: allSourceScores.some((score) => score >= 50),
  };
  const contentConsistencyClean = contentScenarios.every((scenario) => scenario.snapshotAligned && scenario.categoryAligned && scenario.allActionsSignificant && scenario.uniqueActionSources && scenario.uniqueActionCopy && scenario.forbiddenVisibleWording.length === 0);

  await evaluate("document.querySelector('[aria-label=\"Open Ask AirView\"]')?.click(); true");
  await waitFor("Boolean(document.querySelector('[role=\"dialog\"][aria-label=\"Ask AirView\"]'))");
  await waitFor("Array.from(document.querySelectorAll('.ask-airview-system')).some((item) => item.textContent.includes('unavailable on this deployment'))");
  const copilotInitialContext = await evaluate("document.querySelector('.ask-airview-context')?.textContent?.trim()");
  const copilotUnavailableProfessional = await evaluate("Array.from(document.querySelectorAll('.ask-airview-system')).some((item) => item.textContent.trim() === 'Ask AirView is unavailable on this deployment.')");
  const copilotKeyLeakage = await evaluate("/GEMINI_API_KEY|AIza[0-9A-Za-z_-]{20,}|x-goog-api-key/i.test(document.querySelector('[role=\"dialog\"]')?.textContent ?? '')");
  await selectCityByName("Delhi NCR");
  await selectControl(1, "pm2_5");
  await selectControl(2, "24");
  await waitFor("document.querySelector('.ask-airview-context')?.textContent?.includes('Delhi NCR · PM2.5 · Next 24 hours')");
  await selectControl(2, "48");
  await waitFor("document.querySelector('.ask-airview-context')?.textContent?.includes('Next 48 hours')");
  await selectControl(2, "72");
  await waitFor("document.querySelector('.ask-airview-context')?.textContent?.includes('Next 72 hours')");
  await selectCityByName("Mysuru");
  await waitFor("document.querySelector('.ask-airview-context')?.textContent?.includes('Mysuru · PM2.5 · Next 72 hours')");
  const copilotContextAfterSwitch = await evaluate("document.querySelector('.ask-airview-context')?.textContent?.trim()");
  const copilotContextMessage = await evaluate("Array.from(document.querySelectorAll('.ask-airview-system')).some((item) => item.textContent.includes('Context updated to Mysuru'))");
  const copilotDesktop = await command("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  await writeFile(join(reportDirectory, "ask-airview-desktop.png"), Buffer.from(copilotDesktop.data, "base64"));
  await command("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  await delay(250);
  const copilotMobileLayout = await evaluate("getComputedStyle(document.querySelector('.ask-airview-panel')).width === '390px' && document.documentElement.scrollWidth === document.documentElement.clientWidth");
  const copilotMobile = await command("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  await writeFile(join(reportDirectory, "ask-airview-mobile.png"), Buffer.from(copilotMobile.data, "base64"));
  await command("Emulation.setDeviceMetricsOverride", { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
  await command("Input.dispatchKeyEvent", { type: "keyDown", key: "Escape", code: "Escape" });
  await command("Input.dispatchKeyEvent", { type: "keyUp", key: "Escape", code: "Escape" });
  await waitFor("!document.querySelector('[role=\"dialog\"][aria-label=\"Ask AirView\"]')");
  const copilotEscapeClosed = await evaluate("!document.querySelector('[role=\"dialog\"][aria-label=\"Ask AirView\"]')");

  const categoryLegendLabels = await evaluate("Array.from(document.querySelectorAll('[aria-label=\"Current air-quality category colour legend\"] span')).map((item) => item.textContent.trim()).filter((value) => ['Good', 'Satisfactory', 'Moderate', 'Poor', 'Very Poor', 'Severe'].includes(value))");
  const gridFillColours = await evaluate("Array.from(new Set(Array.from(document.querySelectorAll('.leaflet-overlay-pane path[fill]')).map((item) => item.getAttribute('fill')).filter((value) => value && value !== 'none')))");
  await evaluate("document.querySelector('.leaflet-container').scrollIntoView({ block: 'center' }); true");
  await delay(300);
  const mapScreenshot = await command("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  await writeFile(join(reportDirectory, "airview-final-map.png"), Buffer.from(mapScreenshot.data, "base64"));
  await evaluate("scrollTo(0, 0); true");
  await delay(200);

  const desktop = await command("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  await writeFile(join(reportDirectory, "airview-final-desktop.png"), Buffer.from(desktop.data, "base64"));
  await command("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  await delay(300);
  const mobileOverflow = await evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth");
  const mobile = await command("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  await writeFile(join(reportDirectory, "airview-final-mobile.png"), Buffer.from(mobile.data, "base64"));

  const distinctSequenceSnapshots = new Set(citySnapshots).size;
  const mapLayersClean = [...mapLayerCounts, rapidSwitchFinalMap].every((item) => item.activeGridMatchesMetadata && item.cityIdMatchesFrame && item.cityNameMatches);
  const result = {
    status: consoleErrors.length || failedRequests.length || mobileOverflow || distinctSequenceSnapshots !== 4 || !mapLayersClean || categoryLegendLabels.length !== 6 || gridFillColours.length === 0 || !contentConsistencyClean || !Object.values(sourceScoreBandsCovered).every(Boolean) || !copilotUnavailableProfessional || copilotKeyLeakage || !copilotContextMessage || !copilotMobileLayout || !copilotEscapeClosed ? "failed" : "passed",
    progressiveSkeletonObserved,
    testedCitySequence,
    rapidSwitchSequence,
    searchedCities: ["Mysuru", "Jaipur", "Pune"],
    finalCity: await evaluate("document.querySelector('main h1')?.textContent?.trim()"),
    finalPollutantAndHorizon: await evaluate("document.querySelector('main header')?.textContent"),
    distinctSequenceSnapshots,
    mapLayersClean,
    mapLayerCounts,
    rapidSwitchFinalMap,
    mapPaths: await evaluate("document.querySelectorAll('.leaflet-interactive').length"),
    categoryLegendLabels,
    gridFillColours,
    contentCitySequence,
    contentScenarios,
    sourceScoreBandsCovered,
    contentConsistencyClean,
    copilot: {
      initialContext: copilotInitialContext,
      contextAfterSwitch: copilotContextAfterSwitch,
      unavailableProfessional: copilotUnavailableProfessional,
      keyLeakage: copilotKeyLeakage,
      contextMessage: copilotContextMessage,
      mobileLayout: copilotMobileLayout,
      escapeClosed: copilotEscapeClosed,
    },
    mobileOverflow,
    consoleErrors,
    failedRequests,
  };
  await writeFile(join(reportDirectory, "browser_audit.json"), JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result, null, 2));
  if (result.status !== "passed") process.exitCode = 1;
} finally {
  if (socket?.readyState === WebSocket.OPEN) socket.close();
  child.kill();
  await delay(500);
  const temporaryRoot = resolve(tmpdir());
  if (profile.startsWith(`${temporaryRoot}\\`) || profile.startsWith(`${temporaryRoot}/`)) {
    try {
      await retry(() => rm(profile, { recursive: true, force: true }), 5000);
    } catch {
      console.warn("The temporary browser profile is still locked and can be removed after Chrome exits.");
    }
  }
}
