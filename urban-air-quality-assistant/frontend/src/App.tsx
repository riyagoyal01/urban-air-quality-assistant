
import { useEffect, useRef, useState } from "react";
import {
  buildChatPayload,
  buildIndoorAdvicePayload,
  createRequestSequence,
} from "./household";

const API = (import.meta.env.VITE_API_BASE_URL as string | undefined)
  || "http://127.0.0.1:8000";

const pollutants = [
  { key: "pm2_5", label: "PM2.5" },
  { key: "pm10", label: "PM10" },
  { key: "nitrogen_dioxide", label: "Nitrogen Dioxide" },
  { key: "ozone", label: "Ozone" },
  { key: "sulphur_dioxide", label: "Sulphur Dioxide" },
  { key: "carbon_monoxide", label: "Carbon Monoxide" },
];

type Place = {
  name: string;
  admin1?: string;
  country?: string;
  latitude: number;
  longitude: number;
};

type Recommendation = {
  category: string;
  priority: string;
  action: string;
  reason: string;
  alternative: string;
};

type IndoorAdvice = {
  title: string;
  action: string;
  reason: string;
};

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

type AirQualityData = {
  current: Record<string, number | null>;
  current_units: Record<string, string>;
  hourly: {
    pm2_5: (number | null)[];
    time: string[];
  };
  location: {
    latitude: number;
    longitude: number;
    timezone: string | null;
  };
  model_note: string;
};

