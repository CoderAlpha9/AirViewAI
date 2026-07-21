import { useEffect, useState } from "react";

import { advisory, apiError, type Advisory } from "../api/product";
import { CitySelector, LanguageSelector } from "../components/product/ProductControls";
import { ConfidenceIndicator, ErrorState, LimitationNotice, LoadingState, ReplayModeBadge } from "../components/product/ProductStates";

export function CitizenAdvisoryPage() {
  const [city, setCity] = useState("delhi-ncr"); const [language, setLanguage] = useState("en"); const [data, setData] = useState<Advisory>(); const [error, setError] = useState("");
  useEffect(() => { const controller = new AbortController(); void advisory(city, language, "standard", controller.signal).then((next) => { setData(next); setError(""); }).catch((reason: unknown) => { if (!controller.signal.aborted) setError(apiError(reason)); }); return () => controller.abort(); }, [city, language]);
  return <section className="mx-auto max-w-xl px-6 py-12"><ReplayModeBadge /><p className="mt-4 text-xs font-semibold uppercase tracking-[.18em] text-air">Historical public-information replay</p><h1 className="mt-3 text-3xl font-semibold">Citizen advisory</h1><div className="mt-6 flex flex-wrap gap-3"><CitySelector value={city} onChange={setCity} /><LanguageSelector value={language} onChange={setLanguage} /></div>{error && <div className="mt-6"><ErrorState message={error} /></div>}{!data && !error && <div className="mt-6"><LoadingState label="Loading advisory replay…" /></div>}{data && <article className="mt-6 border border-line bg-panel p-5"><p className="text-air">{data.severity}</p><h2 className="mt-2 text-xl font-medium">{data.headline}</h2><p className="mt-4 leading-7 text-mist">{data.rendered_text}</p><p className="mt-5 text-xs text-mist"><ConfidenceIndicator value={data.confidence} /> · {data.issue_timestamp}</p><p className="mt-3 text-xs text-mist">{data.disclaimer}</p><LimitationNotice items={data.warnings} /></article>}</section>;
}