function renderInlineMarkdown(text: string) {
  const parts = text.split(/(\*\*.+?\*\*|__.+?__|(?<!\*)\*[^*\n]+?\*(?!\*)|_[^_\n]+?_|`[^`]+`)/g);

  return parts.map((part, index) => {
    if ((part.startsWith("**") && part.endsWith("**")) ||
        (part.startsWith("__") && part.endsWith("__"))) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    if ((part.startsWith("*") && part.endsWith("*")) ||
        (part.startsWith("_") && part.endsWith("_"))) {
      return <em key={index}>{part.slice(1, -1)}</em>;
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return <code key={index}>{part.slice(1, -1)}</code>;
    }
    return part;
  });
}

export function AssistantMarkdown({ content }: { content: string }) {
  const lines = content
    .replace(/\\([\\`*_{}[\]()#+.!|>~-])/g, "$1")
    .split(/\r?\n/);
  const blocks = [];
  let index = 0;

  const cells = (line: string) =>
    line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());
  const isTableDivider = (line: string) =>
    /^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$/.test(line);
  const isBlockStart = (line: string) =>
    /^#{1,6}\s/.test(line) ||
    /^\s*([-*+]|\d+[.)])\s+/.test(line) ||
    /^\s*(?:(?:\*\s*){3,}|(?:-\s*){3,}|(?:_\s*){3,})$/.test(line) ||
    (line.includes("|") && index + 1 < lines.length && isTableDivider(lines[index + 1]));

  while (index < lines.length) {
    const line = lines[index].trim();
    if (!line) {
      index += 1;
      continue;
    }

    const heading = /^(#{1,6})\s+(.+)$/.exec(line);
    if (heading) {
      const Tag = `h${heading[1].length}` as "h1" | "h2" | "h3" | "h4" | "h5" | "h6";
      blocks.push(<Tag key={index}>{renderInlineMarkdown(heading[2])}</Tag>);
      index += 1;
      continue;
    }

    if (/^(?:(?:\*\s*){3,}|(?:-\s*){3,}|(?:_\s*){3,})$/.test(line)) {
      blocks.push(<hr key={index} />);
      index += 1;
      continue;
    }

    if (line.includes("|") && index + 1 < lines.length && isTableDivider(lines[index + 1])) {
      const headers = cells(line);
      index += 2;
      const rows = [];
      while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
        rows.push(cells(lines[index]));
        index += 1;
      }
      blocks.push(
        <div key={`table-${index}`} style={{ overflowX: "auto" }}>
          <table>
            <thead>
              <tr>{headers.map((header, cellIndex) => (
                <th key={cellIndex}>{renderInlineMarkdown(header)}</th>
              ))}</tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {headers.map((_, cellIndex) => (
                    <td key={cellIndex}>{renderInlineMarkdown(row[cellIndex] ?? "")}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      continue;
    }

    const listItem = /^\s*([-*+]|\d+[.)])\s+(.+)$/.exec(lines[index]);
    if (listItem) {
      const ordered = /^\d/.test(listItem[1]);
      const items = [];
      while (index < lines.length) {
        const current = /^\s*([-*+]|\d+[.)])\s+(.+)$/.exec(lines[index]);
        if (!current || /^\d/.test(current[1]) !== ordered) break;
        items.push(renderInlineMarkdown(current[2]));
        index += 1;
      }
      const List = ordered ? "ol" : "ul";
      blocks.push(<List key={`list-${index}`}>{items.map((item, itemIndex) => (
        <li key={itemIndex}>{item}</li>
      ))}</List>);
      continue;
    }

    const paragraph = [lines[index].trim()];
    index += 1;
    while (index < lines.length && lines[index].trim() && !isBlockStart(lines[index].trim())) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    blocks.push(
      <p key={`paragraph-${index}`}>
        {paragraph.map((paragraphLine, lineIndex) => (
          <span key={lineIndex}>
            {lineIndex > 0 && <br />}
            {renderInlineMarkdown(paragraphLine)}
          </span>
        ))}
      </p>
    );
  }

  return <div>{blocks}</div>;
}

function App() {
  const household = "family_with_children";
  const [city, setCity] = useState("");
  const [hasPurifier, setHasPurifier] = useState("no");
  const [cookingFuel, setCookingFuel] = useState("lpg");
  const [locations, setLocations] = useState<Place[]>([]);
  const [selectedCity, setSelectedCity] = useState("");
  const [data, setData] = useState<AirQualityData | null>(null);
  const [recommendations, setRecommendations] =
    useState<Recommendation[]>([]);
  const [indoorAdvice, setIndoorAdvice] = useState<IndoorAdvice[]>([]);
  const [indoorLoading, setIndoorLoading] = useState(false);
  const [indoorError, setIndoorError] = useState("");
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [chatError, setChatError] = useState("");
  const [disclaimer, setDisclaimer] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const cityRequestSequence = useRef(createRequestSequence());
  const indoorRequestSequence = useRef(createRequestSequence());
  const cityRequestAbort = useRef<AbortController | null>(null);
  const searchRequestSequence = useRef(createRequestSequence());
  const searchRequestAbort = useRef<AbortController | null>(null);
  const recommendationRequestAbort = useRef<AbortController | null>(null);
  const indoorRequestAbort = useRef<AbortController | null>(null);
  const chatRequestSequence = useRef(createRequestSequence());
  const chatRequestAbort = useRef<AbortController | null>(null);
  const activeLocation = useRef<{ latitude: number; longitude: number } | null>(null);

  async function searchCity() {
    setError("");
    setLocations([]);
    searchRequestAbort.current?.abort();
    const requestSequence = searchRequestSequence.current.begin();
    const controller = new AbortController();
    searchRequestAbort.current = controller;

    if (city.trim().length < 2) {
      setError("Enter at least 2 characters.");
      return;
    }

    try {
      const response = await fetch(
        `${API}/api/search-location?name=${encodeURIComponent(city)}`,
        { signal: controller.signal }
      );

      if (!searchRequestSequence.current.isCurrent(requestSequence)) return;
      if (!response.ok) throw new Error("Location search failed.");

      const result = await response.json();
      if (!result || !Array.isArray(result.results)) {
        throw new Error("Location search returned invalid data.");
      }
      if (!searchRequestSequence.current.isCurrent(requestSequence)) return;
      setLocations(result.results || []);

      if (!result.results?.length) {
        setError("No matching cities found.");
      }
    } catch (err) {
      if (searchRequestSequence.current.isCurrent(requestSequence) &&
          !(err instanceof DOMException && err.name === "AbortError")) {
        setError(
          err instanceof Error
            ? err.message
            : "Unable to search locations."
        );
      }
    }
  }

  async function selectCity(place: Place) {
    searchRequestAbort.current?.abort();
    searchRequestSequence.current.invalidate();
    setSelectedCity(
      [place.name, place.admin1, place.country]
        .filter(Boolean)
        .join(", ")
    );

    setLocations([]);
    setCity("");

    await fetchAirQuality(place.latitude, place.longitude);
  }

  async function fetchAirQuality(latitude: number, longitude: number) {
    cityRequestAbort.current?.abort();
    recommendationRequestAbort.current?.abort();
    indoorRequestAbort.current?.abort();
    chatRequestAbort.current?.abort();
    chatRequestSequence.current.invalidate();
    indoorRequestSequence.current.invalidate();

    const requestSequence = cityRequestSequence.current.begin();
    const controller = new AbortController();
    const recommendationController = new AbortController();
    cityRequestAbort.current = controller;
    recommendationRequestAbort.current = recommendationController;
    activeLocation.current = { latitude, longitude };

    setLoading(true);
    setError("");
    setData(null);
    setRecommendations([]);
    setIndoorAdvice([]);
    setIndoorLoading(false);
    setIndoorError("");
    setDisclaimer("");
    setChatMessages([]);

    try {
      const response = await fetch(
        `${API}/api/air-quality?latitude=${latitude}&longitude=${longitude}`,
        { signal: controller.signal }
      );

      if (!response.ok) throw new Error("Unable to retrieve air-quality data.");

      if (!cityRequestSequence.current.isCurrent(requestSequence) ||
          activeLocation.current?.latitude !== latitude ||
          activeLocation.current?.longitude !== longitude) {
        return;
      }

      const result: AirQualityData = await response.json();
      if (!result || typeof result !== "object" ||
          !result.current || typeof result.current !== "object" ||
          !result.location || typeof result.location !== "object" ||
          !result.hourly || typeof result.hourly !== "object") {
        throw new Error("Air-quality service returned invalid data.");
      }
      result.current_units = result.current_units &&
        typeof result.current_units === "object"
        ? result.current_units
        : {};
      result.hourly.pm2_5 = Array.isArray(result.hourly.pm2_5)
        ? result.hourly.pm2_5
        : [];
      result.hourly.time = Array.isArray(result.hourly.time)
        ? result.hourly.time
        : [];
      setData(result);

      const recommendationResponse = await fetch(
        `${API}/api/recommendations`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            pm2_5: result.current.pm2_5,
            pm10: result.current.pm10,
            ozone: result.current.ozone,
            nitrogen_dioxide: result.current.nitrogen_dioxide,
            pm2_5_unit: result.current_units.pm2_5 ?? null,
            pm10_unit: result.current_units.pm10 ?? null,
            ozone_unit: result.current_units.ozone ?? null,
            nitrogen_dioxide_unit: result.current_units.nitrogen_dioxide ?? null,
            household,
          }),
          signal: recommendationController.signal,
        }
      );

      if (!recommendationResponse.ok) {
        const errorDetails = await recommendationResponse.text();
        throw new Error(
          `Recommendations failed (${recommendationResponse.status}): ${errorDetails}`
        );
      }

      if (!cityRequestSequence.current.isCurrent(requestSequence) ||
          activeLocation.current?.latitude !== latitude ||
          activeLocation.current?.longitude !== longitude) {
        return;
      }

      const recommendationData = await recommendationResponse.json();
      if (!Array.isArray(recommendationData.recommendations)) {
        throw new Error("Recommendations service returned invalid data.");
      }

      setRecommendations(recommendationData.recommendations);
      setDisclaimer(recommendationData.disclaimer);

    } catch (err) {
      if (cityRequestSequence.current.isCurrent(requestSequence) &&
          !(err instanceof DOMException && err.name === "AbortError")) {
        setError(
          err instanceof Error ? err.message : "Something went wrong."
        );
      }
    } finally {
      if (cityRequestSequence.current.isCurrent(requestSequence)) {
        setLoading(false);
      }
    }
  }

  useEffect(() => {
    if (!data) {
      indoorRequestSequence.current.invalidate();
      indoorRequestAbort.current?.abort();
      return;
    }

    const requestSequence = indoorRequestSequence.current.begin();
    indoorRequestAbort.current?.abort();
    chatRequestAbort.current?.abort();
    chatRequestSequence.current.invalidate();
    const controller = new AbortController();
    indoorRequestAbort.current = controller;
    const location = activeLocation.current;

    void fetch(`${API}/api/indoor-advice`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(
        buildIndoorAdvicePayload(
          data.current.pm2_5 ?? null,
          hasPurifier === "yes" ? "yes" : "no",
          cookingFuel,
          data.current_units.pm2_5 ?? null,
        )
      ),
      signal: controller.signal,
    }).then(async (response) => {
      if (!indoorRequestSequence.current.isCurrent(requestSequence)) return;
      if (!response.ok) {
        const responseText = await response.text();
        throw new Error(
          `Indoor advice failed (${response.status}): ${responseText}`
        );
      }
      const result = await response.json();
      if (!result || !Array.isArray(result.indoor_advice)) {
        throw new Error("Indoor-advice service returned invalid data.");
      }
      if (!indoorRequestSequence.current.isCurrent(requestSequence) ||
          activeLocation.current?.latitude !== location?.latitude ||
          activeLocation.current?.longitude !== location?.longitude) {
        return;
      }
      setIndoorAdvice(result.indoor_advice);
    }).catch((err) => {
      if (indoorRequestSequence.current.isCurrent(requestSequence) &&
          !(err instanceof DOMException && err.name === "AbortError")) {
        setIndoorAdvice([]);
        setIndoorError(
          err instanceof Error
            ? err.message
            : "Unable to refresh indoor advice."
        );
      }
    }).finally(() => {
      if (indoorRequestSequence.current.isCurrent(requestSequence)) {
        setIndoorLoading(false);
      }
    });

    return () => {
      controller.abort();
    };
  }, [data, hasPurifier, cookingFuel]);

  async function sendChatMessage() {
    const question = chatInput.trim();
    if (!question || !data || chatLoading) return;
    if (indoorLoading) {
      setChatError("Indoor advice is refreshing. Please wait before asking.");
      return;
    }
    if (indoorError) {
      setChatError("Indoor advice could not be refreshed. Refresh it before asking.");
      return;
    }

    setChatInput("");
    setChatError("");
    const requestSequence = chatRequestSequence.current.begin();
    chatRequestAbort.current?.abort();
    const controller = new AbortController();
    chatRequestAbort.current = controller;
    const requestLocation = activeLocation.current;
    setChatMessages((messages) => [
      ...messages,
      { role: "user", content: question },
    ]);
    setChatLoading(true);

    try {
      const response = await fetch(`${API}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildChatPayload(
          question,
          data,
          hasPurifier === "yes" ? "yes" : "no",
          cookingFuel,
          household,
          recommendations,
          chatMessages,
        )),
        signal: controller.signal,
      });

      if (!chatRequestSequence.current.isCurrent(requestSequence) ||
          activeLocation.current?.latitude !== requestLocation?.latitude ||
          activeLocation.current?.longitude !== requestLocation?.longitude) {
        return;
      }

      if (!response.ok) {
        const responseBody = await response.text();
        let detail = responseBody || response.statusText;
        try {
          const errorData = JSON.parse(responseBody);
          detail = errorData.detail || detail;
        } catch {
          // Keep the response text when the server does not return JSON.
        }
        throw new Error(
          response.status === 503
            ? `Assistant unavailable: ${detail}`
            : `Chat request failed (${response.status}): ${detail}`
        );
      }

      const result = await response.json();
      if (!chatRequestSequence.current.isCurrent(requestSequence) ||
          activeLocation.current?.latitude !== requestLocation?.latitude ||
          activeLocation.current?.longitude !== requestLocation?.longitude) {
        return;
      }
      if (!result || typeof result.answer !== "string" || !result.answer.trim()) {
        throw new Error("The assistant returned an invalid response.");
      }
      setChatMessages((messages) => [
        ...messages,
        { role: "assistant", content: result.answer },
      ]);
    } catch (err) {
      if (chatRequestSequence.current.isCurrent(requestSequence) &&
          !(err instanceof DOMException && err.name === "AbortError")) {
        setChatError(
          err instanceof Error
            ? err.message
            : "Unable to send your message. Check that the backend and Ollama are running."
        );
      }
    } finally {
      if (chatRequestSequence.current.isCurrent(requestSequence)) {
        setChatLoading(false);
      }
    }
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">AQ</span>
          <div>
            <p className="eyebrow">URBAN AIR</p>
            <h1>Air quality assistant</h1>
          </div>
        </div>
        <div className={`location-chip${selectedCity ? "" : " location-chip--empty"}`}>
          <span className="location-dot" aria-hidden="true" />
          <span>{selectedCity || "No location selected"}</span>
        </div>
      </header>

      <section className="panel search-panel" aria-labelledby="location-heading">
        <div className="section-heading">
          <div>
            <p className="eyebrow">LOCAL DASHBOARD</p>
            <h2 id="location-heading">Choose a location</h2>
            <p className="section-description">
              Search for a city to view modelled outdoor air quality.
            </p>
          </div>
        </div>

        <div className="search-row">
          <label className="sr-only" htmlFor="city-search">Search city</label>
          <input
            id="city-search"
            className="text-input"
            value={city}
            onChange={(e) => setCity(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") searchCity();
            }}
            placeholder="Enter city name"
          />
          <button className="button button--primary" onClick={searchCity}>
            Search
          </button>
        </div>

        {locations.length > 0 && (
          <div className="location-results" aria-label="City search results">
            {locations.map((place, index) => (
              <button
                className="location-option"
                key={`${place.latitude}-${place.longitude}-${index}`}
                onClick={() => selectCity(place)}
              >
                <span>{place.name}</span>
                <span className="location-option-detail">
                  {[place.admin1, place.country].filter(Boolean).join(", ")}
                </span>
              </button>
            ))}
          </div>
        )}

        <div className="preferences">
          <div className="preferences-heading">
            <div>
              <p className="eyebrow">HOUSEHOLD PROFILE</p>
              <h3>Personalize your advice</h3>
            </div>
            <span className="profile-indicator">Used for indoor guidance</span>
          </div>
          <div className="preferences-fields">
            <label className="form-field">
              <span>Air purifier availability</span>
              <select
                value={hasPurifier}
                onChange={(e) => {
                  setHasPurifier(e.target.value);
                  if (data) {
                    setIndoorLoading(true);
                    setIndoorAdvice([]);
                    setIndoorError("");
                    setChatLoading(false);
                    setChatMessages([]);
                  }
                }}
              >
                <option value="no">No purifier</option>
                <option value="yes">Available</option>
              </select>
            </label>

            <label className="form-field">
              <span>Cooking fuel</span>
              <select
                value={cookingFuel}
                onChange={(e) => {
                  setCookingFuel(e.target.value);
                  if (data) {
                    setIndoorLoading(true);
                    setIndoorAdvice([]);
                    setIndoorError("");
                    setChatLoading(false);
                    setChatMessages([]);
                  }
                }}
              >
                <option value="lpg">LPG</option>
                <option value="electricity">Electricity</option>
                <option value="wood">Wood</option>
                <option value="coal">Coal</option>
                <option value="other">Other</option>
              </select>
            </label>
          </div>
        </div>
      </section>

      {error && <p className="notice notice--error" role="alert">{error}</p>}
      {loading && (
        <p className="notice notice--loading" role="status">
          Fetching air quality and family recommendations...
        </p>
      )}

      {data && (
        <>
          <section className="data-section" aria-labelledby="overview-heading">
            <div className="section-heading section-heading--row">
              <div>
                <p className="eyebrow">OUTDOOR CONDITIONS</p>
                <h2 id="overview-heading">Current pollutant levels</h2>
                <p className="section-description">
                  The most recent modelled readings for {selectedCity || "your selected location"}.
                </p>
              </div>
              <span className="data-badge">
                <span className="data-badge-dot" aria-hidden="true" />
                Modelled outdoor data
              </span>
            </div>

            <div className="pollutant-grid">
              {pollutants.map((pollutant) => {
                const value = data.current[pollutant.key];
                const isMissing = value == null;
                const isProminent =
                  pollutant.key === "pm2_5" || pollutant.key === "pm10";

                return (
                  <article
                    className={`pollutant-card${isProminent ? " pollutant-card--prominent" : ""}${isMissing ? " pollutant-card--missing" : ""}`}
                    key={pollutant.key}
                  >
                    <p className="pollutant-label">{pollutant.label}</p>
                    <p className="pollutant-value">
                      {isMissing ? "Not available" : value}
                    </p>
                    <p className="pollutant-unit">
                      {isMissing
                        ? "Reading unavailable"
                        : data.current_units[pollutant.key] ?? "Unit unavailable"}
                    </p>
                  </article>
                );
              })}
            </div>

            <section className="panel forecast-panel" aria-labelledby="forecast-heading">
              <div className="section-heading section-heading--compact">
                <div>
                  <p className="eyebrow">NEXT 12 HOURS</p>
                  <h3 id="forecast-heading">Hourly PM2.5 forecast</h3>
                </div>
                <span className="forecast-unit">
                  {data.current_units.pm2_5 ?? "Unit unavailable"}
                </span>
              </div>
              {data.hourly.pm2_5.slice(0, 12).some(
                (value) => typeof value === "number",
              ) ? (
                <div className="forecast-scroll">
                  <div className="forecast-chart">
                    {data.hourly.pm2_5.slice(0, 12).map(
                      (value: number | null, index: number) => {
                        if (typeof value !== "number") return null;
                        const max = Math.max(
                          ...data.hourly.pm2_5
                            .filter((item): item is number => typeof item === "number")
                            .slice(0, 12),
                          1
                        );

                        return (
                          <div className="forecast-item" key={index}>
                            <span className="forecast-value">{value}</span>
                            <div
                              className="forecast-bar"
                              style={{ height: `${value / max * 125}px` }}
                              role="img"
                              aria-label={`PM2.5 ${value} ${data.current_units.pm2_5 ?? ""}`}
                            />
                            <span className="forecast-time">
                              {typeof data.hourly.time[index] === "string"
                                ? data.hourly.time[index].slice(11, 16)
                                : "N/A"}
                            </span>
                          </div>
                        );
                      }
                    )}
                  </div>
                </div>
              ) : (
                <p className="empty-state">Hourly PM2.5 forecast is unavailable.</p>
              )}
            </section>
          </section>

          <div className="support-grid">
            <section className="panel content-panel" aria-labelledby="recommendations-heading">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">OUTDOOR ACTION PLAN</p>
                  <h2 id="recommendations-heading">Family air-quality action plan</h2>
                  <p className="section-description">
                    Recommendations for households with children
                  </p>
                </div>
              </div>
              {recommendations.length > 0 ? (
                <div className="recommendation-list">
                  {recommendations.map((item, index) => (
                    <article
                      className={`recommendation-card recommendation-card--${item.priority.toLowerCase()}`}
                      key={index}
                    >
                      <div className="recommendation-card-heading">
                        <span className="recommendation-category">{item.category}</span>
                        <span className={`priority-badge priority-badge--${item.priority.toLowerCase()}`}>
                          <span className="priority-dot" aria-hidden="true" />
                          {item.priority}
                        </span>
                      </div>
                      <h3>{item.action}</h3>
                      <p>{item.reason}</p>
                      <p className="alternative">
                        <strong>Try instead:</strong> {item.alternative}
                      </p>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="empty-state">No outdoor recommendations are available for these readings.</p>
              )}
            </section>

            <section className="panel content-panel" aria-labelledby="indoor-heading">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">AT HOME</p>
                  <h2 id="indoor-heading">Indoor Air Quality Advisor</h2>
                  <p className="section-description">
                    Practical guidance shaped by your household profile.
                  </p>
                </div>
              </div>

              <div className="household-summary">
                <p className="household-summary-title">Current household profile</p>
                <div className="profile-tags">
                  <span className="profile-tag">
                    Air purifier <strong>{hasPurifier === "yes" ? "Yes" : "No"}</strong>
                  </span>
                  <span className="profile-tag">
                    Cooking fuel <strong>{cookingFuel.charAt(0).toUpperCase() + cookingFuel.slice(1)}</strong>
                  </span>
                </div>
              </div>

              {indoorLoading && (
                <p className="notice notice--loading" role="status">
                  Refreshing indoor advice...
                </p>
              )}
              {indoorError && (
                <p className="notice notice--error" role="alert">{indoorError}</p>
              )}
              {indoorAdvice.length > 0 ? (
                <div className="advice-list">
                  {indoorAdvice.map((item, index) => {
                    const isFuelSpecific = item.title === "Reduce cooking pollution";
                    const isPurifierSpecific =
                      item.title === "Use your air purifier effectively" ||
                      item.title === "Consider particle filtration";
                    const isPersonalized = isFuelSpecific || isPurifierSpecific;
                    const label = isFuelSpecific
                      ? `${cookingFuel.charAt(0).toUpperCase() + cookingFuel.slice(1)}-specific advice`
                      : isPurifierSpecific
                        ? "Purifier-specific advice"
                        : "General recommendation";

                    return (
                      <article
                        className={`advice-card${isPersonalized ? " advice-card--personalized" : ""}`}
                        key={index}
                      >
                        <span className="advice-label">{label}</span>
                        <h3>{item.title}</h3>
                        <p className="advice-action">{item.action}</p>
                        <p>{item.reason}</p>
                      </article>
                    );
                  })}
                </div>
              ) : !indoorLoading && !indoorError ? (
                <p className="empty-state">No indoor advice is available for this profile and reading.</p>
              ) : null}
            </section>
          </div>

          <section className="panel chat-panel" aria-labelledby="chat-heading">
            <div className="section-heading section-heading--row">
              <div>
                <p className="eyebrow">ASK A QUESTION</p>
                <h2 id="chat-heading">Air Quality Assistant</h2>
                <p className="section-description">
                  Ask about the current readings or your household recommendations.
                </p>
              </div>
              <span className="assistant-badge">
                <span className="assistant-badge-dot" aria-hidden="true" />
                Context-aware
              </span>
            </div>

            <div className="chat-messages" aria-live="polite">
              {chatMessages.map((message, index) => (
                <article className={`chat-message chat-message--${message.role}`} key={index}>
                  <strong className="chat-author">
                    {message.role === "user" ? "You" : "Assistant"}
                  </strong>
                  {message.role === "assistant"
                    ? <AssistantMarkdown content={message.content} />
                    : <p>{message.content}</p>}
                </article>
              ))}
              {chatLoading && (
                <p className="notice notice--loading" role="status">
                  Assistant is thinking...
                </p>
              )}
            </div>

            {chatError && (
              <p className="notice notice--error" role="alert">{chatError}</p>
            )}

            <div className="chat-compose">
              <label className="sr-only" htmlFor="chat-input">
                Message the Air Quality Assistant
              </label>
              <textarea
                id="chat-input"
                value={chatInput}
                onChange={(event) => setChatInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void sendChatMessage();
                  }
                }}
                placeholder="Ask a question about your air quality"
                rows={3}
              />
              <button
                className="button button--primary chat-send"
                type="button"
                onClick={() => void sendChatMessage()}
                disabled={!chatInput.trim() || chatLoading || indoorLoading || Boolean(indoorError)}
              >
                {chatLoading ? "Sending..." : "Send"}
              </button>
            </div>
            <small className="keyboard-hint">
              Press Enter to send, or Shift+Enter for a new line.
            </small>
          </section>

          <footer className="data-footer">
            {disclaimer && <p className="disclaimer">{disclaimer}</p>}
            <p>
              Source: Open-Meteo Air Quality API
              <span aria-hidden="true"> · </span>
              Timezone: {data.location.timezone ?? "Not provided"}
            </p>
            <p>{data.model_note}</p>
          </footer>
        </>
      )}
    </main>
  );
}

export default App;